# coding=utf-8
import argparse
import logging
import sys
import signal
import os

from . import __version__
from . import agi_server
from . import config

LOG_SPEC = "%(name)s[%(process)s]: %(filename)s:%(lineno)d/%(funcName)s###%(message)s"

def _get_log_level_from_env():
    level_name = os.environ.get("LOG_LEVEL", os.environ.get("DEBUG_LEVEL", "INFO")).upper()
    return getattr(logging, level_name, logging.INFO)


log = logging.getLogger("slack_asterisk")
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(logging.Formatter("%(asctime)s.%(msecs)06d" + " " + LOG_SPEC, datefmt='%Y-%m-%dT%T'))
ch.setLevel(_get_log_level_from_env())
log.addHandler(ch)
log.setLevel(_get_log_level_from_env())


def _handle_stop_signal(signum, frame):  # pylint:disable=unused-argument
	log.info("Received signal %s, stopping AGI server immediately", signum)
	# Immediate stop – terminate the process
	sys.exit(0)


def main():
	# Ensure SLACK_TOKEN is set in environment
	if not os.environ.get("SLACK_TOKEN"):
		log.error("Environment variable SLACK_TOKEN must be set before starting slack_asterisk.")
		sys.exit(1)

	conf = config.SlackAsteriskConfig()
	c = conf.get_configobj()

	argp = argparse.ArgumentParser()
	argp.add_argument("-i", "--ip", help="Set bind ip", default=c["general"]["ip"])
	argp.add_argument("-p", "--port", help="Set bind port", type=int, default=c["general"]["port"])

	args = argp.parse_args()  # pylint: disable=W0612

	ip = args.ip
	port = args.port

	# Register signal handlers so external stops (SIGTERM/SIGINT) kill the server immediately
	signal.signal(signal.SIGTERM, _handle_stop_signal)
	signal.signal(signal.SIGINT, _handle_stop_signal)

	log.info("slack_asterisk version %s starting AGI server on %s:%i", __version__, ip, port)

	agi_server.agi_server(ip, port, c)


if __name__ == "__main__":
	main()
