var pythonPort = thisProcess.argv[0].asInteger;
PyCom.setPyNetAddress(NetAddr.new( NetAddr.localAddr.hostname, pythonPort ));

s.waitForBoot({
	PyCom.send("/sendPort", NetAddr.langPort);
	PyCom.receive('/run/file', { |time, responder, msg| msg[1].asString.load; });
	PyCom.receive('/run/string', { |time, responder, msg| msg[1].asString.interpret; });
});