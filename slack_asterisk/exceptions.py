# coding=utf-8
# pylint: disable=unnecessary-pass


class AGIException(Exception):
	"""Base AGI Exception"""
	pass


class AGIError(AGIException):
	"""AGI Generic Error"""
	pass


class AGIUnknownError(AGIError):
	"""AGI Unknown Error"""
	pass


class AGIAppError(AGIError):
	"""AGI App Error"""
	pass


class AGIHangup(AGIAppError):
	"""Base AGI Hangup"""
	pass


class AGISIGHUPHangup(AGIHangup):
	"""AGI SIGHUP Hangup"""
	pass


class AGISIGPIPEHangup(AGIHangup):
	"""AGI SIGPIPE Hangup"""
	pass


class AGIResultHangup(AGIHangup):
	"""AGI Result Hangup"""
	pass


class AGIDBError(AGIAppError):
	"""AGI Database Error"""
	pass


class AGIUsageError(AGIError):
	"""AGI Usage Error"""
	pass


class AGIInvalidCommand(AGIError):
	"""AGI Invalid Command Error"""
	pass
