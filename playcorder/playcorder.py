__author__ = 'mpevans'

import localfluidsynth
import time
import thread
from collections import namedtuple
from marcpy.chuck.chuck import *
from marcpy import utilities
from marcpy import barlicity
from music21 import converter
from music21 import musicxml
from music21.stream import Voice, Part, Score
from music21.note import Note, Rest
from music21.pitch import Pitch
from music21.tempo import MetronomeMark
from music21.meter import TimeSignature
from xml.etree.ElementTree import ElementTree
from MidiFile import MIDIFile
from fractions import Fraction

PCNote = namedtuple("PCNote", "start_time length pitch volume variant")


class BeatQuantizationScheme:

    def __init__(self, tempo, beat_length, max_divisions=8, max_indigestibility=4, quantization_divisions=None,
                 simplicity_preference=1.0):
        """

        :param tempo: In quarter-notes per minute
        :param beat_length: In quarter-notes
        :param max_divisions: For generating preferred divisions automatically, the biggest divisor allowed.
        :param max_indigestibility: For generating preferred divisions automatically, the biggest divisor
        indigestibility allowed.
        :param quantization_divisions: Use this to set the quantization divisions manually. Either a 1D list or
        tuple, or a nx2 list/tuple consisting of (divisor, divisor undesirability) as elements. If 1D, the
        undesirabilities are generated automatically.
        :param simplicity_preference: ranges 0 - whatever. A simplicity_preference of 0 means, all divisions are
        treated equally; a 7 is as good as a 4. A simplicity_preference of 1 means that the most desirable division
        is left along, the most undesirable division gets its error doubled, and all other divisions are somewhere in
        between. Simplicity preference can be greater than 1.
        """
        self.tempo = tempo
        self.beat_length = float(beat_length)

        # now we populate a self.quantization_divisions with tuples consisting of the allowed divisions and
        # their undesirabilities. Undesirability is a factor by which the error in a given quantization option
        # is multiplied; the lowest possible undesirability is 1
        if quantization_divisions is None:
            # what we care about is how well the given division works within the most natural division of the beat_length
            # so first notate the beat_length as a fraction; its numerator is its most natural division
            beat_length_fraction = Fraction(self.beat_length).limit_denominator()

            quantization_divisions = []
            div_indigestibilities = []
            for div in range(2, max_divisions + 1):
                relative_division = Fraction(div, beat_length_fraction.numerator)
                div_indigestibility = barlicity.indigestibility(relative_division.numerator) + \
                    barlicity.indigestibility(relative_division.denominator)
                if div_indigestibility < max_indigestibility:
                    quantization_divisions.append(div)
                    div_indigestibilities.append(div_indigestibility)
            div_indigestibility_range = min(div_indigestibilities), max(div_indigestibilities)
            div_undesirabilities = [1 + simplicity_preference * (float(di) - div_indigestibility_range[0]) /
                                    (div_indigestibility_range[1] - div_indigestibility_range[0])
                                    for di in div_indigestibilities]
            self.quantization_divisions = zip(quantization_divisions, div_undesirabilities)
        else:
            if isinstance(quantization_divisions[0], tuple):
                # already (divisor, undesirability) tuples
                self.quantization_divisions = quantization_divisions
            else:
                # we've just been given the divisors, and have to figure out the undesirabilities
                beat_length_fraction = Fraction(self.beat_length).limit_denominator()
                div_indigestibilities = []
                for div in quantization_divisions:
                    relative_division = Fraction(div, beat_length_fraction.numerator)
                    div_indigestibility = barlicity.indigestibility(relative_division.numerator) + \
                        barlicity.indigestibility(relative_division.denominator)
                    div_indigestibilities.append(div_indigestibility)
                div_indigestibility_range = min(div_indigestibilities), max(div_indigestibilities)
                div_undesirabilities = [1 + simplicity_preference * (float(di) - div_indigestibility_range[0]) /
                                        (div_indigestibility_range[1] - div_indigestibility_range[0])
                                        for di in div_indigestibilities]
                self.quantization_divisions = zip(quantization_divisions, div_undesirabilities)


class MeasureScheme:

    def __init__(self, time_signature, beat_quantization_schemes):
        # time_signature is either a tuple, e.g. (3, 4), or a string, e.g. "3/4"
        if isinstance(time_signature, str):
            self.string_time_signature = time_signature
            tuple_time_signature = tuple(time_signature.split("/"))
        else:
            tuple_time_signature = tuple(time_signature)
            self.string_time_signature = str(time_signature[0]) + "/" + str(time_signature[1])
        measure_length_in_quarters = tuple_time_signature[0]*4/float(tuple_time_signature[1])

        # either we give a list of beat_quantization schemes or a single beat quantization scheme to use for all beats
        if hasattr(beat_quantization_schemes, "__len__"):
            total_length = 0
            for beat_quantization_scheme in beat_quantization_schemes:
                assert isinstance(beat_quantization_scheme, BeatQuantizationScheme)
                total_length += beat_quantization_scheme.beat_length
            assert total_length == measure_length_in_quarters
            self.beat_quantization_schemes = beat_quantization_schemes
        else:
            assert isinstance(beat_quantization_schemes, BeatQuantizationScheme)
            assert utilities.is_multiple(measure_length_in_quarters, beat_quantization_schemes.beat_length)
            self.beat_quantization_schemes = [beat_quantization_schemes] * \
                int(round(measure_length_in_quarters /beat_quantization_schemes.beat_length))


class Playcorder:

    def __init__(self, soundfont_path=None, channels_per_part=50):
        """

        :param soundfont_path: if we are using midi playback, the soundfont path
        :param channels_per_part: in fluidsynth midi playback,  each new note is played through a separate "channel".
        This sets the number of channels used by each instrument before recycling. Essentially a max # of voices.
        """

        # list of the current instruments used by this playcorder
        self.instruments = []

        # --- MIDI setup, if necessary ---
        self.channels_per_part = channels_per_part
        self.used_channels = 0  # how many channels have we already assigned to various instruments
        self.synth = None
        self.soundfont_id = None  # the id of a loaded soundfont
        if soundfont_path is not None:
            if soundfont_path == "default":
                soundfont_path = get_relative_file_path("LiteSoundFont.sf2")
            self.initialize_fluidsynth(soundfont_path)

        # construct a list of all the instruments available in the soundfont, for reference access
        self.instrument_list = None
        if soundfont_path is not None:
            from sf2utils.sf2parse import Sf2File
            with open(soundfont_path, "rb") as sf2_file:
                sf2 = Sf2File(sf2_file)
                self.instrument_list = sf2.presets

        # --- Recording Setup ---
        # parts_being_recorded is a list of parts being recorded if recording otherwise it's None
        self.parts_being_recorded = None
        # once recording stops parts_recorded stores the parts that were recorded
        self.parts_recorded = None
        # recording_start_time is used if using time.time() as time
        # time_passed is used if manually recording time
        self.recording_start_time = None
        self.time_passed = None

    def initialize_fluidsynth(self, soundfont_path):
        # loads the soundfont and gets the synth going
        self.synth = localfluidsynth.Synth()
        self.soundfont_id = self.synth.sfload(soundfont_path)
        self.synth.start()

    def get_instruments_with_substring(self, word):
        if self.instrument_list is None:
            return None
        return [inst for i, inst in enumerate(self.instrument_list) if word.lower() in inst.name.lower()]

    def add_part(self, instrument):
        assert isinstance(instrument, PlaycorderInstrument)
        if not hasattr(instrument, "name") or instrument.name is None:
            instrument.name = "Track " + str(len(self.instruments) + 1)
        instrument.host_playcorder = self
        self.instruments.append(instrument)

    def add_midi_part(self, preset, name=None):
        """
        Constructs a MidiPlaycorderInstrument, adds it to the Playcorder, and returns it
        :param preset: if an int, assumes bank #0; can also be a tuple of form (bank, preset)
        :rtype : MidiPlaycorderInstrument
        """
        if self.synth is None:
            raise Exception("Fluidsynth not initialized")

        if name is None:
            name = "Track " + str(len(self.instruments) + 1)

        if isinstance(preset, int):
            # if just an int, assume bank 0 and that's the preset
            instrument = MidiPlaycorderInstrument(self.synth, self.soundfont_id, (0, preset), self.used_channels,
                                                  self.channels_per_part, self, name)
        else:
            # inst_num is a bank, preset pair
            instrument = MidiPlaycorderInstrument(self.synth, self.soundfont_id, preset, self.used_channels,
                                                  self.channels_per_part, self, name)

        self.used_channels += self.channels_per_part
        self.add_part(instrument)
        return instrument

    def add_silent_part(self, name=None):
        """
        Constructs a SilentPlaycorderInstrument, adds it to the Playcorder, and returns it
        :rtype : SilentPlaycorderInstrument
        """
        name = "Track " + str(len(self.instruments) + 1) if name is None else name
        instrument = PlaycorderInstrument(self, name=name)
        self.add_part(instrument)
        return instrument

    # ----------------------------------- Recording ----------------------------------

    def record_note(self, instrument, pitch, volume, length, start_delay=0,
                    variant_dictionary=None, start_time=None, written_length=None):
        if self.parts_being_recorded is not None and instrument in self.parts_being_recorded:
            if start_time is not None:
                note_start_time = start_time
            else:
                note_start_time = self.get_time_passed() + start_delay
            instrument.recording.append(PCNote(start_time=note_start_time,
                                               length=length if written_length is None else written_length,
                                               pitch=pitch, volume=volume, variant=variant_dictionary))

    def get_time_passed(self):
        if self.parts_being_recorded is not None:
            if self.time_passed is not None:
                # manually logging time, so use time_passed
                return self.time_passed
            else:
                # not manually logging time; just measure from the start time
                return time.time()-self.recording_start_time

    def start_recording(self, which_parts=None, manual_time=False):
        if manual_time:
            self.time_passed = 0
        else:
            self.recording_start_time = time.time()
        self.parts_being_recorded = self.instruments if which_parts is None else which_parts
        # the "score" for each part is recorded as an attribute of that part called "recording"
        for instrument in self.parts_being_recorded:
            instrument.recording = []

    def stop_recording(self):
        for part in self.parts_being_recorded:
            part.end_all_notes()
        self.parts_recorded = self.parts_being_recorded
        self.parts_being_recorded = None
        self.time_passed = None
        self.recording_start_time = None

    # used for a situation where all parts are played from a single thread
    def wait(self, seconds):
        if self.time_passed is not None:
            self.time_passed += seconds
        time.sleep(seconds)

    # used for a situation where time is recorded manually, but there may be multiple threads,
    # only one of which registers time passed.
    def register_time_passed(self, seconds):
        self.time_passed += seconds

    # ----------------------------------- Saving Output ----------------------------------

    @staticmethod
    def _quantize_recording(recording_in_seconds, beat_schemes, onset_termination_weighting=0.3):

        """

        :param recording_in_seconds: a voice consisting of PCNotes, with timings in seconds
        :param beat_schemes: a list of beat_schemes through which we iterate, which determine the quantization
        parameters. The last beat scheme is looped through till the end.
        :param onset_termination_weighting: 0 means we only care about onsets when determining the best quantization,
        and 1 means we only care about terminations. In between is a weighting.
        """
        # raw_onsets and raw_terminations are in seconds
        raw_onsets = [(pc_note.start_time, pc_note) for pc_note in recording_in_seconds]
        raw_terminations = [(pc_note.start_time + pc_note.length, pc_note) for pc_note in recording_in_seconds]
        raw_onsets.sort(key=lambda x: x[0])
        raw_terminations.sort(key=lambda x: x[0])

        pc_note_to_quantized_start_time = {}
        pc_note_to_quantized_end_time = {}
        current_beat_scheme = 0
        beat_start_time = 0
        while len(raw_onsets) + len(raw_terminations) > 0:
            # move forward one beat at a time
            # get the beat scheme for this beat
            this_beat_scheme = beat_schemes[current_beat_scheme]
            assert isinstance(this_beat_scheme, BeatQuantizationScheme)
            if current_beat_scheme + 1 < len(beat_schemes):
                current_beat_scheme += 1

            this_beat_seconds_length = this_beat_scheme.beat_length * 60.0 / this_beat_scheme.tempo
            beat_end_time = beat_start_time + this_beat_seconds_length

            # find the onsets in this beat
            onsets_to_quantize = []
            while len(raw_onsets) > 0 and raw_onsets[0][0] < beat_end_time:
                onsets_to_quantize.append(raw_onsets.pop(0))

            # find the terminations in this beat
            terminations_to_quantize = []
            while len(raw_terminations) > 0 and raw_terminations[0][0] < beat_end_time:
                terminations_to_quantize.append(raw_terminations.pop(0))

            # try out each quantization division
            best_divisor = None
            best_error = float("inf")
            for divisor, undesirability in this_beat_scheme.quantization_divisions:
                piece_length = this_beat_scheme.beat_length / divisor
                total_squared_onset_error = 0
                for onset in onsets_to_quantize:
                    total_squared_onset_error += (onset[0] - utilities.round_to_multiple(onset[0] - beat_start_time, piece_length)) ** 2
                total_squared_term_error = 0
                for term in terminations_to_quantize:
                    total_squared_term_error += (term[0] - utilities.round_to_multiple(term[0] - beat_start_time, piece_length)) ** 2
                this_div_error_score = undesirability * (onset_termination_weighting * total_squared_term_error +
                                                         (1 - onset_termination_weighting) * total_squared_onset_error)
                if this_div_error_score < best_error:
                    best_divisor = divisor
                    best_error = this_div_error_score

            best_piece_length = this_beat_scheme.beat_length / best_divisor
            for onset, pc_note in onsets_to_quantize:
                pc_note_to_quantized_start_time[pc_note] = beat_start_time + utilities.round_to_multiple(onset - beat_start_time, best_piece_length)
            for termination, pc_note in terminations_to_quantize:
                pc_note_to_quantized_end_time[pc_note] = beat_start_time + utilities.round_to_multiple(termination - beat_start_time, best_piece_length)
                if pc_note_to_quantized_end_time[pc_note] == pc_note_to_quantized_start_time[pc_note]:
                    # if the quantization collapses the start and end times of a note to the same point, adjust the
                    # end time so the the not is a single piece_length long. Not perfect, but better than deleting
                    pc_note_to_quantized_end_time[pc_note] += best_piece_length
            beat_start_time += this_beat_seconds_length

        return [PCNote(start_time=pc_note_to_quantized_start_time[pc_note],
                length=pc_note_to_quantized_end_time[pc_note] - pc_note_to_quantized_start_time[pc_note],
                pitch=pc_note.pitch, volume=pc_note.volume, variant=pc_note.variant)
                for pc_note in recording_in_seconds]

    @staticmethod
    def _collapse_recording_chords(recording):
        # sort it
        out = sorted(recording, key=lambda x: x.start_time)
        # combine contemporaneous notes into chords
        i = 0
        while i + 1 < len(out):
            if out[i].start_time == out[i+1].start_time and out[i].length == out[i+1].length \
                    and out[i].volume == out[i+1].volume and out[i].variant == out[i+1].variant:
                chord_pitches = utilities.make_flat_list(out[i].pitch, out[i+1].pitch)
                out = out[:i] + [PCNote(start_time=out[i].start_time, length=out[i].length, pitch=chord_pitches,
                                 volume=out[i].volume, variant=out[i].variant)] + out[i+2:]
            else:
                i += 1
        # Now split it into non-overlapping voices, and then we're good.
        return out

    @staticmethod
    def _separate_into_non_overlapping_voices(recording, max_overlap):
        # takes a recording of PCNotes and breaks it up into separate voices that don't overlap more than max_overlap
        assert isinstance(recording, list)
        recording.sort(key=lambda note: note.start_time)
        voices = []
        for pc_note in recording:
            # find the first non-conflicting voices
            voice_to_add_to = None
            for voice in voices:
                voice_end_time = voice[-1].start_time + voice[-1].length
                if voice_end_time - pc_note.start_time < max_overlap:
                    voice_to_add_to = voice
                    break
            if voice_to_add_to is None:
                voice_to_add_to = []
                voices.append(voice_to_add_to)
            voice_to_add_to.append(pc_note)

        return voices

    # Make this a save to MIDI, and give options for the search tree
    def save_to_xml_file(self, tempo=60, time_signature="4/4", max_overlap=0.01, name=None, quantization_divisions=(4,)):
        print "Saving Output..."

        # scale the note lengths up by this factor, since we recorded them in seconds, not beats
        tempo_scaling_factor = tempo/60.0
        m21_score = Score()
        for i, part in enumerate(self.parts_recorded):
            print "Working on Part " + str(i+1) + "..."
            voices = Playcorder._separate_into_non_overlapping_voices(part.recording, max_overlap)
            m21_part = Part()
            for voice in voices:
                m21_voice = Voice()
                # current_beat = 0
                for pc_note in voice:
                    assert isinstance(pc_note, PCNote)
                    scaled_start_time = pc_note.start_time*tempo_scaling_factor
                    note_beat_length = pc_note.length * tempo_scaling_factor
                    the_note = Note(Pitch(pc_note.pitch), quarterLength=note_beat_length)
                    m21_voice.insert(scaled_start_time, the_note)
                m21_voice.quantize(quantization_divisions, processOffsets=True, processDurations=True, inPlace=True)
                new_m21_voice = Voice()
                current_beat = 0

                for m21Note in m21_voice:
                    if m21Note.offset > current_beat:
                        new_m21_voice.append(Rest(quarterLength = m21Note.offset - current_beat))
                        current_beat += m21Note.offset - current_beat
                    new_m21_voice.append(m21Note)
                    current_beat += m21Note.quarterLength
                m21_part.insert(0, TimeSignature(time_signature))
                m21_part.insert(0, new_m21_voice)
            m21_score.insert(0, m21_part)
        m21_score.insert(MetronomeMark(number=tempo))
        gex = musicxml.m21ToXml.GeneralObjectExporter()
        sx = musicxml.m21ToXml.ScoreExporter(gex.fromGeneralObject(m21_score))
        mx_score = sx.parse()

        ElementTree(mx_score).write(name)

    def save_to_midi_file(self, path, tempo=60, max_overlap=0.01):
        parts = [Playcorder._separate_into_non_overlapping_voices(part.recording, max_overlap) for part in self.parts_recorded]
        midi_file = MIDIFile(sum([len(x) for x in parts]))

        current_track = 0
        tempo_scaling_factor = tempo/60.0
        for which_part, part in enumerate(parts):
            current_voice = 0
            for voice in part:
                midi_file.addTrackName(current_track, 0, self.parts_recorded[which_part].name + " " + str(current_voice + 1))
                midi_file.addTempo(current_track, 0, tempo)

                for pc_note in voice:
                    assert isinstance(pc_note, PCNote)
                    midi_file.addNote(current_track, 0, int(round(pc_note.pitch)), pc_note.start_time * tempo_scaling_factor,
                                      pc_note.length * tempo_scaling_factor, int(pc_note.volume*127))

                current_track += 1
                current_voice += 1

        bin_file = open(path, 'wb')
        midi_file.writeFile(bin_file)
        bin_file.close()


class PlaycorderInstrument:

    def __init__(self, host_playcorder=None, name=None):
        assert isinstance(host_playcorder, Playcorder)
        self.host_playcorder = host_playcorder
        self.name = name
        self.notes_started = []   # each entry goes (note_id, pitch, volume, start_time, variant_dictionary)

    # ------------------ Methods to be overridden by subclasses ------------------

    def _do_play_note(self, pitch, volume, length, start_delay, variant_dictionary):
        # Does the actual sonic implementation of playing a note
        pass

    def _do_start_note(self, pitch, volume, variant_dictionary=None):
        # Does the actual sonic implementation of starting a note
        # should return the note_id, which is used to keep track of the note
        return 0

    def _do_end_note(self, note_id):
        # Does the actual sonic implementation of ending a the note with the given id
        pass

    def change_note_pitch(self, note_id, new_pitch):
        # Changes the pitch of the note with the given id
        pass

    # ------------------------- "Public" Playback Methods -------------------------

    def play_note(self, pitch, volume, length, start_delay=0, variant_dictionary=None):
        thread.start_new_thread(self._do_play_note, (pitch, volume, length, start_delay, variant_dictionary))
        # record the note in the hosting playcorder, if it's recording
        if self.host_playcorder and self.host_playcorder.get_time_passed() is not None:
            self.host_playcorder.record_note(self, pitch, volume, length,
                                             start_delay, variant_dictionary=variant_dictionary)

    def start_note(self, pitch, volume, variant_dictionary=None):
        note_id = self._do_start_note(pitch, volume, variant_dictionary)
        self.notes_started.append((note_id, pitch, volume, self.host_playcorder.get_time_passed(), variant_dictionary))
        # returns the channel as a reference, in case we want to start and stop a bunch of these
        return note_id

    def end_note(self, note_id=None):
        note_to_end = None
        if note_id is not None:
            # find the note referred to in the notes_started list
            for started_note in self.notes_started:
                if started_note[0] == note_id:
                    note_to_end = started_note
                    break
            if note_to_end is not None:
                self.notes_started.remove(note_to_end)
        elif len(self.notes_started) > 0:
            # if no note_id is specified, just end the note that has been going the longest
            note_to_end = self.notes_started.pop(0)

        if note_to_end is None:
            # no appropriate note has been found to end
            return

        note_id, pitch, volume, start_time, variant_dictionary = note_to_end
        # call the specific implementation to stop the note
        self._do_end_note(note_id)
        # record the note in the hosting playcorder, if it's recording
        if start_time is not None and self.host_playcorder.get_time_passed() is not None:
            self.host_playcorder.record_note(self, pitch, volume, self.host_playcorder.get_time_passed()-start_time,
                                             start_time=start_time, variant_dictionary=variant_dictionary)

    def end_all_notes(self):
        while len(self.notes_started) > 0:
            self.end_note()

    def num_notes_playing(self):
        return len(self.notes_started)


class MidiPlaycorderInstrument(PlaycorderInstrument):

    def __init__(self, synth, soundfont_id, (bank, preset), start_channel, num_channels, host_playcorder=None, name=None):
        assert isinstance(synth, localfluidsynth.Synth)
        assert isinstance(host_playcorder, Playcorder)
        PlaycorderInstrument.__init__(self, host_playcorder=host_playcorder, name=name)

        self.host_playcorder = host_playcorder
        self.name = name

        self.synth = synth
        # set all the channels owned by this instrument to the correct preset
        for i in range(start_channel, start_channel + num_channels):
            synth.program_select(i, soundfont_id, bank, preset)

        self.current_channel = 0
        self.start_channel = start_channel
        self.num_channels = num_channels

    def _do_start_note(self, pitch, volume, variant_dictionary=None):
        # Does the actual sonic implementation of starting a note
        # in this case the note_id returned will be a tuple consisting of the channel and the midi key pressed
        channel = self.start_channel + self.current_channel
        self.current_channel = (self.current_channel + 1) % self.num_channels
        int_pitch = int(round(pitch))
        pitch_bend_val = int((pitch - int_pitch)*2048)
        self.synth.pitch_bend(channel, pitch_bend_val)
        self.synth.noteon(channel, int_pitch, int(volume*127))
        return channel, int_pitch

    def _do_end_note(self, note_id):
        # Does the actual sonic implementation of ending a the note with the given note_id = channel, key pressed
        channel, int_pitch = note_id
        self.synth.noteon(channel, int_pitch, 0)

    def _do_play_note(self, pitch, volume, length, start_delay, variant_dictionary):
        # Does the actual sonic implementation of playing a note
        time.sleep(start_delay)
        note_id = self._do_start_note(pitch, volume, variant_dictionary)
        time.sleep(length)
        self._do_end_note(note_id)

    def change_note_pitch(self, note_id, new_pitch):
        # Changes the pitch of the note started at channel
        channel, int_pitch = note_id
        pitch_bend_val = int((new_pitch - int_pitch) * 4096)
        # unfortunately there is a limit of -8192 to 8192 (or 4 half-steps up or down), so we confine it to this range
        pitch_bend_val = min(max(pitch_bend_val, -8192), 8191)
        self.synth.pitch_bend(channel, pitch_bend_val)


# -------------- EXAMPLE --------------
# pc = Playcorder(soundfont_path="default")
# piano = pc.add_midi_part(0)

# pc.start_recording([piano])
# n = piano.start_note(68, 0.5)
# time.sleep(1)
# piano.change_note_pitch(n, 70)
# time.sleep(1)
# piano.end_note(n)
# piano.play_note(72, 0.5, 1.5)
# time.sleep(1.5)
# piano.play_note(70, 0.5, 2)
# time.sleep(2.5)
# pc.stop_recording()

# pc.save_to_xml_file(name="bob.xml")

#
# voice = utilities.load_object("rec.pk")
voice = [PCNote(start_time=0.0, length=0.2, pitch=64, volume=0.5, variant=None),
         PCNote(start_time=0.25, length=0.2, pitch=64, volume=0.5, variant=None),
         PCNote(start_time=0.25, length=0.2, pitch=67, volume=0.5, variant=None),
         PCNote(start_time=0.25, length=0.2, pitch=72, volume=0.5, variant=None),
         PCNote(start_time=1.1, length=0.2, pitch=64, volume=0.5, variant=None),
         PCNote(start_time=1.1, length=0.7, pitch=64, volume=0.5, variant=None),
         PCNote(start_time=1.4, length=0.4, pitch=64, volume=0.5, variant=None),
         PCNote(start_time=1.8, length=0.2, pitch=64, volume=0.5, variant=None)]
# print BeatQuantizationScheme(60, 1.0, max_indigestibility=7, simplicity_preference=3).quantization_divisions
# print voice
# print "Start"
# Playcorder._collapse_recording_chords(voice)
# print "Stop"
# print "------------------------"

# LOOK INTO WHAT'S UP HERE: Seems like we need to be a little careful if start and end time are rounded to the start
# of the next beat. Should it disappear? Should it turn into a grace note?
print Playcorder._separate_into_non_overlapping_voices(
    Playcorder._collapse_recording_chords(
        Playcorder._quantize_recording(voice,
            [BeatQuantizationScheme(60, 1.0, max_indigestibility=7, simplicity_preference=0.1)]
        )
    ), 0.001
)
