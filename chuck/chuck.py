__author__ = 'mpevans'

import subprocess
import OSC
import thread
import time
import atexit
from marcpy.utilities import get_relative_file_path
import sys
import socket

next_osc_port = 59120

class ChuckInstrument:
    def __init__(self, file_path, args=[], buf_size=512):
        self.process = None
        self.client = None
        self.do_chuck_process(file_path, args, buf_size)
        atexit.register(self.kill_process)

    def do_chuck_process(self, file_path, args=[], buf_size=512):
        global next_osc_port
        launch_string = file_path+":"+str(next_osc_port)

        buf_size_string = "--bufsize" + str(buf_size)

        for arg in args:
            launch_string += ":"+str(arg)
        if getattr(sys, 'frozen', False):
            self.process = subprocess.Popen([get_relative_file_path("Resources/chuck"), buf_size_string, launch_string])
        else:
            self.process = subprocess.Popen(["chuck", buf_size_string, launch_string])
        self.client = OSC.OSCClient()
        self.client.connect(( '127.0.0.1', next_osc_port ))
        next_osc_port += 1

    def send_message(self, message_address, message):
        assert isinstance(message_address, str)
        msg = OSC.OSCMessage()
        msg.setAddress(message_address)
        msg.append(message)
        self.client.send(msg)

    def kill_process(self):
        self.process.kill()

next_receiver_port = 11027

class ChuckTimer:
    def __init__(self, tick_function, interval):
        self.tick_function = tick_function
        self.interval = interval
        self.process = None
        self.time_passed = 0.0
        self.server = None

    def start_timer(self, separate_thread=False):
        global next_receiver_port

        # Find open address and launch OSC Server to listen
        successful_address = False
        while not successful_address:
            try:
                self.server = OSC.OSCServer(('127.0.0.1', next_receiver_port))
                self.server.addDefaultHandlers()
                print "port", next_receiver_port, "connected for chuck timer listening"
                successful_address = True
            except socket.error:
                print "port", next_receiver_port, "failed"
                next_receiver_port += 1


        launch_string = get_relative_file_path("ChuckSynchronizer.ck")+":"+str(next_receiver_port)+":"+str(self.interval)
        self.process = subprocess.Popen(["chuck", launch_string])

        def tick(addr, tags, stuff, source):
            self.tick_function(self.time_passed)
            self.time_passed += self.interval

        self.server.addMsgHandler("/tick", tick) #OSC client automatically sends sample rate data, just routing to do mostly nothing

        next_receiver_port += 1
        atexit.register(self.stop_timer)
        if separate_thread:
            thread.start_new_thread(self.server.serve_forever, ())
        else:
            self.server.serve_forever()

    def stop_timer(self):
        if self.process is not None:
            self.process.kill()
            self.server.close()

