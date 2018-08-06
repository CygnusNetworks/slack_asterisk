# coding=utf-8
import argparse
import datetime
import logging
import os
import SocketServer
import sys

import asterisk.agi
import slackclient
#import phonenumbers

from . import config
from . import __version__

log = logging.getLogger("slack_asterisk")
log.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
log.addHandler(ch)


class SlackAsterisk(SocketServer.StreamRequestHandler, SocketServer.ThreadingMixIn, object):
	def get_vars(self, agi):
		vars = dict()
		vars["callerid_num"] = agi.get_variable('CALLERID(num)')
		vars["callerid_name"] = agi.get_variable('CALLERID(name)')
		vars["uniqueid"] = agi.get_variable('UNIQUEID')
		vars["arg1"] = agi.get_variable('ARG1')
		vars["dialstatus"] = agi.get_variable('DIALSTATUS')
		vars["dialedpeername"] = agi.get_variable('DIALEDPEERNAME')
		vars["dialedpeernumber"] = agi.get_variable('DIALEDPEERNUMBER')
		vars["dialedtime"] = agi.get_variable("DIALEDTIME")
		vars["answeredtime"] = agi.get_variable("ANSWEREDTIME")
		vars["exten"] = agi.get_variable('EXTEN')
		to_delete = []
		for k, v in vars.items():
			if len(v) == 0:
				to_delete.append(k)
		for entry in to_delete:
			del vars[entry]
		return vars

	def get_formatting(self, msg, msg_data, color="good"):
		#actions = [dict(type="button", text="Bla", url="http://w359.de")]
		actions = None
		title = ""
		title += msg_data["from_num"]
		if msg_data["from_name"] is not None:
			title += " (%s) " % msg_data["from_name"]
		title += "=>"
		title += msg_data["to_num"]
		if msg_data["to_name"] is not None:
			title += " (%s) " % msg_data["to_name"]
		footer = "Time: %s" % msg_data["ts_in"].strftime("%A %d.%m.%Y %H:%M:%S")
		if msg_data["dialedtime"] is not None:
			footer += " - Dialed for %s" % str(datetime.timedelta(seconds=msg_data["dialedtime"]))
		if msg_data["answeredtime"] is not None:
			footer += " - Answered for %s" % str(datetime.timedelta(seconds=msg_data["answeredtime"]))
		data = dict(color=color, title=title, text=msg, username="Cygnus PBX", icon_emoji=":telephone_receiver:", actions=actions, footer=footer)
		return data

	def update_message(self, msg, msg_data, color="good"):
		data = self.get_formatting(msg, msg_data, color)
		att = [data]
		log.debug("Channel update called for channel %s", self.server.slack_channel)
		method = "chat.update"
		ret = self.server.slack_client.api_call(method, channel=msg_data["channel"], attachments=att, ts=msg_data["ts"])
		if ret["ok"] is not True:
			raise RuntimeError("Cannot post message with error %s" % ret["error"])

	def post_message(self, msg, msg_data, color="good"):
		data = self.get_formatting(msg, msg_data, color)
		att = [data]
		log.debug("Channel post called for channel %s", self.server.slack_channel)
		method = "chat.postMessage"
		ret = self.server.slack_client.api_call(method, channel=self.server.slack_channel, attachments=att)

		if ret["ok"] is not True:
			raise RuntimeError("Cannot post message with error %s" % ret["error"])
		else:
			return (ret["ts"], ret["channel"])

	def handle(self):
		sc = self.server.slack_client
		log.debug("Received FastAGI request for client %s:%s", self.client_address[0], self.client_address[1])
		try:
			devnull = open(os.devnull, 'w')
			agi = asterisk.agi.AGI(self.rfile, self.wfile, devnull)
			vars = self.get_vars(agi)
			log.debug("FastAGI request for client %s:%s for %s", self.client_address[0], self.client_address[1], str(vars))

			if "arg1" in vars:
				# case Dial Macro, call completed
				msg_data = self.server.calls_dict[vars["arg1"]]
			else:
				# all other cases
				if vars["uniqueid"] not in self.server.calls_dict:
					self.server.calls_dict[vars["uniqueid"]] = dict(ts=None, channel=None, from_num=None, from_name=None, to_num=None, to_name=None, ts_in=datetime.datetime.now(), ts_connected=None, dialedtime=None, answeredtime=None)
				msg_data = self.server.calls_dict[vars["uniqueid"]]
				if msg_data["from_num"] is None:
					msg_data["from_num"] = vars["callerid_num"]
					msg_data["from_name"] = vars["callerid_name"]
					msg_data["to_num"] = vars["exten"]
			if "dialedtime" in vars:
				msg_data["dialedtime"] = int(vars["dialedtime"])
			if "answeredtime" in vars:
				msg_data["answeredtime"] = int(vars["answeredtime"])

			if "uniqueid" in vars and "arg1" not in vars and "dialstatus" not in vars:
				# this is a new detected call which is not in a macro
				log.debug("New call detected for uniqueid %s", vars["uniqueid"])
				(ts, channel) = self.post_message("Incoming call (ringing)", msg_data)
				msg_data["ts"] = ts
				msg_data["channel"] = channel

			elif "arg1" in vars:
				log.debug("Picked up call detected for uniqueid %s", vars["uniqueid"])
				# this is a picked up call in a dial M macro
				msg_data["to_name"] = vars["callerid_name"]
				msg_data["to_num"] = vars["callerid_num"]
				self.update_message("Call established", msg_data)
			elif "dialstatus" in vars:
				log.debug("finished call detected for uniqueid %s", vars["uniqueid"])
				# this is a finished call
				if vars["dialstatus"] == "ANSWER":
					text = "Call accepted and finished"
					color = "good"
				elif vars["dialstatus"] == "BUSY":
					text = "Busy"
					color = "warning"
				elif vars["dialstatus"] == "NOANSWER":
					text = "Not answered"
					color = "warning"
				elif vars["dialstatus"] == "CANCEL":
					text = "Canceled"
					color = "warning"
				elif vars["dialstatus"] == "CONGESTION":
					text = "Congestion"
					color = "#9400D3"
				elif vars["dialstatus"] == "CHANUNAVAIL":
					text = "Channel unavailable"
					color = "#9400D3"
				elif vars["dialstatus"] == "DONTCALL":
					text = "Reject (don't call)"
					color = "#A9A9A9"
				elif vars["dialstatus"] == "TORTURE":
					text = "Reject (torture)"
					color = "#A9A9A9"
				else:
					text = "Unknown"
				self.update_message(text, msg_data, color=color)
		except Exception as e:
			del agi
			log.exception("Exception occured with mesage %s", e)
		finally:
			devnull.close()


def main():
	argp = argparse.ArgumentParser()
	argp.add_argument("-i", "--ip", help="Set bind ip for FastAGI", default=None)
	argp.add_argument("-p", "--port", help="Set bind port for FastAGI", type=int, default=None)

	args = argp.parse_args()  # pylint: disable=W0612

	conf = config.SlackAsteriskConfig()
	c = conf.get_configobj()

	if args.ip is not None:
		ip = args.ip
	else:
		ip = c["general"]["ip"]

	if args.port is not None:
		port = args.port
	else:
		port = c["general"]["port"]

	# FIXME: add oauth
	if "SLACK_TOKEN" in os.environ:
		slack_token = os.environ["SLACK_TOKEN"]
		sc = slackclient.SlackClient(slack_token)
	else:
		raise RuntimeError("oauth not yet implemented")

	SocketServer.TCPServer.allow_reuse_address = True
	server = SocketServer.TCPServer((ip, port), SlackAsterisk)
	server.slack_client = sc
	server.slack_channel = c["slack"]["channel"]
	server.calls_dict = dict()

	log.info("slack_asterisk version %s starting", __version__)

	server.config = c
	try:
		log.debug("Server FastAGI on %s:%s", ip, port)
		server.serve_forever()
	except KeyboardInterrupt as e:
		log.info("Shutdown on ctrl-c")
		sys.exit(0)
	except Exception as e:
		log.exception("Unknown Exception %s occured", e)
		sys.exit(1)


if __name__ == "__main__":
	main()
