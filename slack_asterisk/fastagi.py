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
ch = logging.StreamHandler(sys.stdout)
log.addHandler(ch)


class SlackAsterisk(SocketServer.StreamRequestHandler, SocketServer.ThreadingMixIn, object):
	@staticmethod
	def get_vars(agi):
		chan_vars = dict()
		chan_vars["callerid_num"] = agi.get_variable('CALLERID(num)')
		chan_vars["callerid_name"] = agi.get_variable('CALLERID(name)')
		chan_vars["uniqueid"] = agi.get_variable('UNIQUEID')
		chan_vars["arg1"] = agi.get_variable('ARG1')
		chan_vars["refid"] = agi.get_variable('SLACK_ASTERISK_REFID')

		chan_vars["dialstatus"] = agi.get_variable('DIALSTATUS')
		chan_vars["dialedpeername"] = agi.get_variable('DIALEDPEERNAME')
		chan_vars["dialedpeernumber"] = agi.get_variable('DIALEDPEERNUMBER')
		chan_vars["dialedtime"] = agi.get_variable("DIALEDTIME")
		chan_vars["answeredtime"] = agi.get_variable("ANSWEREDTIME")
		chan_vars["exten"] = agi.get_variable('EXTEN')
		chan_vars["hangupcause"] = agi.get_variable('HANGUPCAUSE')

		chan_vars["type"] = agi.get_variable('SLACK_ASTERISK_TYPE')
		chan_vars["color"] = agi.get_variable('SLACK_ASTERISK_COLOR')

		chan_vars["direction"] = agi.get_variable('SLACK_ASTERISK_DIRECTION')

		to_delete = []
		for k, v in chan_vars.items():
			if len(v) == 0:
				to_delete.append(k)
		for entry in to_delete:
			del chan_vars[entry]
		return chan_vars

	def get_formatting(self, msg, msg_data, color="good"):
		actions = None
		title = "Call from "
		title += msg_data["from_num"]
		if msg_data["from_name"] is not None:
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
		method = "chat.update"
		ret = self.server.slack_client.api_call(method, channel=msg_data["channel"], attachments=att, ts=msg_data["ts"])
		if ret["ok"] is not True:
			raise RuntimeError("Cannot post message with error %s" % ret["error"])

	def post_message(self, msg, msg_data, color="good"):
		data = self.get_formatting(msg, msg_data, color)
		att = [data]
		log.debug("Channel post called for channel %s", self.server.config["channel"])
		method = "chat.postMessage"
		ret = self.server.slack_client.api_call(method, channel=self.server.config["channel"], attachments=att)

		if ret["ok"] is not True:
			raise RuntimeError("Cannot post message with error %s" % ret["error"])
		else:
			return ret["ts"], ret["channel"]

	def get_destination(self, msg_data):
		log.debug("get_destination called with msg_data %s", msg_data)
		dest = "Unknown"
		if msg_data["to_num"] is not None:
			dest = msg_data["to_num"]
		if msg_data["to_name"] is not None:
			dest += " (%s)" % msg_data["to_name"]
		log.debug("Destination results in %s", dest)
		return dest

	def get_dialedpeernumber(self, dp):
		num = None
		try:
			num = dp.split("/")[1]
		except:
			log.debug("Error in parsing dialedpeernumber by /")
		try:
			num = dp.split("@")[0]
		except:
			log.debug("Error in parsing dialedpeernumber by @")
		log.debug("Dialed peer number %s leads to number %s", dp, num)
		return num

	def handle(self):  # pylint:disable=too-many-statements
		log.debug("Received FastAGI request for client %s:%s", self.client_address[0], self.client_address[1])
		try:
			devnull = open(os.devnull, 'w')
			agi = asterisk.agi.AGI(self.rfile, self.wfile, devnull)
			channel_vars = self.get_vars(agi)
			log.debug("FastAGI request for client %s:%s for %s", self.client_address[0], self.client_address[1], str(channel_vars))

			new_call = False
			if "arg1" in channel_vars:
				# case Dial Macro, call completed
				msg_data = self.server.calls_dict[channel_vars["arg1"]]
			else:
				# all other cases
				if channel_vars["uniqueid"] not in self.server.calls_dict:
					self.server.calls_dict[channel_vars["uniqueid"]] = dict(ts=None, channel=None, from_num=None, from_name=None, to_num=None, to_name=None, ts_in=datetime.datetime.now(), ts_connected=None, dialedtime=None, answeredtime=None, color=None, type=None, direction=None)
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
					agi.set_variable("SLACK_ASTERISK_REFID", channel_vars["uniqueid"])
					new_call = True
				else:
					msg_data = self.server.calls_dict[channel_vars["uniqueid"]]

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
					text = "Incoming call (ringing)"
				else:
					text = "Outgoing call (ringing) to %s" % channel_vars["exten"]
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
				self.update_message("Call established with %s" % dest, msg_data)
			elif "dialstatus" in channel_vars:
				log.debug("finished call detected for uniqueid %s", channel_vars["uniqueid"])
				dest = self.get_destination(msg_data)
				# this is a finished call
				if channel_vars["dialstatus"] == "ANSWER":
					text = "Call accepted and finished by %s" % dest
					color = "good"
				elif channel_vars["dialstatus"] == "BUSY":
					text = "Busy"
					color = "warning"
				elif channel_vars["dialstatus"] == "NOANSWER":
					text = "Not answered"
					color = "warning"
				elif channel_vars["dialstatus"] == "CANCEL":
					text = "Canceled"
					color = "warning"
				elif channel_vars["dialstatus"] == "CONGESTION":
					text = "Congestion"
					color = "#9400D3"
				elif channel_vars["dialstatus"] == "CHANUNAVAIL":
					text = "Channel unavailable"
					color = "#9400D3"
				elif channel_vars["dialstatus"] == "DONTCALL":
					text = "Reject (don't call)"
					color = "#A9A9A9"
				elif channel_vars["dialstatus"] == "TORTURE":
					text = "Reject (torture)"
					color = "#A9A9A9"
				else:
					text = "Unknown"
				self.update_message(text, msg_data, color=color)
			elif "hangupcause" in channel_vars and int(channel_vars["hangupcause"]) > 0:
				dest = self.get_destination(msg_data)
				self.update_message("Call hung up by %s" % dest, msg_data)
			else:
				self.update_message("Unknown call state", msg_data)
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
	server.config = c["slack"]
	server.calls_dict = dict()

	log.info("slack_asterisk version %s starting", __version__)

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
