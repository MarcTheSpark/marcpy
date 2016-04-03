__author__ = 'mpevans'

import localfluidsynth
import time
import thread
from MidiFile import MIDIFile
from collections import namedtuple
from marcpy.chuck.chuck import *

PCNote = namedtuple("PCNote", "start_time length pitch volume")

class Playcorder:

    def __init__(self, soundfont_path=None, channels_per_part=50):
        self.channels_per_part = channels_per_part
        self.used_channels = 0
        self.fs = None
        self.sfid = None
        if soundfont_path is not None:
            self.initialize_fluidsynth(soundfont_path)
        self.instruments = []
        self.recording_start_time = None
        self.which_parts = None
        self.score = None
        self.part_names = None
        self.time_passed = None

    def initialize_fluidsynth(self, soundfont_path):
        self.fs = localfluidsynth.Synth()
        self.sfid = self.fs.sfload(soundfont_path)
        self.fs.start()

    def add_part(self, inst_num, name=None):
        """

        :rtype : FSPlaycorderInstrument
        """
        if self.fs is None:
            raise Exception("fluidsynth not initialized")
        instrument = FSPlaycorderInstrument(self.fs, self.sfid, inst_num, self.used_channels, self.channels_per_part, self, name)
        self.instruments.append(instrument)
        self.used_channels += self.channels_per_part
        return instrument

    def add_chuck_part(self, file_path, osc_message_address, args=[], name=None):
        """

        :rtype : ChuckPlaycorderInstrument
        """
        instrument = ChuckPlaycorderInstrument(file_path, osc_message_address, args, self, name)
        self.instruments.append(instrument)
        return instrument

    def play_note(self, instrument, pitch, volume, length, start_delay=0):
        # instrument can be a reference to the instrument itself or an int representing its number
        if isinstance(instrument, int):
            instrument = self.instruments[instrument]
        instrument.play_note(pitch, volume, length, start_delay)

    def record_note(self, instrument, pitch, volume, length, start_delay=0, start_time=None):
        if self.recording_start_time is not None:
            score_part_num = self.which_parts.index(instrument)
            if start_time is not None:
                note_start_time = start_time
            else:
                note_start_time = self.get_time_passed() + start_delay
            self.score[score_part_num].append(PCNote(start_time=note_start_time, length=length,
                                                     pitch=pitch, volume=volume))

    def get_time_passed(self):
        if self.recording_start_time is None:
            return None
        if self.time_passed is None:
            # not manually logging time; just measure from the start time
           return time.time()-self.recording_start_time
        else:
            # manually logging time, so use time_passed
            return self.time_passed

    def start_recording(self, which_parts=None, manual_time=False):
        self.recording_start_time = time.time()
        if manual_time:
            self.time_passed = 0
        else:
            self.time_passed = None
        self.which_parts = self.instruments if which_parts is None else which_parts
        self.score = []
        self.part_names = []
        for i, part in enumerate(self.which_parts):
            self.score.append([])
            if part.name is None:
                self.part_names.append("Track " + str(i))
            else:
                self.part_names.append(part.name)

    def stop_recording(self):
        self.recording_start_time = None
        self.which_parts = None

    def split_parts_into_voices(self):
        voiced_parts = []
        for part in self.score:
            voices = []
            i = 0
            while i < len(part):
                this_note = part[i]
                max_deviation = this_note.length / 100.0
                # find the first non-overlapping voice
                voice_to_add_to = None
                for voice in voices:
                    if voice[-1].start_time + voice[-1].length < this_note.start_time + max_deviation:
                        voice_to_add_to = voice
                        break
                if voice_to_add_to is None:
                    voice_to_add_to = []
                    voices.append(voice_to_add_to)
                voice_to_add_to.append(this_note)

                # now see if any of the notes following are almost exactly the same start time
                # and length (indicating a chord that should be all in one voice)
                i += 1
                while i < len(part):
                    next_note = part[i]
                    if abs(next_note.start_time - this_note.start_time) < max_deviation and \
                                    abs(next_note.length - this_note.length) < max_deviation:
                        voice_to_add_to.append(next_note)
                        i += 1
                    else:
                        break
            voiced_parts.append(voices)
        return voiced_parts

    def save_to_midi_file(self, path, tempo=60, separate_voices=False):
        if self.score is None:
            return
        voiced_parts = self.split_parts_into_voices()
        if separate_voices:
            part_names = []
            for pnum, part in enumerate(voiced_parts):
                for voice in part:
                    part_names.append(self.part_names[pnum])
            new_voiced_parts = []
            for part in voiced_parts:
                for voice in part:
                    new_voiced_parts.append([voice])
            voiced_parts = new_voiced_parts
        else:
            part_names = self.part_names

        midi_file = MIDIFile(len(voiced_parts))

        for part_num, voiced_part in enumerate(voiced_parts):
            print part_num, voiced_part
            midi_file.addTrackName(part_num, 0, part_names[part_num])
            midi_file.addTempo(part_num, 0, tempo)

            for v, voice in enumerate(voiced_part):
                for note in voice:
                    assert isinstance(note, PCNote)
                    start_time = note.start_time*tempo/60.0
                    length = note.length*tempo/60.0
                    int_pitch = int(note.pitch)
                    volume = min(int(note.volume*127), 127)
                    midi_file.addNote(part_num, v, int_pitch, start_time, length, volume)

        binfile = open(path, 'wb')
        midi_file.writeFile(binfile)
        binfile.close()

    def wait(self, seconds):
        self.time_passed += seconds
        time.sleep(seconds)

    def register_time_passed(self, seconds):
        self.time_passed += seconds

class FSPlaycorderInstrument:

    def __init__(self, fs, sfid, inst_num, start_channel, num_channels, host_playcorder=None, name=None):
        assert isinstance(fs, localfluidsynth.Synth)
        assert isinstance(host_playcorder, Playcorder)
        self.host_playcorder = host_playcorder
        self.fs = fs
        for i in range(start_channel, start_channel + num_channels):
            fs.program_select(i, sfid, 0, inst_num)
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

    def play_note(self, pitch, volume, length, start_delay=0):
        thread.start_new_thread(self.play_note_thread, (pitch, volume, length, start_delay))
        if self.host_playcorder and self.host_playcorder.recording_start_time is not None:
            self.host_playcorder.record_note(self, pitch, volume, length, start_delay)

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
        assert isinstance(host_playcorder, Playcorder)
        self.host_playcorder = host_playcorder
        self.osc_message_address = osc_message_address
        self.name = name
        self.chuck_instrument = ChuckInstrument(file_path, args)

    def play_note(self, pitch, volume, length, start_delay=0):
        self.chuck_instrument.send_message(self.osc_message_address, [float(pitch), float(volume),
                                                                      float(length), float(start_delay)])
        if self.host_playcorder:
            self.host_playcorder.record_note(self, pitch, volume, length, start_delay)
