# slack_asterisk

This is a Asterisk Slack Integration, which provides logging of incoming and outgoing phone calls including call progress. 
It will post a initial message on the first call and updates this on call progress.
It is implemented as a Asterisk FastAGI server (listening on local socket port 4574).

![Slack Asterisk example](slack_asterisk_example.png?raw=true "Example Output")

## Requirements

 * Python 2.7
 * configobj
 * pyst
 * slackclient
 * falcon
 
## Installation

Use:

`python setup.py install`

or build a rpm using the provided RPM spec file (tested using CentOS 7). 
Also a SystemD Unit file is provided, which allows starting and stopping of the FastAGI service.

## Configuration

You will need a Slack API Token to be able to post messages to Slack. Create a Slack API Token with the proper 
permissions and put the token into a environment variable, before starting the daemon. In addition you can use
a config file in /etc/slack-asterisk.conf to override the default values.

Start using Slack Token from environment:

```
export SLACK_TOKEN=xoxb....
/usr/bin/slack-asterisk
```

The provided SystemD Unit file will read the Slack Token from /etc/slack-asterisk.token.

### Asterisk extensions

Once the service is running, you need to have the FastAGI included in your extensions. Be sure to included 
all incoming and outgoing dials and all call states. 

```
; incoming call extension
same => n,AGI(agi://127.0.0.1:4574/)
same => n,Dial(SIP/FIXME,120,trM(slack-answered^${UNIQUEID})) ; Macro see below

...
; congestion, hangup, ... call states
exten => congestion,1,Noop(Congestion called)
same => next,AGI(agi://127.0.0.1:4574/)
same => next,Goto(noanswer,1)

exten => chanunavail,1,Noop(Channel unavailable called)
same => next,AGI(agi://127.0.0.1:4574/)
same => next,Goto(noanswer,1)

exten => h,1,Noop(Channel hangup called)
same => next,AGI(agi://127.0.0.1:4574/)

exten => noanswer,1,Set(GREETING=u)
same => next,Goto(leave-voicemail,${EXTEN},1)

exten => busy,1,Set(GREETING=b)
same => next,AGI(agi://127.0.0.1:4574/)
same => next,Goto(leave-voicemail,${EXTEN},1)
```

In additon define the Macro given below, to catch answered calls.

```
[macro-slack-answered]
exten => s,1,Noop(macro slack-answered called)
same => next,AGI(agi://127.0.0.1:4574/)
```

### Config file

Config file options are the following (defaults are given):

```
[general]
ip = 127.0.0.1
port = 4574

[slack]
client_id = ""
client_secret = ""
channel = "telefon"

username = "User"
emoji  = ":telephone_receiver:"
```
