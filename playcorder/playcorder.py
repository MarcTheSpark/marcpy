__author__ = 'mpevans'

from fractions import Fraction

import localfluidsynth
from marcpy.chuck.chuck import *
from MidiFile import MIDIFile
from MeasuresBeatsNotes import *
import RecordingToXML
from threading import Event


# TODO: SOMETHING GOES WRONG WHEN THERE ARE LIKE 3 STAVES, and they get disconnected
# TODO: SPECIFY MAX VOICES PER STAFF
# TODO: SPECIFY MOST APPROPRIATE CLEF FOR EACH STAFF OF EACH MEASURE
# TODO: DON'T SPLIT RESTS IN EMPTY VOICE INTO TUPLETS

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
            instrument.recording.append(MPNote(start_time=note_start_time,
                                               length=length if written_length is None else written_length,
                                               pitch=pitch, volume=volume, variant=variant_dictionary, tie=None))

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
        time.sleep(seconds)
        if self.time_passed is not None:
            self.time_passed += seconds

    # used for a situation where time is recorded manually, but there may be multiple threads,
    # only one of which registers time passed.
    def register_time_passed(self, seconds):
        if self.time_passed is not None:
            self.time_passed += seconds

    # ---------------------------------------- SAVING TO XML ----------------------------------------------

    def save_to_xml_file(self, file_name, measure_schemes=None, time_signature="4/4", tempo=60, max_divisions=8,
                         max_indigestibility=4, simplicity_preference=0.2, title=None, composer=None,
                         separate_voices_in_separate_staves=True, show_cent_values=True, add_sibelius_pitch_bend=True):

        part_recordings = [this_part.recording for this_part in self.parts_recorded]
        part_names = [this_part.name for this_part in self.parts_recorded]
        RecordingToXML.save_to_xml_file(part_recordings, part_names, file_name, measure_schemes=measure_schemes,
                                        time_signature=time_signature, tempo=tempo, max_divisions=max_divisions,
                                        max_indigestibility=max_indigestibility,
                                        simplicity_preference=simplicity_preference, title=title, composer=composer,
                                        separate_voices_in_separate_staves=separate_voices_in_separate_staves,
                                        show_cent_values=show_cent_values, add_sibelius_pitch_bend=add_sibelius_pitch_bend)


    # ---------------------------------------- SAVING TO MIDI ----------------------------------------------

    @staticmethod
    def get_good_tempo_choice(pc_note_list, max_tempo=200, max_tempo_to_divide_to=300, goal_tempo=80):
        min_beat_length = 60.0 / max_tempo_to_divide_to
        total_length = max([(pc_note.start_time + pc_note.length) for pc_note in pc_note_list])
        divisor = 1

        best_beat_length = None
        best_error = float("inf")
        while total_length / divisor >= min_beat_length:
            beat_length = total_length / divisor
            total_squared_error = 0.0
            for pc_note in pc_note_list:
                total_squared_error += \
                    (pc_note.start_time - utilities.round_to_multiple(pc_note.start_time, beat_length/4.0)) ** 2

            total_squared_error *= (abs((60.0/beat_length) - goal_tempo)/50 + 1.0)
            if total_squared_error < best_error:
                best_error = total_squared_error
                best_beat_length = beat_length
            divisor += 1

        best_tempo = 60 / best_beat_length
        while best_tempo > max_tempo:
            best_tempo /= 2
        return best_tempo

    def save_to_midi_file(self, path, tempo=60, beat_length=1.0, max_beat_divisions=8, max_indigestibility=4,
                          beat_max_overlap=0.01, quantization_divisions=None, quantize=True, round_pitches=True,
                          guess_tempo=False):
        if guess_tempo:
            flattened_recording = utilities.make_flat_list(
                [part.recording for part in self.parts_recorded]
            )
            tempo = Playcorder.get_good_tempo_choice(flattened_recording)

        if quantize:
            beat_scheme = BeatQuantizationScheme(tempo, beat_length, max_beat_divisions, max_indigestibility) \
                if quantization_divisions is None \
                else BeatQuantizationScheme(tempo, beat_length, quantization_divisions=quantization_divisions)
            parts = [RecordingToXML.separate_into_non_overlapping_voices(
                RecordingToXML.quantize_recording(
                    part.recording, [beat_scheme])[0],
                beat_max_overlap
            ) for part in self.parts_recorded]
        else:
            parts = [RecordingToXML.separate_into_non_overlapping_voices(
                part.recording, beat_max_overlap
            ) for part in self.parts_recorded]

        midi_file = MIDIFile(sum([len(x) for x in parts]))

        current_track = 0
        for which_part, part in enumerate(parts):
            current_voice = 0
            for voice in part:
                midi_file.addTrackName(current_track, 0, self.parts_recorded[which_part].name + " " + str(current_voice + 1))
                midi_file.addTempo(current_track, 0, tempo)

                for pc_note in voice:
                    assert isinstance(pc_note, MPNote)
                    pitch_to_notate = int(round(pc_note.pitch)) if round_pitches else pc_note.pitch
                    midi_file.addNote(current_track, 0, pitch_to_notate, pc_note.start_time,
                                      pc_note.length, int(pc_note.volume*127))
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
        self.render_info = {}

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

    def play_note(self, pitch, volume, length, start_delay=0, variant_dictionary=None, play_length=None):
        thread.start_new_thread(self._do_play_note, (pitch, volume, length if play_length is None else play_length,
                                                     start_delay, variant_dictionary))

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
#
# piano = pc.add_midi_part((0, 0), "Piano")
# guitar = pc.add_midi_part((0, 27), "Guitar")
#
# pc.start_recording([piano, guitar], manual_time=True)
#
# import random
# for i in range(15):
#     l = random.random()*1.5+0.1
#     random.choice([piano, guitar]).play_note(50 + random.random()*20, 0.5, l)
#     pc.wait(l+random.random()*1.5)
#
# pc.stop_recording()
#
# pc.save_to_xml_file(file_name="bob.xml", time_signature="5/4", tempo=120, max_divisions=6)