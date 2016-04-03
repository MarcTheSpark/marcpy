//ARGS: port, tick period (seconds)

// host name and port
"localhost" => string hostname;
8000 => int port;
1.0 => float tickPeriodInSeconds;

// get command line
if( me.args() ) me.arg(0) => Std.atoi => port;
if( me.args() > 1 ) me.arg(1) => Std.atof => tickPeriodInSeconds;

// send object
OscSend xmit;

// aim the transmitter
xmit.setHost( hostname, port );

// infinite time loop
while( true )
{
    // start the message...
    xmit.startMsg( "/tick");
    
    // advance time
    tickPeriodInSeconds::second => now;
}