# coding=utf-8

import falcon
import logging
import wsgiref
import wsgiref.simple_server
import SocketServer

log = logging.getLogger("slack_asterisk")

app = falcon.API()


class ThreadingWSGIServer(SocketServer.ThreadingMixIn, wsgiref.simple_server.WSGIServer):  # pylint:disable=too-few-public-methods
	pass


class NoLoggingWSGIRequestHandler(wsgiref.simple_server.WSGIRequestHandler, object):  # pylint:disable=too-few-public-methods
	"""WSGIRequestHandler that logs to debug instead of stderr"""

	def log_message(self, _, *args):
		# pylint:disable=W1401
		"""Log an arbitrary message to log.debug
		"""
		# pylint:enable=W1401
		log.debug("HTTP server request %s - status %s - length %s", *args)


class HTTPHandler(object):  # pylint:disable=too-few-public-methods
	def on_get(self, req, resp):  # pylint:disable=no-self-use
		log.debug("Got GET request for %s", req.path)
		resp.status = falcon.HTTP_200
		resp.body = "OK"


def oauth_server(ip, port, _):
	httph = HTTPHandler()
	app.add_route('/', httph)
	http_serv = wsgiref.simple_server.make_server(ip, port, app, server_class=ThreadingWSGIServer, handler_class=NoLoggingWSGIRequestHandler)
	http_serv.serve_forever()
