fork {
	SynthDef("pinkWobble", { |wobbleFreq=0.5|
		Out.ar(0, Pan2.ar(PinkNoise.ar(0.2), SinOsc.kr(wobbleFreq)));
	}).add;

	s.sync;

	~wobble = Synth.new("pinkWobble");
};

PyCom.receive("setWobbleFrequency", { |time, node, msg|
    // msg[0] is just the name of the message
	~wobble.set("wobbleFreq", msg[1]);
	PyCom.send("/chatter", "I can talk back too!");
});