# coding=utf-8
import socketserver
import datetime
import logging
import os
import sys

from slack_sdk import WebClient

log = logging.getLogger("slack_asterisk")
LOG_SPEC = "%(name)s[%(process)s]: %(filename)s:%(lineno)d/%(funcName)s###%(message)s"


def _configure_logging_from_env():
    level_name = os.getenv("LOG_LEVEL", os.getenv("DEBUG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = logging.Formatter("%(asctime)s.%(msecs)06d" + " " + LOG_SPEC, datefmt='%Y-%m-%dT%T')
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(fmt)
        h.setLevel(level)
        log.addHandler(h)
    log.setLevel(level)


_configure_logging_from_env()


class SlackAsterisk(socketserver.StreamRequestHandler):

    # --- Minimal built-in AGI helpers (replacing asterisk_agi) ---
    def _readline(self):
        """Read a single line from the socket, return str without CRLF or None."""
        data = b""
        try:
            while not data.endswith(b"\n"):
                chunk = self.request.recv(1)
                if not chunk:
                    break
                data += chunk
        except Exception as e:  # pragma: no cover
            log.debug("Error while reading line from socket: %s", e)
        if not data:
            return None
        return data.decode(errors="ignore").rstrip("\r\n")

    def _read_agi_env(self):
        """Read AGI environment lines until a blank line, return dict."""
        env = {}
        while True:
            line = self._readline()
            if line is None:
                break
            if line == "":
                break
            parts = line.split(":", 1)
            if len(parts) == 2:
                env[parts[0].strip()] = parts[1].strip()
        log.debug("AGI env: %s", env)
        return env

    def _send_cmd(self, cmd: str) -> str:
        """Send a raw AGI command and return the single-line reply."""
        log.debug("AGI >> %s", cmd)
        try:
            self.request.sendall((cmd + "\n").encode())
        except Exception as e:  # pragma: no cover
            log.debug("Error sending AGI command: %s", e)
        reply = self._readline() or ""
        log.debug("AGI << %s", reply)
        return reply

    def _set_var(self, name: str, value: str | None) -> None:
        if value is None:
            value = ""
        safe = value.replace('"', '\\"')
        self._send_cmd(f'SET VARIABLE {name} "{safe}"')

    def get_variable(self, name: str) -> str | None:
        """Get an Asterisk variable value via AGI.

        Parses typical responses like:
          200 result=1 (foo)
          200 result=0
        Returns the string value or None if not set.
        """
        reply = self._send_cmd(f"GET VARIABLE {name}")
        # Quick parse
        # Find result=
        result_pos = reply.find("result=")
        if result_pos == -1:
            return None
        try:
            after = reply[result_pos + len("result="):]
            # result may be like 1 (value) or 0
            # extract integer result
            res_str = ""
            i = 0
            while i < len(after) and after[i].isdigit():
                res_str += after[i]
                i += 1
            res = int(res_str) if res_str else 0
            if res == 0:
                return None
            # try to extract value inside parentheses
            lpar = reply.find("(")
            rpar = reply.rfind(")")
            if lpar != -1 and rpar != -1 and rpar > lpar:
                val = reply[lpar + 1:rpar]
                # Some asterisk versions wrap empty value as ""; normalize
                if val == '""':
                    return ""
                return val
            # sometimes value is quoted without parentheses in some impls
            return ""
        except Exception:  # pragma: no cover
            return None

    def get_vars(self):
        chan_vars = dict()
        chan_vars["callerid_num"] = self.get_variable('CALLERID(num)')
        chan_vars["callerid_name"] = self.get_variable('CALLERID(name)')
        chan_vars["uniqueid"] = self.get_variable('UNIQUEID')
        chan_vars["arg1"] = self.get_variable('ARG1')
        chan_vars["refid"] = self.get_variable('SLACK_ASTERISK_REFID')
        chan_vars["info_text"] = self.get_variable('SLACK_ASTERISK_INFO_TEXT')

        chan_vars["dialstatus"] = self.get_variable('DIALSTATUS')
        chan_vars["dialedpeername"] = self.get_variable('DIALEDPEERNAME')
        chan_vars["dialedpeernumber"] = self.get_variable('DIALEDPEERNUMBER')
        chan_vars["dialedtime"] = self.get_variable("DIALEDTIME")
        chan_vars["answeredtime"] = self.get_variable("ANSWEREDTIME")
        chan_vars["exten"] = self.get_variable('EXTEN')
        chan_vars["hangupcause"] = self.get_variable('HANGUPCAUSE')

        chan_vars["type"] = self.get_variable('SLACK_ASTERISK_TYPE')
        chan_vars["color"] = self.get_variable('SLACK_ASTERISK_COLOR')

        chan_vars["direction"] = self.get_variable('SLACK_ASTERISK_DIRECTION')

        to_delete = []
        for k, v in chan_vars.items():
            if not v:
                to_delete.append(k)
        for entry in to_delete:
            del chan_vars[entry]
        return chan_vars

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
        data = dict(color=color, title=title, text=msg, username=self.server.config["username"], icon_emoji=self.server.config["emoji"], actions=actions, footer=footer)
        return data

    def update_message(self, msg, msg_data, color="good"):
        data = self.get_formatting(msg, msg_data, color)
        att = [data]
        log.debug("Channel update called for channel %s", self.server.config["channel"])
        ret = self.server.slack_client.chat_update(channel=msg_data["channel"], attachments=att, ts=msg_data["ts"])
        if ret["ok"] is not True:
            raise RuntimeError("Cannot post message with error %s" % ret["error"])

    def post_message(self, msg, msg_data, color="good"):
        data = self.get_formatting(msg, msg_data, color)
        att = [data]
        log.debug("Channel post called for channel %s", self.server.config["channel"])
        ret = self.server.slack_client.chat_postMessage(channel=self.server.config["channel"], attachments=att)

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

    def handle(self):  # pylint:disable=too-many-statements
        log.debug("Received FastAGI request for client %s:%s", self.client_address[0], self.client_address[1])
        try:  # pylint:disable=too-many-nested-blocks
            # Read and log AGI environment
            _env = self._read_agi_env()
            # Collect channel vars using minimal GET VARIABLE calls
            channel_vars = self.get_vars()
            log.debug("FastAGI channel vars from %s:%s -> %s", self.client_address[0], self.client_address[1], channel_vars)

            new_call = False
            if "arg1" in channel_vars:
                # case Dial Macro, call completed
                msg_data = self.server.calls_dict[channel_vars["arg1"]]
            else:
                # all other cases
                if channel_vars["uniqueid"] not in self.server.calls_dict:
                    self.server.calls_dict[channel_vars["uniqueid"]] = dict(ts=None, channel=None, from_num=None, from_name=None, to_num=None, to_name=None, ts_in=datetime.datetime.now(), ts_connected=None, dialedtime=None, answeredtime=None, info_text=None, color=None, type=None, direction=None)
                    msg_data = self.server.calls_dict[channel_vars["uniqueid"]]
                    if msg_data["from_num"] is None:
                        msg_data["from_num"] = channel_vars["callerid_num"]
                    if msg_data["direction"] is None and "direction" in channel_vars:
                        msg_data["direction"] = channel_vars["direction"]
                    else:
                        msg_data["direction"] = "in"
                    if "callerid_name" in channel_vars:
                        if channel_vars["callerid_name"] != channel_vars["callerid_num"]:
                            msg_data["from_name"] = channel_vars["callerid_name"]
                    else:
                        msg_data["from_name"] = "anonymous"
                    if msg_data["to_num"] is None:
                        msg_data["to_num"] = channel_vars["exten"]
                    self._set_var("SLACK_ASTERISK_REFID", channel_vars["uniqueid"])
                    new_call = True
                else:
                    msg_data = self.server.calls_dict[channel_vars["uniqueid"]]

            if "info_text" in channel_vars:
                msg_data["info_text"] = channel_vars["info_text"]
            if "color" in channel_vars:
                msg_data["color"] = channel_vars["color"]
            if "type" in channel_vars:
                msg_data["type"] = channel_vars["type"]

            if "dialedtime" in channel_vars:
                msg_data["dialedtime"] = int(channel_vars["dialedtime"])
            if "answeredtime" in channel_vars:
                msg_data["answeredtime"] = int(channel_vars["answeredtime"])

            if new_call is True:
                # this is a new detected call which is not in a macro
                log.debug("New call detected for uniqueid %s", channel_vars["uniqueid"])
                if msg_data["direction"] == "in":
                    text = "📞 Incoming call (ringing)"
                else:
                    text = "📞 Outgoing call (ringing) to %s" % channel_vars["exten"]
                if msg_data["info_text"] is not None:
                    text += " (%s)" % msg_data["info_text"]
                (ts, channel) = self.post_message(text, msg_data)
                msg_data["ts"] = ts
                msg_data["channel"] = channel
            elif "arg1" in channel_vars:
                log.debug("Picked up call detected for uniqueid %s", channel_vars["uniqueid"])
                # this is a picked up call in a dial M macro
                if "dialedpeernumber" in channel_vars:
                    log.debug("Found dp number in channel vars %s", channel_vars)
                    msg_data["to_num"] = self.get_dialedpeernumber(channel_vars["dialedpeernumber"])
                else:
                    log.debug("No dialed peer number in channel vars %s", channel_vars)
                    if "callerid_num" in channel_vars:
                        msg_data["to_num"] = channel_vars["callerid_num"]
                    if "callerid_name" in channel_vars:
                        msg_data["to_name"] = channel_vars["callerid_name"]
                dest = self.get_destination(msg_data)
                self.update_message("☑️ Call established with %s" % dest, msg_data)
            elif "dialstatus" in channel_vars:
                log.debug("finished call detected for uniqueid %s", channel_vars["uniqueid"])
                dest = self.get_destination(msg_data)
                # set color to grey as default
                color = "#333333"
                # this is a finished call
                if channel_vars["dialstatus"] == "ANSWER":
                    text = "✅ Call ended"
                    color = "good"
                elif channel_vars["dialstatus"] == "BUSY":
                    text = "⭕ Busy"
                    color = "warning"
                elif channel_vars["dialstatus"] == "NOANSWER":
                    text = "❌️ Not answered"
                    color = "warning"
                elif channel_vars["dialstatus"] == "CANCEL":
                    text = "❌ Canceled"
                    color = "warning"
                elif channel_vars["dialstatus"] == "CONGESTION":
                    text = "❌ Congestion"
                    color = "#9400D3"
                elif channel_vars["dialstatus"] == "CHANUNAVAIL":
                    text = "❌ Channel unavailable"
                    color = "#9400D3"
                elif channel_vars["dialstatus"] == "DONTCALL":
                    text = "❌ Reject (don't call)"
                    color = "#A9A9A9"
                elif channel_vars["dialstatus"] == "TORTURE":
                    text = "❌ Reject (torture)"
                    color = "#A9A9A9"
                else:
                    text = "Unknown"
                if msg_data["direction"] == "in":
                    text += " from %s" % dest
                else:
                    text += " to %s" % dest
                self.update_message(text, msg_data, color=color)
            elif "hangupcause" in channel_vars and int(channel_vars["hangupcause"]) > 0:
                dest = self.get_destination(msg_data)
                self.update_message("Call hung up by %s" % dest, msg_data)
            elif "hangupcause" in channel_vars and int(channel_vars["hangupcause"]) <= 0:
                self.update_message("Unknown call state (hangupcause %i)" % int(channel_vars["hangupcause"]), msg_data)
            else:
                self.update_message("Unknown call state", msg_data)

        except Exception as e:
            log.exception("Exception occurred with message %s", e)


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):  # noqa: N803 (keep arg names per base class)
        # Predefine instance attributes to satisfy linters and clarify intent.
        self.slack_client = None  # type: ignore[assignment]
        self.config = {}          # type: ignore[assignment]
        self.calls_dict = {}
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)


def agi_server(ip, port, config):
    slack_token = os.environ["SLACK_TOKEN"]
    sc = WebClient(slack_token)

    ThreadedTCPServer.allow_reuse_address = True
    server = ThreadedTCPServer((ip, port), SlackAsterisk)
    server.slack_client = sc
    server.config = config["slack"]
    server.calls_dict = dict()

    try:
        log.debug("Server FastAGI on %s:%s", ip, port)
        server.serve_forever()
    except KeyboardInterrupt as e:  # pylint:disable=unused-variable
        log.info("Shutdown on ctrl-c")
        sys.exit(0)
    except Exception as e:
        log.exception("Unknown Exception %s occurred", e)
        sys.exit(1)
