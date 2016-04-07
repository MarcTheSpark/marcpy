class HardLimit extends Chugen {
    1 => float limit;
    fun float tick(float in) {
        Math.min(Math.max(in, -limit), limit) => float limited;
        //if(limited != in) {<<<"clipping!">>>;}
        return limited;
    }
    fun float setLimit(float limit) {
        limit => this.limit;
    }
}

Pan2 panner => HardLimit h => dac;
0 => panner.pan;

//60:norm:bob:frank:72:norm:flog:72:pizz:dood:fudge

0 => int i;
OscRecv recv;
Std.atoi(me.arg(i)) => recv.port;
i++;

0 => int default_length_response;
if (me.arg(i).substring(0, 2) == "lr") {
    Std.atoi(me.arg(i).substring(2)) => default_length_response;
    i++;
}

if (me.arg(i).length() >= 3 && me.arg(i).substring(0, 3) == "pan") {
    Std.atof(me.arg(i).substring(3)) => panner.pan;
    i++;
}

//arg structure is pitch:variant:path1:path2:etc. repeat
string pathFinder[0];
int numVersionsFinder[0];
int currentVersionFinder[0];
// a lengthResponseMode of 0 means it plays full length no matter what
// a lengthResponseMode of 1 means it trims length from the end and adds a fade out that lasts the minimum of half the
//     play length and the amount trimmed off the end
// a lengthResponseMode of 2 means it trims length from the beginning and adds a fade in that lasts the minimum of half
//     the play length and the amount trimmed off the beginning
// a lengthResponseMode of 3 means it trims length equally from the both sides and adds a fade in and a fade out that
//     last the minimum of a quarter the play length and the amount trimmed of start and finish
int lengthResponseMode[0];
while(i<me.args()) {
    me.arg(i) => string pitch;
    i++;
    me.arg(i) => string variant;
    i++;
    0 => int numVersions;
    
    default_length_response => lengthResponseMode[pitch + variant];
    while(i<me.args() && Std.atoi(me.arg(i)) == 0) {
        if(me.arg(i).substring(0, 2) == "lr") {
            //"lr" sets the length response type to 0, 1, 2, or 3
            Std.atoi(me.arg(i).substring(2)) => lengthResponseMode[pitch + variant];
        } else {
            me.arg(i) => pathFinder[pitch + variant + numVersions];
            numVersions++;
        }
        i++;
    }
    numVersions => numVersionsFinder[pitch + variant];
    0 => currentVersionFinder[pitch + variant];
}

<<<"Locked and Loaded">>>;
// start listening (launch thread)
recv.listen();

// create a player with the given name
recv.event( "/play_sample, i, s, f, f, f" ) @=> OscEvent @ playEvent;

while( true )
{
    // wait for event to arrive
    playEvent => now;
    
    // grab the next message from the queue. 
    while( playEvent.nextMsg() )
    {
        playEvent.getInt() => int midi;
        playEvent.getString() => string variant;
        playEvent.getFloat() => float gain;
        playEvent.getFloat() => float length;
        playEvent.getFloat() => float startDelay;
        <<<midi, variant,  length, gain>>>;
        spork ~ playSample( midi, variant, length, gain );
    }
}

fun dur minDur(dur dur1, dur dur2) {
    if (dur1 < dur2) {
        return dur1;
    } else {
        return dur2;
    }
}

fun void playSample(int midi, string variant, float length, float gain) {
    SndBuf s;
    HardLimit h;
    h.setLimit(3);
    midi + variant => string searchString;
    pathFinder[midi + variant + currentVersionFinder[searchString]] => string path;
    (currentVersionFinder[searchString] + 1) % numVersionsFinder[searchString] => currentVersionFinder[searchString];
    path => s.read;
    gain => s.gain;
    length::second => dur durLength;
    if(durLength < s.length() && lengthResponseMode[searchString] != 0) {
        s.length() - durLength => dur clippedLength;
        if(lengthResponseMode[searchString] == 1) {
            //shorten from the end
            minDur(clippedLength, durLength/2) => dur fadeOutLength;
            s => Envelope e => panner;
            1 => e.value;
            (durLength - fadeOutLength) => now;
            fadeOutLength => e.duration;
            e.keyOff();
            fadeOutLength => now;
        } else if (lengthResponseMode[searchString] == 2) {
            //shorten from the start
            minDur(clippedLength, durLength/2) => dur fadeInLength;
            s => Envelope e => panner;
            (clippedLength/samp) $ int => s.pos;
            0 => e.value;
            e.keyOn();
            fadeInLength => e.duration;
            fadeInLength => now;
            (durLength - fadeInLength) => now;
        } else if (lengthResponseMode[searchString] == 3) {
            //shorten from the middle: so as to keep the middle in the right place
            minDur(clippedLength/2, durLength/4) => dur fadeLength;
            s => Envelope e => panner;
            (clippedLength/2/samp) $ int => s.pos;
            0 => e.value;
            e.keyOn();
            fadeLength => e.duration;
            (durLength - fadeLength) => now;
            e.keyOff();
            fadeLength => now;
        }
    } else if (lengthResponseMode[searchString] != 0) {
        (durLength - s.length()) / 2 => now;
        s => panner;
        s.length() => now;
        (durLength - s.length()) / 2 => now;
    } else {
        s => panner;
        s.length() => now;
    }
}