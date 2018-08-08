# coding=utf-8
import argparse
import logging
import sys

from . import __version__
from . import agi_server
from . import config
from . import http_server

log = logging.getLogger("slack_asterisk")
log.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
log.addHandler(ch)


def main():
	argp = argparse.ArgumentParser()
	argp.add_argument("-i", "--ip", help="Set bind ip", default=None)
	argp.add_argument("-p", "--port", help="Set bind port", type=int, default=None)

	args = argp.parse_args()  # pylint: disable=W0612

	conf = config.SlackAsteriskConfig()
	c = conf.get_configobj()

	if args.ip is not None:
		ip = args.ip
	else:
		ip = c["general"]["ip"]

	log.info("slack_asterisk version %s starting AGI server", __version__)
	if args.port is not None:
		port = args.port
	else:
		port = c["general"]["port"]
	agi_server.agi_server(ip, port, c)

if __name__ == "__main__":
	main()
