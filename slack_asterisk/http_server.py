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
    # SECURITY NOTE: Flask's built-in development server is used here.
    # It is not suitable for production: it has no request concurrency limits,
    # no TLS support, and limited error isolation. For production deployments,
    # replace this with a WSGI server such as Gunicorn or uWSGI, e.g.:
    #   gunicorn -w 2 -b ip:port "slack_asterisk.http_server:app"
    app.run(host=ip, port=port, threaded=True)
