__author__ = 'mpevans'

from playcorder import *


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