__author__ = 'mpevans'

from playcorder import *


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