__author__ = 'mpevans'

import subprocess
import socket
import OSC
import sys
import atexit
import time
import thread
import os
from marcpy.utilities import get_relative_file_path


_supercollider_process = None
_supercollider_listener = None
_py_to_supercollider_client = None


if getattr(sys, 'frozen', False):
    # running from a compiled application
    executable_path = get_relative_file_path("Resources/supercollider/sclang")
    sc_directory = get_relative_file_path("Resources/supercollider")
    sc_file_runner_path = get_relative_file_path("Resources/supercollider/FileRunner.scd")
else:
    # interpreted
    executable_path = get_relative_file_path("executable/sclang")
    sc_directory = get_relative_file_path("executable")
    sc_file_runner_path = get_relative_file_path("executable/FileRunner.scd")


def is_running():
    return _supercollider_process is not None


def _pick_unused_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    address, port = s.getsockname()
    s.close()
    return port


def kill_supercollider():
    global _supercollider_process, _supercollider_listener, _py_to_supercollider_client
    if _supercollider_process is not None:
        _supercollider_process.kill()
        _supercollider_process = None
        os.system("killall scsynth")
        # subprocess.call(["killall", "scsynth"])
    if _supercollider_listener is not None:
        _supercollider_listener.close()
        _supercollider_listener = None
    if _py_to_supercollider_client is not None:
        _py_to_supercollider_client.close()
        _py_to_supercollider_client = None

atexit.register(kill_supercollider)


def start_supercollider(callback_when_ready=None):
    if not is_running():
        global _supercollider_process, _supercollider_listener, \
            executable_path, sc_directory, sc_file_runner_path

        port = _pick_unused_port()
        _supercollider_listener = OSC.OSCServer(('127.0.0.1', port))
        _supercollider_listener.addDefaultHandlers()

        def sc_port_received(addr, tags, stuff, source):
            global _py_to_supercollider_client
            print "SuperCollider started and listening on port", stuff[0]
            _py_to_supercollider_client = OSC.OSCClient()
            _py_to_supercollider_client.connect(( '127.0.0.1', stuff[0] ))
            if callback_when_ready is not None:
                callback_when_ready()

        _supercollider_listener.addMsgHandler("/sendPort", sc_port_received)
        thread.start_new_thread(_supercollider_listener.serve_forever, ())

        _supercollider_process = subprocess.Popen([executable_path, "-d", sc_directory, sc_file_runner_path, str(port)])
    else:
        print "Tried to start supercollider, but it was already running"


def run_file(file_path):
    global _py_to_supercollider_client
    run_msg = OSC.OSCMessage()
    run_msg.setAddress("/run/file")
    run_msg.append(file_path)
    _py_to_supercollider_client.send(run_msg)


def run_code(code_string):
    global _py_to_supercollider_client
    run_msg = OSC.OSCMessage()
    run_msg.setAddress("/run/string")
    run_msg.append(code_string)
    _py_to_supercollider_client.send(run_msg)


def send_sc_message(address, data):
    global _py_to_supercollider_client
    the_msg = OSC.OSCMessage()
    for datum in data:
        the_msg.setAddress(address)
        the_msg.append(datum)
    _py_to_supercollider_client.send(the_msg)

# start_supercollider(callback_when_ready=lambda: run_file(get_relative_file_path("executable/Test.scd")))
