# coding=utf-8
import datetime
import logging
import os
import sys
from typing import Dict, Any

from flask import Flask, request, jsonify
import slack


log = logging.getLogger("slack_asterisk")
LOG_SPEC = "%(name)s[%(process)s]: %(filename)s:%(lineno)d/%(funcName)s###%(message)s"
stdout_formatter = logging.Formatter("%(asctime)s.%(msecs)06d" + " " + LOG_SPEC, datefmt='%Y-%m-%dT%T')

# configure a standard output handler with env-configurable level
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(stdout_formatter)


def _get_log_level_from_env() -> int:
    level_name = os.environ.get("LOG_LEVEL", os.environ.get("DEBUG_LEVEL", "INFO")).upper()
    return getattr(logging, level_name, logging.INFO)


stdout_handler.setLevel(_get_log_level_from_env())
log.addHandler(stdout_handler)
log.setLevel(_get_log_level_from_env())


class SlackAsteriskHTTP():  # pylint:disable=too-few-public-methods
    def __init__(self, slack_client, config):
        self.slack_client = slack_client
        self.config = config["slack"]
        self.calls_dict: Dict[str, Dict[str, Any]] = dict()

    def get_formatting(self, msg, msg_data, color="good"):
        actions = None
        if msg_data["direction"] == "out":
            title = "➡️ "
        else:
            title = "⬅️ "
        title += "Call from "
        title += msg_data["from_num"]
        if msg_data["from_name"] and msg_data["from_name"] != "anonymous":
            title += " (%s) " % msg_data["from_name"]

        footer = "Time: %s" % msg_data["ts_in"].strftime("%A %d.%m.%Y %H:%M:%S")
        if msg_data["dialedtime"] is not None:
            footer += " - Dialed for %s" % str(datetime.timedelta(seconds=msg_data["dialedtime"]))
        if msg_data["answeredtime"] is not None:
            footer += " - Answered for %s" % str(datetime.timedelta(seconds=msg_data["answeredtime"]))
        if msg_data["color"] is not None:
            color = msg_data["color"]
        if msg_data["type"] is not None:
            msg = "%s: %s" % (msg_data["type"], msg)
        data = dict(color=color, title=title, text=msg, username=self.config["username"], icon_emoji=self.config["emoji"], actions=actions, footer=footer)
        return data

    def update_message(self, msg, msg_data, color="good"):
        data = self.get_formatting(msg, msg_data, color)
        att = [data]
        log.debug("Channel update called for channel %s", self.config["channel"])
        ret = self.slack_client.chat_update(channel=msg_data["channel"], attachments=att, ts=msg_data["ts"])
        if ret["ok"] is not True:
            raise RuntimeError("Cannot post message with error %s" % ret["error"])

    def post_message(self, msg, msg_data, color="good"):
        data = self.get_formatting(msg, msg_data, color)
        att = [data]
        log.debug("Channel post called for channel %s", self.config["channel"])
        ret = self.slack_client.chat_postMessage(channel=self.config["channel"], attachments=att)

        if ret["ok"] is not True:
            raise RuntimeError("Cannot post message with error %s" % ret["error"])
        return ret["ts"], ret["channel"]

    @staticmethod
    def get_destination(msg_data):
        log.debug("get_destination called with msg_data %s", msg_data)
        dest = "Unknown"
        if msg_data["to_num"] is not None:
            dest = msg_data["to_num"]
        if msg_data["to_name"] is not None:
            dest = " (%s)" % msg_data["to_name"]
        log.debug("Destination results in %s", dest)
        return dest

    @staticmethod
    def get_dialedpeernumber(dp):
        num = None
        try:
            num = dp.split("/")[1]
        except Exception as e:
            log.debug("Error in parsing dialedpeernumber by / with msg %s", e)
        try:
            num = dp.split("@")[0]
        except Exception as e:
            log.debug("Error in parsing dialedpeernumber by @ with msg %s", e)
        log.debug("Dialed peer number %s leads to number %s", dp, num)
        return num

    def process_vars(self, channel_vars: Dict[str, Any]):  # pylint:disable=too-many-statements
        """Process variables received from Asterisk over HTTP."""
        log.debug("Received AGI variables: %s", channel_vars)

        try:
            new_call = False
            if "arg1" in channel_vars and channel_vars["arg1"] in self.calls_dict:
                # case Dial Macro, call completed
                msg_data = self.calls_dict[channel_vars["arg1"]]
            else:
                # all other cases
                if channel_vars.get("uniqueid") not in self.calls_dict:
                    self.calls_dict[channel_vars.get("uniqueid")] = dict(
                        ts=None, channel=None, from_num=None, from_name=None, to_num=None, to_name=None,
                        ts_in=datetime.datetime.now(), ts_connected=None, dialedtime=None, answeredtime=None,
                        info_text=None, color=None, type=None, direction=None
                    )
                    msg_data = self.calls_dict[channel_vars.get("uniqueid")]
                    if msg_data["from_num"] is None:
                        msg_data["from_num"] = channel_vars.get("callerid_num")
                    if msg_data["direction"] is None and channel_vars.get("direction") is not None:
                        msg_data["direction"] = channel_vars.get("direction")
                    else:
                        msg_data["direction"] = "in"
                    if channel_vars.get("callerid_name") is not None:
                        if channel_vars.get("callerid_name") != channel_vars.get("callerid_num"):
                            msg_data["from_name"] = channel_vars.get("callerid_name")
                    else:
                        msg_data["from_name"] = "anonymous"
                    if msg_data["to_num"] is None:
                        msg_data["to_num"] = channel_vars.get("exten")
                    new_call = True
                else:
                    msg_data = self.calls_dict[channel_vars.get("uniqueid")]

            if channel_vars.get("info_text") is not None:
                msg_data["info_text"] = channel_vars.get("info_text")
            if channel_vars.get("color") is not None:
                msg_data["color"] = channel_vars.get("color")
            if channel_vars.get("type") is not None:
                msg_data["type"] = channel_vars.get("type")

            if channel_vars.get("dialedtime") is not None:
                msg_data["dialedtime"] = int(channel_vars.get("dialedtime"))
            if channel_vars.get("answeredtime") is not None:
                msg_data["answeredtime"] = int(channel_vars.get("answeredtime"))

            if new_call is True:
                # this is a new detected call which is not in a macro
                log.debug("New call detected for uniqueid %s", channel_vars.get("uniqueid"))
                if msg_data["direction"] == "in":
                    text = "📞 Incoming call (ringing)"
                else:
                    text = "📞 Outgoing call (ringing) to %s" % channel_vars.get("exten")
                if msg_data["info_text"] is not None:
                    text += " (%s)" % msg_data["info_text"]
                (ts, channel) = self.post_message(text, msg_data)
                msg_data["ts"] = ts
                msg_data["channel"] = channel
            elif channel_vars.get("arg1") is not None:
                log.debug("Picked up call detected for uniqueid %s", channel_vars.get("uniqueid"))
                # this is a picked up call in a dial M macro
                if channel_vars.get("dialedpeernumber") is not None:
                    log.debug("Found dp number in channel vars %s", channel_vars)
                    msg_data["to_num"] = self.get_dialedpeernumber(channel_vars.get("dialedpeernumber"))
                else:
                    log.debug("No dialed peer number in channel vars %s", channel_vars)
                    if channel_vars.get("callerid_num") is not None:
                        msg_data["to_num"] = channel_vars.get("callerid_num")
                    if channel_vars.get("callerid_name") is not None:
                        msg_data["to_name"] = channel_vars.get("callerid_name")
                dest = self.get_destination(msg_data)
                self.update_message("☑️ Call established with %s" % dest, msg_data)
            elif channel_vars.get("dialstatus") is not None:
                log.debug("finished call detected for uniqueid %s", channel_vars.get("uniqueid"))
                dest = self.get_destination(msg_data)
                # set color to grey as default
                color = "#333333"
                # this is a finished call
                if channel_vars.get("dialstatus") == "ANSWER":
                    text = "✅ Call ended"
                    color = "good"
                elif channel_vars.get("dialstatus") == "BUSY":
                    text = "⭕ Busy"
                    color = "warning"
                elif channel_vars.get("dialstatus") == "NOANSWER":
                    text = "❌️ Not answered"
                    color = "warning"
                elif channel_vars.get("dialstatus") == "CANCEL":
                    text = "❌ Canceled"
                    color = "warning"
                elif channel_vars.get("dialstatus") == "CONGESTION":
                    text = "❌ Congestion"
                    color = "#9400D3"
                elif channel_vars.get("dialstatus") == "CHANUNAVAIL":
                    text = "❌ Channel unavailable"
                    color = "#9400D3"
                elif channel_vars.get("dialstatus") == "DONTCALL":
                    text = "❌ Reject (don't call)"
                    color = "#A9A9A9"
                elif channel_vars.get("dialstatus") == "TORTURE":
                    text = "❌ Reject (torture)"
                    color = "#A9A9A9"
                else:
                    text = "Unknown"
                if msg_data["direction"] == "in":
                    text += " from %s" % dest
                else:
                    text += " to %s" % dest
                self.update_message(text, msg_data, color=color)
            elif channel_vars.get("hangupcause") is not None and int(channel_vars.get("hangupcause")) > 0:
                dest = self.get_destination(msg_data)
                self.update_message("Call hung up by %s" % dest, msg_data)
            elif channel_vars.get("hangupcause") is not None and int(channel_vars.get("hangupcause")) <= 0:
                self.update_message("Unknown call state (hangupcause %i)" % int(channel_vars.get("hangupcause")), msg_data)
            else:
                self.update_message("Unknown call state", msg_data)
        except Exception as e:  # pylint:disable=broad-except
            log.exception("Exception occured with message %s", e)


def agi_server(ip, port, config):
    """Start a Flask server that replaces FastAGI.

    Exposes POST /agi to receive variables from Asterisk using CURL() or System(curl ...).
    """
    slack_token = os.environ["SLACK_TOKEN"]
    sc = slack.WebClient(slack_token)

    sa = SlackAsteriskHTTP(sc, config)

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])  # simple health endpoint
    def health():  # pylint:disable=unused-variable
        return jsonify({"status": "ok"})

    @app.route("/agi", methods=["POST"])  # main AGI endpoint
    def agi_endpoint():  # pylint:disable=unused-variable
        # Accept either JSON or application/x-www-form-urlencoded
        incoming: Dict[str, Any]
        if request.is_json:
            incoming = request.get_json(silent=True) or {}
        else:
            incoming = request.form.to_dict(flat=True)

        # Normalize keys to lowercase expected names
        normalized = {k.lower(): v for k, v in incoming.items()}

        # Debug log of received variables
        log.debug("Received AGI HTTP payload: %s", normalized)

        # Process
        sa.process_vars(normalized)
        return jsonify({"ok": True})

    # Run Flask dev server (Werkzeug). In production, use gunicorn or uwsgi.
    try:
        log.info("Starting Flask AGI server on %s:%s", ip, port)
        # Avoid Flask's own noisy logging if level > DEBUG
        werk_log = logging.getLogger('werkzeug')
        werk_log.setLevel(logging.WARNING)
        app.run(host=ip, port=port)
    except KeyboardInterrupt:  # pylint:disable=unused-variable
        log.info("Shutdown on ctrl-c")
        sys.exit(0)
    except Exception as e:  # pylint:disable=broad-except
        log.exception("Unknown Exception %s occured", e)
        sys.exit(1)
