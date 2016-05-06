This folder contains my implementation of OSC communication between python and Supercollider.

The "executable" folder contains an old version of supercollider (the reason being that the old version did not contain the large QT library). A better approach would be to compile a newer version of supercollider without qt, but somehow that kept failing on my computer. Anyway, the class library has one custom class called "PyCom" used in the supercollider code for setting up responders to OSC messages coming from python (and sending messages if desired).

"supercollider.py" contains the python implementation. A short example at the end of that file opens supercollider, runs "Test.scd", and does some basic communication with the synth.

Hopefully it's pretty self-explanatory.

