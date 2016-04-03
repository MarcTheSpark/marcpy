__author__ = 'mpevans'

import localfluidsynth
import time
import thread
from collections import namedtuple
from marcpy.chuck.chuck import *
from marcpy import utilities
from music21 import converter
from music21 import musicxml
from music21 import *
from music21.stream import Voice, Part, Score
from music21.note import Note, Rest
from music21.pitch import Pitch
from music21.tempo import MetronomeMark
from xml.etree.ElementTree import ElementTree

# n = note.Note()
# n.pitch.midi = 60
# n.quarterLength = .49
# s = stream.Stream()
# s.repeatInsert(n, [0.1, .49, .9])
# nshort = note.Note()
# nshort.quarterLength = .26
# nshort.pitch.midi = 67
# s.repeatInsert(nshort, [1.49, 1.76])
# s.quantize([4], processOffsets=True, processDurations=True, inPlace=True)
# print [e.offset for e in s]
# print [e.duration.quarterLength for e in s]
#
# GEX = musicxml.m21ToXml.GeneralObjectExporter()
# SX = musicxml.m21ToXml.ScoreExporter(GEX.fromGeneralObject(s))
# mxScore = SX.parse()
# from xml.etree.ElementTree import ElementTree
# ElementTree(mxScore).write("Butts.xml")


_articulation_locations = {
    "staccato": "end",
    "staccatissimo": "end",
    "accent": "start",
    "marcato": "start"
}

PCNote = namedtuple("PCNote", "start_time length pitch volume variant")

class Playcorder:

    def __init__(self, soundfont_path=None, channels_per_part=50):
        self.channels_per_part = channels_per_part
        self.used_channels = 0
        self.fs = None
        self.sfid = None
        if soundfont_path is not None:
            if soundfont_path == "default":
                soundfont_path = get_relative_file_path("LiteSoundFont.sf2")
            self.initialize_fluidsynth(soundfont_path)
        self.instruments = []
        # RECORDING STUFF
        # parts_being_recorded is a list of parts being recorded if recording otherwise it's None
        self.parts_being_recorded = None
        # once recording stops parts_recorded stores the parts that were recorded
        self.parts_recorded = None
        # recording_start_time is used if using time.time() as time
        # time_passed is used if manually recording time
        self.recording_start_time = None
        self.time_passed = None

        self.instrument_list = None
        if soundfont_path is not None:
            from sf2utils.sf2parse import Sf2File
            with open(soundfont_path, "rb") as sf2_file:
                sf2 = Sf2File(sf2_file)
                self.instrument_list = sf2.presets

    def initialize_fluidsynth(self, soundfont_path):
        self.fs = localfluidsynth.Synth()
        self.sfid = self.fs.sfload(soundfont_path)
        self.fs.start()

    def get_instruments_with_substring(self, word):
        if self.instrument_list is None:
            return None
        return [inst for i, inst in enumerate(self.instrument_list) if word.lower() in inst.name.lower()]

    def add_part(self, inst_num, name=None):
        """

        :rtype : FSPlaycorderInstrument
        """
        if self.fs is None:
            raise Exception("fluidsynth not initialized")
        if name is None:
            name = "Track " + str(len(self.instruments) + 1)

        if isinstance(inst_num, int):
            # if just an int, assume bank 0 and that's the preset
            instrument = FSPlaycorderInstrument(self.fs, self.sfid, inst_num, self.used_channels, self.channels_per_part, self, name, bank=0)
        else:
            # inst_num is a bank, preset pair
            instrument = FSPlaycorderInstrument(self.fs, self.sfid, inst_num[1], self.used_channels, self.channels_per_part, self, name, inst_num[0])
        self.instruments.append(instrument)
        self.used_channels += self.channels_per_part
        return instrument

    def add_chuck_part(self, file_path, osc_message_address, args=[], name=None):
        """

        :rtype : ChuckPlaycorderInstrument
        """
        if name is None:
            name = "Track " + str(len(self.instruments) + 1)
        instrument = ChuckPlaycorderInstrument(file_path, osc_message_address, args, self, name)
        self.instruments.append(instrument)
        return instrument

    def add_chuck_multisample_player(self, path_dictionary, name=None, default_length_response=None, pan=0):
        """

        :rtype : ChuckMultiSamplePlayer
        """
        if name is None:
            name = "Track " + str(len(self.instruments) + 1)
        instrument = ChuckMultiSamplePlayer(path_dictionary, self, name,
                                            default_length_response=default_length_response, pan=pan)
        self.instruments.append(instrument)
        return instrument

    def add_silent_part(self, name=None):
        """

        :rtype : SilentPlaycorderInstrument
        """
        if name is None:
            name = "Track " + str(len(self.instruments) + 1)
        instrument = SilentPlaycorderInstrument(self, name=name)
        self.instruments.append(instrument)
        return instrument

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

    # Make this a save to MIDI, and give options for the search tree
    def save_to_xml_file(self, tempo=60, time_signature="4/4", max_overlap=0.01, name=None, quantization_divisions=(4,)):
        # print "saving output..."
        # staff_groups = []

        # scale the note lengths up by this factor, since we recorded them in seconds, not beats
        tempo_scaling_factor = tempo/60.0
        m21Score = Score()
        for i, part in enumerate(self.parts_recorded):
            print "Working on Part " + str(i+1) + "..."
            voices = self._separate_part_recording_into_voice_streams(part.recording, tempo, time_signature, max_overlap)
            m21Part = Part()
            for voice in voices:
                m21Voice = Voice()
                # current_beat = 0
                for pcnote in voice:
                    assert isinstance(pcnote, PCNote)
                    scaled_start_time = pcnote.start_time*tempo_scaling_factor
                    note_beat_length = pcnote.length * tempo_scaling_factor
                    # if scaled_start_time > current_beat:
                    #     # there is a gap so we need a rest
                    #     m21Voice.append(Rest(quarterLength=scaled_start_time - current_beat))
                    #     # then we can advance time to the start of the note
                    #     current_beat = scaled_start_time
                    the_note = Note(Pitch(pcnote.pitch), quarterLength=note_beat_length)
                    m21Voice.insert(scaled_start_time, the_note)
                    # current_beat += note_beat_length
                m21Voice.quantize(quantization_divisions, processOffsets=True, processDurations=True, inPlace=True)
                index_rest_insertion_pairs = []
                new_m21Voice = Voice()
                current_beat = 0

                for m21Note in m21Voice:
                    if m21Note.offset > current_beat:
                        new_m21Voice.append(Rest(quarterLength = m21Note.offset - current_beat))
                        current_beat += m21Note.offset - current_beat
                    new_m21Voice.append(m21Note)
                    current_beat += m21Note.quarterLength
                m21Part.insert(0, meter.TimeSignature(time_signature))
                m21Part.insert(0, new_m21Voice)
            m21Score.insert(0, m21Part)
        m21Score.insert(MetronomeMark(number=tempo))
        GEX = musicxml.m21ToXml.GeneralObjectExporter()
        SX = musicxml.m21ToXml.ScoreExporter(GEX.fromGeneralObject(m21Score))
        mxScore = SX.parse()

        ElementTree(mxScore).write(name)
        #     show(Staff(voices))
        #     if voices is not None:
        #         staff_group = StaffGroup()
        #         staff_group.extend(voices)
        #         staff_groups.append(staff_group)



    def _separate_part_recording_into_voice_streams(self, recording, tempo, time_signature, max_overlap):

        assert isinstance(recording, list)
        recording.sort(key=lambda note: note.start_time)
        voices = []
        for note in recording:
            # find the first non-conflicting voices
            voice_to_add_to = None
            for voice in voices:
                if len(voice) == 0:
                    voice_to_add_to = voice
                    break
                else:
                    voice_end_time = voice[-1].start_time + voice[-1].length
                    if voice_end_time - note.start_time < max_overlap:
                        voice_to_add_to = voice
                        break
            if voice_to_add_to is None:
                voice_to_add_to = []
                voices.append(voice_to_add_to)
            voice_to_add_to.append(note)

        if len(voices) == 0:
            return None

        return voices

    # used for a situation where all parts are played from a single thread
    def wait(self, seconds):
        self.time_passed += seconds
        time.sleep(seconds)

    # used for a situation where time is recorded manually, but there may be multiple threads,
    # only one of which registers time passed.
    def register_time_passed(self, seconds):
        self.time_passed += seconds

class FSPlaycorderInstrument:

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


class ChuckPlaycorderInstrument:

    def __init__(self, file_path, osc_message_address, args=[], host_playcorder=None, name=None):
        assert isinstance(host_playcorder, Playcorder) or host_playcorder is None
        self.host_playcorder = host_playcorder
        self.osc_message_address = osc_message_address
        self.name = name
        self.chuck_instrument = ChuckInstrument(file_path, args)

    def play_note(self, pitch, volume, length, start_delay=0, variant="norm"):
        self.chuck_instrument.send_message(self.osc_message_address, [float(pitch), float(volume),
                                                                      float(length), float(start_delay)])
        if self.host_playcorder:
            self.host_playcorder.record_note(self, pitch, volume, length, start_delay, variant=variant)


class SilentPlaycorderInstrument:

    def __init__(self, host_playcorder=None, name=None):
        assert isinstance(host_playcorder, Playcorder) or host_playcorder is None
        self.host_playcorder = host_playcorder
        self.name = name

    def play_note(self, pitch, volume, length, start_delay=0, variant="norm", text_annotation=None):
        if self.host_playcorder:
            self.host_playcorder.record_note(self, pitch, volume, length, start_delay,
                                             variant=variant, text_annotation=text_annotation)


class ChuckMultiSamplePlayer:

    """ example path dictionary"
    {
        60: "some simple path",
        62: {
            # Timpani Edge
            "[(a)W]{staccato}": utilities.get_relative_file_path('HitSamples/TimpaniWoodMalletEdgeHandDamped.wav'),
            "[(a)F]{staccato}": utilities.get_relative_file_path('HitSamples/TimpaniFingerHandDampenedCenter.wav'),
            "[(a)F] trem !lr3!": utilities.get_relative_file_path('RollSamples/H22_HighTimpaniFingerRollEdge.wav')
        },
        64: {
            # Timpani Normal
            "Large trem": utilities.get_relative_file_path('RollSamples/H2_TimpRoll.wav'),
            "Small trem": utilities.get_relative_file_path('RollSamples/H4_SmallTimpRoll.wav'),
            "[(a)Th.] trem": [utilities.get_relative_file_path('RollSamples/H8_HighTimpThumbRoll_1.wav'),
                              utilities.get_relative_file_path('RollSamples/H8_LowTimpThumbRoll_1.wav'),
                              utilities.get_relative_file_path('RollSamples/H8_HighTimpThumbRoll_2.wav'),
                              utilities.get_relative_file_path('RollSamples/H8_LowTimpThumbRoll_2.wav'),
                              utilities.get_relative_file_path('RollSamples/H8_HighTimpThumbRoll_3.wav'),
                              utilities.get_relative_file_path('RollSamples/H8_LowTimpThumbRoll_3.wav')]

        },
    }
    !lr3! means length response - different ways of cutting a sound short if the length is short.
    The default, lr0, means it's not cut short at all.
    """
    def __init__(self, path_dictionary={}, host_playcorder=None, name=None, default_length_response=None, pan=0):
        assert isinstance(host_playcorder, Playcorder) or host_playcorder is None
        self.host_playcorder = host_playcorder
        self.osc_message_address = "/play_sample"
        self.name = name

        chuck_args = []
        if default_length_response is not None and 0 <= int(default_length_response) <= 3 :
            chuck_args.append("lr" + str(int(default_length_response)))

        if pan != 0 and -1 <= pan <= 1:
            chuck_args.append("pan" + str(pan))

        for midi_note in path_dictionary:
            if isinstance(path_dictionary[midi_note], str):
                chuck_args.extend([midi_note, "norm", path_dictionary[midi_note]])
            elif isinstance(path_dictionary[midi_note], list) or isinstance(path_dictionary[midi_note], tuple):
                chuck_args.extend([midi_note, "norm"])
                chuck_args.extend(path_dictionary[midi_note])
            elif isinstance(path_dictionary[midi_note], dict):
                for variant in path_dictionary[midi_note]:
                    lr_strings = utilities.get_bracketed_text(variant, "!", "!")
                    if isinstance(path_dictionary[midi_note][variant], str):
                        chuck_args.extend([midi_note, variant, path_dictionary[midi_note][variant]])
                    elif isinstance(path_dictionary[midi_note][variant], list) or \
                            isinstance(path_dictionary[midi_note][variant], tuple):
                        chuck_args.extend([midi_note, variant])
                        chuck_args.extend(path_dictionary[midi_note][variant])
                    if len(lr_strings) > 0:
                        chuck_args.append(lr_strings[0])

        self.path_dictionary = path_dictionary
        self.chuck_instrument = ChuckInstrument(get_relative_file_path("MultiSamplePlayer.ck"), chuck_args)

    def play_note_thread(self, pitch, variant, volume, length, start_delay):
        time.sleep(start_delay)
        self.chuck_instrument.send_message(self.osc_message_address, [int(pitch), variant, float(volume),
                                                                              float(length), float(start_delay)])

    def play_note(self, pitch, volume, length, start_delay=0, variant="norm", text_annotation=None, written_length=None):
        # check that it's playable before sending it to the dangerous chuck player:
        if pitch in self.path_dictionary:
            if (not isinstance(self.path_dictionary[pitch], dict) and variant == "norm")\
                    or variant in self.path_dictionary[pitch]:
                # it's playable
                thread.start_new_thread(self.play_note_thread, (pitch, variant, volume, length, start_delay))

        if self.host_playcorder:
            self.host_playcorder.record_note(self, pitch, volume, length if written_length is None else written_length,
                                             start_delay=start_delay, variant=variant, text_annotation=text_annotation)


# manual_recorder = Playcorder()
# note_noter = manual_recorder.add_silent_part("piano")
# manual_recorder.start_recording([note_noter], manual_time=True)
# for _ in range(10):
#     note_noter.play_note(67, 0.6, 1.0)
#     manual_recorder.register_time_passed(1.0)
#     note_noter.play_note(60, 0.6, 1.0)
#     manual_recorder.register_time_passed(1.5)
#     note_noter.play_note(63, 0.6, 0.5)
#     manual_recorder.register_time_passed(0.5)
#
# manual_recorder.stop_recording()
# manual_recorder.save_to_xml_file(60, "3/4", name="Butts.xml", quantization_divisions=(4))