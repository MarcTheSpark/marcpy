__author__ = 'mpevans'

import localfluidsynth
import time
import thread
from collections import namedtuple
from marcpy.chuck.chuck import *
from marcpy import utilities
from music21 import converter
from music21 import musicxml
from music21.stream import Voice, Part, Score
from music21.note import Note, Rest
from music21.pitch import Pitch
from music21.tempo import MetronomeMark
from music21.meter import TimeSignature
from xml.etree.ElementTree import ElementTree


PCNote = namedtuple("PCNote", "start_time length pitch volume variant")


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
        if not hasattr(instrument, "name") or instrument.name is None:
            instrument.name = "Track " + str(len(self.instruments) + 1)
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
            instrument = MidiPlaycorderInstrument(self.synth, self.soundfont_id, preset, self.used_channels,
                                                  self.channels_per_part, self, name, bank=0)
        else:
            # inst_num is a bank, preset pair
            instrument = MidiPlaycorderInstrument(self.synth, self.soundfont_id, preset[1], self.used_channels,
                                                  self.channels_per_part, self, name, preset[0])

        self.used_channels += self.channels_per_part
        self.add_part(instrument)
        return instrument

    def add_silent_part(self, name=None):
        """
        Constructs a SilentPlaycorderInstrument, adds it to the Playcorder, and returns it
        :rtype : SilentPlaycorderInstrument
        """
        name = "Track " + str(len(self.instruments) + 1) if name is None else name
        instrument = SilentPlaycorderInstrument(self, name=name)
        self.add_part(instrument)
        return instrument


    # ----------------------------------- Recording ----------------------------------

    def record_note(self, instrument, pitch, volume, length, start_delay=0,
                    variant="norm", text_annotation=None, start_time=None, written_length=None):
        if self.parts_being_recorded is not None and instrument in self.parts_being_recorded:
            if start_time is not None:
                note_start_time = start_time
            else:
                note_start_time = self.get_time_passed() + start_delay
            recorded_variant = variant if text_annotation is None else variant + "[" + text_annotation + "]"
            instrument.recording.append(PCNote(start_time=note_start_time,
                                               length=length if written_length is None else written_length,
                                               pitch=pitch, volume=volume, variant=recorded_variant))

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
        self.parts_recorded = self.parts_being_recorded
        self.parts_being_recorded = None
        self.time_passed = None
        self.recording_start_time = None

    # used for a situation where all parts are played from a single thread
    def wait(self, seconds):
        self.time_passed += seconds
        time.sleep(seconds)

    # used for a situation where time is recorded manually, but there may be multiple threads,
    # only one of which registers time passed.
    def register_time_passed(self, seconds):
        self.time_passed += seconds

    # ----------------------------------- Saving Output ----------------------------------

    # Make this a save to MIDI, and give options for the search tree
    def save_to_xml_file(self, tempo=60, time_signature="4/4", max_overlap=0.01, name=None, quantization_divisions=(4,)):
        print "Saving Output..."

        # scale the note lengths up by this factor, since we recorded them in seconds, not beats
        tempo_scaling_factor = tempo/60.0
        m21_score = Score()
        for i, part in enumerate(self.parts_recorded):
            print "Working on Part " + str(i+1) + "..."
            voices = Playcorder._separate_part_recording_into_voice_streams(part.recording, max_overlap)
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

    @staticmethod
    def _separate_part_recording_into_voice_streams(recording, max_overlap):
        # takes a recording of PCNotes and breaks it up into separate voices that don't overlap more than max_overlap
        assert isinstance(recording, list)
        recording.sort(key=lambda note: note.start_time)
        voices = []
        for pc_note in recording:
            # find the first non-conflicting voices
            voice_to_add_to = None
            for voice in voices:
                if len(voice) == 0:
                    voice_to_add_to = voice
                    break
                else:
                    voice_end_time = voice[-1].start_time + voice[-1].length
                    if voice_end_time - pc_note.start_time < max_overlap:
                        voice_to_add_to = voice
                        break
            if voice_to_add_to is None:
                voice_to_add_to = []
                voices.append(voice_to_add_to)
            voice_to_add_to.append(pc_note)

        return voices


class MidiPlaycorderInstrument:

    def __init__(self, fs, sfid, inst_num, start_channel, num_channels, host_playcorder=None, name=None, bank=0):
        assert isinstance(fs, localfluidsynth.Synth)
        assert isinstance(host_playcorder, Playcorder)
        self.host_playcorder = host_playcorder
        self.fs = fs
        for i in range(start_channel, start_channel + num_channels):
            fs.program_select(i, sfid, bank, inst_num)
        self.chan = 0
        self.start_channel = start_channel
        self.num_channels = num_channels
        self.name = name
        # each entry goes (pitch, volume, start_time)
        self.notes_started = []

    def play_note_thread(self, pitch, volume, length, start_delay):
        chan = self.start_channel + self.chan
        self.chan = (self.chan + 1) % self.num_channels
        int_pitch = int(round(pitch))
        pitch_bend_val = int((pitch - int_pitch)*2048)
        self.fs.pitch_bend(chan, pitch_bend_val)
        time.sleep(start_delay)
        self.fs.noteon(chan, int_pitch, int(volume*127))
        time.sleep(length)
        self.fs.noteon(chan, int_pitch, 0)

    def play_note(self, pitch, volume, length, start_delay=0, variant="norm"):
        thread.start_new_thread(self.play_note_thread, (pitch, volume, length, start_delay))
        if self.host_playcorder and self.host_playcorder.recording_start_time is not None:
            self.host_playcorder.record_note(self, pitch, volume, length, start_delay, variant=variant)

    def start_note(self, pitch, volume):
        chan = self.start_channel + self.chan
        self.chan = (self.chan + 1) % self.num_channels
        int_pitch = int(round(pitch))
        pitch_bend_val = int((pitch - int_pitch)*2048)
        self.fs.pitch_bend(chan, pitch_bend_val)
        self.fs.noteon(chan, int_pitch, int(volume*127))
        self.notes_started.append((chan, pitch, volume, self.host_playcorder.get_time_passed()))
        # returns the channel as a reference, in case we want to start and stop a bunch of these
        return chan

    def set_pitch_bend(self, cents, chan=None):
        if chan is None:
            chan = self.start_channel + self.chan -1
        pitch_bend_val = int(cents/100.0*2048)
        self.fs.pitch_bend(chan, pitch_bend_val)

    def end_note(self, chan=None):
        if chan is not None:
            note_to_end = None
            for started_note in self.notes_started:
                if started_note[0] == chan:
                    note_to_end = started_note
                    break
            self.notes_started.remove(note_to_end)
        else:
            note_to_end = self.notes_started.pop(0)
        if note_to_end is None:
            return
        chan, pitch, volume, start_time = note_to_end
        self.fs.noteon(chan, int(pitch), 0)
        if start_time is not None and self.host_playcorder.get_time_passed() is not None:
            self.host_playcorder.record_note(self, pitch, volume, self.host_playcorder.get_time_passed()-start_time,
                                             start_time=start_time)

    def end_all_notes(self):
        while len(self.notes_started) > 0:
            self.end_note()

    def num_notes_playing(self):
        return len(self.notes_started)


class SilentPlaycorderInstrument:

    def __init__(self, host_playcorder=None, name=None):
        assert isinstance(host_playcorder, Playcorder) or host_playcorder is None
        self.host_playcorder = host_playcorder
        self.name = name

    def play_note(self, pitch, volume, length, start_delay=0, variant="norm", text_annotation=None):
        if self.host_playcorder:
            self.host_playcorder.record_note(self, pitch, volume, length, start_delay,
                                             variant=variant, text_annotation=text_annotation)


# -------------- EXAMPLE --------------
# pc = Playcorder(soundfont_path="default")
# piano = pc.add_midi_part(0)
#
# pc.start_recording([piano])
# piano.play_note(68, 0.5, 2)
# time.sleep(2)
# piano.play_note(72, 0.5, 1.5)
# time.sleep(1.5)
# piano.play_note(70, 0.5, 2)
# time.sleep(2.5)
# pc.stop_recording()
# pc.save_to_xml_file(name="bob.xml")
