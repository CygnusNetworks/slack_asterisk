"""Minimal Flask-based HTTP health server (deprecated module).

This file previously hosted a Falcon-based HTTP server. It is now converted to
Flask for Python 3 compatibility and to avoid the Falcon dependency. It is not
used by the main application flow but retained for compatibility.
"""

# coding=utf-8

import logging
from flask import Flask

log = logging.getLogger("slack_asterisk")

app = Flask(__name__)


@app.get("/")
def root():  # pylint:disable=unused-variable
    log.debug("Got GET request for /")
    return "OK", 200


def oauth_server(ip, port, _):
    app.run(host=ip, port=port)
