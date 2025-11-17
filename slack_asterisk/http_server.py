"""Simple Flask-based HTTP server (replacing Falcon).

Exposes a single health endpoint returning "OK". Intended as a lightweight
status/oAuth callback placeholder matching previous behavior.
"""

# coding=utf-8

import logging
import os
from flask import Flask, request, Response

log = logging.getLogger("slack_asterisk")


def _init_logging_from_env():
    level_name = os.getenv("LOG_LEVEL", os.getenv("DEBUG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    if not log.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        log.addHandler(ch)
    log.setLevel(level)


_init_logging_from_env()

app = Flask(__name__)


@app.route("/", methods=["GET"])  # health/simple endpoint
def root_ok():  # pylint:disable=unused-variable
    log.debug("Got %s request for %s", request.method, request.path)
    return Response("OK", status=200, mimetype="text/plain")


def oauth_server(ip, port, _):
    # Run a threaded Flask development server. In production, use a WSGI server.
    app.run(host=ip, port=port, threaded=True)
