# slack_asterisk

This is an Asterisk → Slack integration that logs incoming and outgoing phone calls, including call progress.
It posts an initial message when a call starts and updates it as the call progresses.

Starting with this version, the project runs a Flask HTTP server rather than a FastAGI TCP server. Asterisk should
send the relevant channel variables to the Flask endpoint using `CURL()` or `System(curl ...)` instead of `AGI()`.

![Slack Asterisk example](slack_asterisk_example.png?raw=true "Example Output")

## Requirements

 * Python 3.x
 * configobj
 * slackclient
 * Flask

For a Python 2.7 version see release tag 0.10.
 
## Installation

Use:

`python3 setup.py install`

or build a rpm using the provided RPM spec file (tested using CentOS 7). 
Also a SystemD Unit file is provided, which allows starting and stopping of the HTTP service.

## Configuration

You will need a Slack API Token to be able to post messages to Slack. Create a Slack API Token with the proper
permissions and put the token into an environment variable before starting the daemon. In addition you can use
a config file in /etc/slack-asterisk.conf to override the default values.

Start using Slack Token from environment:

```
export SLACK_TOKEN=xoxb....
/usr/bin/slack-asterisk
```

The provided SystemD Unit file will read the Slack Token from /etc/slack-asterisk.token.

You can also configure the log level via `LOG_LEVEL` (or `DEBUG_LEVEL`) environment variables. Valid values are the
standard Python logging levels like `DEBUG`, `INFO`, `WARNING`, `ERROR`.

### Asterisk dialplan (HTTP via CURL)

Once the service is running, update the dialplan to POST the relevant variables to the Flask endpoint.
Below are examples using `CURL()` to post `application/x-www-form-urlencoded` to `http://127.0.0.1:4574/agi`.

Note: adjust the list of variables to suit your environment. The server accepts both JSON and form-encoded payloads
and logs all received variables at DEBUG level.

```
; Helper to URL-encode values (Asterisk 16+ often provides URIENCODE())
; If not available, keep values simple (digits) or use System(curl ...).

; Incoming call (ringing)
exten => _X.,1,NoOp(Incoming call)
 same => n,Set(_HTTP_BODY=callerid_num=${CALLERID(num)}&callerid_name=${CALLERID(name)}&uniqueid=${UNIQUEID}&exten=${EXTEN}&direction=in)
 same => n,Set(_curl_res=${CURL(http://127.0.0.1:4574/agi,${HTTP_BODY})})

; After Dial() returns, report final status
 same => n,Dial(SIP/FIXME,120,trM(slack-answered^${UNIQUEID}))
 same => n,Set(_HTTP_BODY=uniqueid=${UNIQUEID}&dialstatus=${DIALSTATUS})
 same => n,Set(_curl_res=${CURL(http://127.0.0.1:4574/agi,${HTTP_BODY})})

; Hangup handler (optional)
exten => h,1,NoOp(Hangup cause)
 same => n,Set(_HTTP_BODY=uniqueid=${UNIQUEID}&hangupcause=${HANGUPCAUSE})
 same => n,Set(_curl_res=${CURL(http://127.0.0.1:4574/agi,${HTTP_BODY})})

; Macro called when call is answered (from Dial trM)
[macro-slack-answered]
exten => s,1,NoOp(macro slack-answered called)
 same => n,Set(_HTTP_BODY=arg1=${ARG1}&callerid_num=${CALLERID(num)}&callerid_name=${CALLERID(name)}&dialedpeernumber=${DIALEDPEERNUMBER})
 same => n,Set(_curl_res=${CURL(http://127.0.0.1:4574/agi,${HTTP_BODY})})
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

### Notes

- Logging level is controlled via `LOG_LEVEL` (or `DEBUG_LEVEL`) environment variables. Example: `LOG_LEVEL=DEBUG`.
- The Flask app exposes a simple health endpoint on `GET /health` returning `{ "status": "ok" }`.
- The deprecated FastAGI mode and `asterisk_agi.py` library are no longer used.
