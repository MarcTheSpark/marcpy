__author__ = 'mpevans'

import mido
import thread


def _listening_loop(port, message_handler_callback, note_message_callback, control_message_callback):
    for msg in port:
        if message_handler_callback is not None:
            message_handler_callback(msg)
        if note_message_callback is not None and (msg.type == "note_off" or msg.type == "note_on"):
            on_off = msg.type == "note_on"
            note_message_callback(msg.channel, on_off, msg.note, msg.velocity)
        if control_message_callback is not None and msg.type == "control_change":
            control_message_callback(msg.channel, msg.control, msg.value)


def start_listening(all_message_callback=None, note_message_callback=None, control_message_callback=None,
                    input_name=None):
    # CALLBACK FUNCTION FORMATS:
    #   all_message_callback(message)
    #   note_message_callback(channel, on_off, note, velocity)
    #   control_message_callback(channel, control, value)
    if input_name is None:
        port = mido.open_input()
    else:
        port = mido.open_input(input_name)
    thread.start_new_thread(_listening_loop,
                            (port, all_message_callback, note_message_callback, control_message_callback))