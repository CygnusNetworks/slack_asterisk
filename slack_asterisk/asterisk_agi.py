#!/usr/bin/env python3
# coding=utf-8

import pprint
import re
import signal
import sys

from slack_asterisk import exceptions

DEFAULT_TIMEOUT = 2000  # 2sec timeout used as default for functions that take timeouts
DEFAULT_RECORD = 20000  # 20sec record time

re_code = re.compile(r'(^\d*)\s*(.*)')
re_kv = re.compile(r'(?P<key>\w+)=(?P<value>[^\s]+)\s*(?:\((?P<data>.*)\))*')


class AGI(object):  # pylint:disable=too-many-public-methods
	"""
	Asterisk AGI interface

	This class encapsulates communication between Asterisk an a python script.
	It handles encoding commands to Asterisk and parsing responses from
	Asterisk.
	"""

	def __init__(self, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr):
		self.stdin = stdin
		self.stdout = stdout
		self.stderr = stderr
		self._got_sighup = False
		signal.signal(signal.SIGHUP, self._handle_sighup)  # handle SIGHUP
		self.stderr.write('ARGS: ')
		self.stderr.write(str(sys.argv))
		self.stderr.write('\n')
		self.env = {}
		self._get_agi_env()

	def _get_agi_env(self):
		"""
		Get AGI Environment variables and store to self.env dictionary
		"""
		while 1:
			line = self.stdin.readline().strip()
			line = line.decode('utf8')
			self.stderr.write('ENV LINE: ')
			self.stderr.write(line)
			self.stderr.write('\n')
			if line == '':
				# blank line signals end
				break
			key, data = line.split(':')[0], ':'.join(line.split(':')[1:])
			key = key.strip()
			data = data.strip()
			if key != '':
				self.env[key] = data
		self.stderr.write('class AGI: self.env = ')
		self.stderr.write(pprint.pformat(self.env))
		self.stderr.write('\n')

	@staticmethod
	def _quote(string):
		"""Quote given string

		:param string: String to be quoted
		:type string: str
		:return: String wrapped in double quotes
		:rtype: str
		"""
		return ''.join(['"', str(string), '"'])

	def _handle_sighup(self, signum, frame):  # pylint:disable=unused-argument
		"""Handle the SIGHUP signal"""
		self._got_sighup = True

	def test_hangup(self):
		"""This function throws AGIHangup if we have received a SIGHUP

		:raises AGISIGHUPHangup: if call has been hung up
		"""
		if self._got_sighup:
			raise exceptions.AGISIGHUPHangup("Received SIGHUP from Asterisk")

	def execute(self, command, *args):
		"""Execute Asterisk command with supplied parameters if call has not been hung up already

		:param command: Command to be executed
		:type command: str
		:param args: Command parameters
		:type args: str
		:return: Result fetched from Asterisk
		:rtype: dict
		"""
		self.test_hangup()

		try:
			self.send_command(command, *args)
			return self.get_result()
		except IOError as e:
			if e.errno == 32:
				# Broken Pipe * let us go
				raise exceptions.AGISIGPIPEHangup("Received SIGPIPE")
			else:
				raise
		except Exception as exc:
			self.stderr.write("Exception occured: %s\n" % exc)

	def send_command(self, command, *args):
		"""Send a command with parameters to Asterisk

		:param command: Command to be executed
		:type command: str
		:param args: Command parameters
		:type args: str
		"""
		command = command.strip()
		command = '%s %s' % (command, ' '.join([str(x) for x in args]))
		command = command.strip()
		if command[-1] != '\n':
			command += '\n'
		self.stderr.write('    COMMAND: %s' % command)
		self.stdout.write(command.encode('utf8'))
		self.stdout.flush()

	def get_result(self):
		"""Read the result of a command from Asterisk

		:return: Asterisk command result
		:rtype: dict
		"""
		code = 0
		response = None
		result = {'result': ('', '')}
		line = self.stdin.readline().strip().decode('utf8')
		self.stderr.write('    RESULT_LINE: %s\n' % line)
		m = re_code.search(line)
		if m:
			code, response = m.groups()
			code = int(code)

		if code == 200:
			for key, value, data in re_kv.findall(response):
				result[key] = (value, data)

				# If user hangs up... we get 'hangup' in the data
				if data == 'hangup':
					raise exceptions.AGIResultHangup("User hung up during execution")

				if key == 'result' and value == '-1':
					raise exceptions.AGIAppError("Error executing application, or hangup")

			self.stderr.write('    RESULT_DICT: %s\n' % pprint.pformat(result))
			return result
		if code == 510:
			raise exceptions.AGIInvalidCommand(response)
		if code == 520:
			usage = [line]
			line = self.stdin.readline().strip()
			while line[:3] != '520':
				usage.append(line)
				line = self.stdin.readline().strip()
			usage.append(line)
			usage_msg = '%s\n' % '\n'.join(usage)
			raise exceptions.AGIUsageError(usage_msg)
		raise exceptions.AGIUnknownError(code, 'Unhandled code or undefined response')

	def _process_digit_list(self, digits):
		if isinstance(digits, list):
			digits = ''.join([str(x) for x in digits])
		return self._quote(digits)

	def answer(self):
		"""agi.answer() --> None
		Answer channel if not already in answer state.
		"""
		res = self.execute('ANSWER')['result'][0]
		return res

	def wait_for_digit(self, timeout=DEFAULT_TIMEOUT):
		"""agi.wait_for_digit(timeout=DEFAULT_TIMEOUT) --> digit

		Waits for up to 'timeout' milliseconds for a channel to receive a DTMF
		digit.

		:param timeout: Timeout in milliseconds
		:type timeout: int
		:returns: digit dialed
		:rtype: str
		:raises AGIError: on value conversion error
		"""
		ret = self.execute('WAIT FOR DIGIT', timeout)
		if ret and "result" in ret:
			res = ret["result"][0]
		else:
			res = '0'
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except ValueError:
			raise exceptions.AGIError('Unable to convert result to digit: %s' % res)

	def send_text(self, text=''):
		"""agi.send_text(text='') --> None

		Sends the given text on a channel.  Most channels do not support the
		transmission of text.

		:param text: Text to be sent
		:type text: str
		:returns: Asterisk command result
		:rtype: dict
		:raises AGIError: on error/hangup
		"""
		res = self.execute('SEND TEXT', self._quote(text))['result'][0]
		return res

	def receive_char(self, timeout=DEFAULT_TIMEOUT):
		"""agi.receive_char(timeout=DEFAULT_TIMEOUT) --> chr

		Receives a character of text on a channel.  Specify timeout to be the
		maximum time to wait for input in milliseconds, or 0 for infinite. Most channels
		do not support the reception of text.

		:param timeout: Timeout in milliseconds
		:type timeout: int
		:returns: received character
		:rtype: str
		:raises AGIError: on character conversion error
		"""
		res = self.execute('RECEIVE CHAR', timeout)['result'][0]

		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def tdd_mode(self, mode='off'):
		"""agi.tdd_mode(mode='on'|'off') --> None

		Enable/Disable TDD transmission/reception on a channel.

		:param mode: TDD mode to be set
		:type mode: str
		:raises AGIAppError: if channel is not TDD-capable
		"""
		res = self.execute('TDD MODE', mode)['result'][0]
		if res == '0':
			raise exceptions.AGIAppError('Channel %s is not TDD-capable')

	def stream_file(self, filename, escape_digits='', sample_offset=0):
		"""agi.stream_file(filename, escape_digits='', sample_offset=0) --> digit

		Send the given file, allowing playback to be interrupted by the given
		digits, if any.  escape_digits is a string '12345' or a list  of
		ints [1,2,3,4,5] or strings ['1','2','3'] or mixed [1,'2',3,'4']
		If sample offset is provided then the audio will seek to sample
		offset before play starts.  Returns  digit if one was pressed.
		Remember, the file extension must not be included in the filename.

		:param filename: Name of file to be streamed
		:type filename: str
		:param escape_digits: digits to be escaped
		:type escape_digits: str or list
		:param sample_offset: offset
		:type sample_offset: int
		:return: digit pressed during playback
		:rtype: str
		:raises AGIError: if the channel was disconnected
		"""
		escape_digits = self._process_digit_list(escape_digits)
		response = self.execute('STREAM FILE', filename, escape_digits, sample_offset)
		res = response['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def control_stream_file(self, filename, escape_digits='', skipms=3000, fwd='', rew='', pause=''):  # pylint:disable=too-many-arguments
		"""
		Send the given file, allowing playback to be interrupted by the given
		digits, if any.  escape_digits is a string '12345' or a list  of
		ints [1,2,3,4,5] or strings ['1','2','3'] or mixed [1,'2',3,'4']
		If sample offset is provided then the audio will seek to sample
		offset before play starts.  Returns  digit if one was pressed.
		Throws AGIError if the channel was disconnected.  Remember, the file
		extension must not be included in the filename.
		"""
		escape_digits = self._process_digit_list(escape_digits)
		response = self.execute('CONTROL STREAM FILE', self._quote(filename), escape_digits, self._quote(skipms), self._quote(fwd), self._quote(rew), self._quote(pause))

		if response is None:
			raise exceptions.HangupDetected()

		res = response['result'][0]

		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def send_image(self, filename):
		"""agi.send_image(filename) --> None

		Sends the given image on a channel.  Most channels do not support the
		transmission of images.   Image names should not include extensions.
		Throws AGIError on channel failure
		"""
		res = self.execute('SEND IMAGE', filename)['result'][0]
		if res != '0':
			raise exceptions.AGIAppError('Channel failure on channel %s' % self.env.get('agi_channel', 'UNKNOWN'))

	def say_digits(self, digits, escape_digits=''):
		"""agi.say_digits(digits, escape_digits='') --> digit

		Say a given digit string, returning early if any of the given DTMF digits
		are received on the channel.
		Throws AGIError on channel failure
		"""
		digits = self._process_digit_list(digits)
		escape_digits = self._process_digit_list(escape_digits)
		res = self.execute('SAY DIGITS', digits, escape_digits)['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def say_number(self, number, escape_digits=''):
		"""agi.say_number(number, escape_digits='') --> digit

		Say a given digit string, returning early if any of the given DTMF digits
		are received on the channel.
		Throws AGIError on channel failure
		"""
		number = self._process_digit_list(number)
		escape_digits = self._process_digit_list(escape_digits)
		res = self.execute('SAY NUMBER', number, escape_digits)['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def say_alpha(self, characters, escape_digits=''):
		"""agi.say_alpha(string, escape_digits='') --> digit

		Say a given character string, returning early if any of the given DTMF
		digits are received on the channel.
		Throws AGIError on channel failure
		"""
		characters = self._process_digit_list(characters)
		escape_digits = self._process_digit_list(escape_digits)
		res = self.execute('SAY ALPHA', characters, escape_digits)['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def say_phonetic(self, characters, escape_digits=''):
		"""agi.say_phonetic(string, escape_digits='') --> digit

		Phonetically say a given character string, returning early if any of
		the given DTMF digits are received on the channel.
		Throws AGIError on channel failure
		"""
		characters = self._process_digit_list(characters)
		escape_digits = self._process_digit_list(escape_digits)
		res = self.execute(
			'SAY PHONETIC', characters, escape_digits)['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def say_date(self, seconds, escape_digits=''):
		"""agi.say_date(seconds, escape_digits='') --> digit

		Say a given date, returning early if any of the given DTMF digits are
		pressed.  The date should be in seconds since the UNIX Epoch (Jan 1, 1970 00:00:00)
		"""
		escape_digits = self._process_digit_list(escape_digits)
		res = self.execute('SAY DATE', seconds, escape_digits)['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def say_time(self, seconds, escape_digits=''):
		"""agi.say_time(seconds, escape_digits='') --> digit

		Say a given time, returning early if any of the given DTMF digits are
		pressed.  The time should be in seconds since the UNIX Epoch (Jan 1, 1970 00:00:00)
		"""
		escape_digits = self._process_digit_list(escape_digits)
		res = self.execute('SAY TIME', seconds, escape_digits)['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def say_datetime(self, seconds, escape_digits='', fmt='', zone=''):
		"""agi.say_datetime(seconds, escape_digits='', format='', zone='') --> digit

		Say a given date in the format specified (see voicemail.conf), returning
		early if any of the given DTMF digits are pressed.  The date should be
		in seconds since the UNIX Epoch (Jan 1, 1970 00:00:00).
		"""
		escape_digits = self._process_digit_list(escape_digits)
		if fmt:
			fmt = self._quote(fmt)
		res = self.execute(
			'SAY DATETIME', seconds, escape_digits, fmt, zone)['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def get_data(self, filename, timeout=DEFAULT_TIMEOUT, max_digits=255):
		"""agi.get_data(filename, timeout=DEFAULT_TIMEOUT, max_digits=255) --> digits
		Stream the given file and receive dialed digits
		"""
		result = self.execute('GET DATA', filename, timeout, max_digits)
		res, _ = result['result']
		return res

	def get_option(self, filename, escape_digits='', timeout=0):
		"""agi.get_option(filename, escape_digits='', timeout=0) --> digit

		Send the given file, allowing playback to be interrupted by the given
		digits, if any.  escape_digits is a string '12345' or a list  of
		ints [1,2,3,4,5] or strings ['1','2','3'] or mixed [1,'2',3,'4']
		Returns  digit if one was pressed.
		Throws AGIError if the channel was disconnected.  Remember, the file
		extension must not be included in the filename.
		"""
		escape_digits = self._process_digit_list(escape_digits)
		if timeout:
			response = self.execute(
				'GET OPTION', filename, escape_digits, timeout)
		else:
			response = self.execute('GET OPTION', filename, escape_digits)

		res = response['result'][0]
		if res == '0':
			return ''
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to char: %s' % res)

	def set_context(self, context):
		"""agi.set_context(context)

		Sets the context for continuation upon exiting the application.
		No error appears to be produced.  Does not set exten or priority
		Use at your own risk.  Ensure that you specify a valid context.
		"""
		self.execute('SET CONTEXT', context)

	def set_extension(self, extension):
		"""agi.set_extension(extension)

		Sets the extension for continuation upon exiting the application.
		No error appears to be produced.  Does not set context or priority
		Use at your own risk.  Ensure that you specify a valid extension.
		"""
		self.execute('SET EXTENSION', extension)

	def set_priority(self, priority):
		"""agi.set_priority(priority)

		Sets the priority for continuation upon exiting the application.
		No error appears to be produced.  Does not set exten or context
		Use at your own risk.  Ensure that you specify a valid priority.
		"""
		self.execute('set priority', priority)

	def record_file(self, filename, fmt='gsm', escape_digits='#', timeout=DEFAULT_RECORD, offset=0, beep='beep'):  # pylint:disable=too-many-arguments
		"""agi.record_file(filename, format, escape_digits, timeout=DEFAULT_TIMEOUT, offset=0, beep='beep') --> None

		Record to a file until a given dtmf digit in the sequence is received
		The format will specify what kind of file will be recorded.  The timeout
		is the maximum record time in milliseconds, or -1 for no timeout. Offset
		samples is optional, and if provided will seek to the offset without
		exceeding the end of the file
		"""
		escape_digits = self._process_digit_list(escape_digits)
		res = self.execute('RECORD FILE', self._quote(filename), fmt, escape_digits, timeout, offset, beep)['result'][0]
		try:
			return chr(int(res))
		except Exception:
			raise exceptions.AGIError('Unable to convert result to digit: %s' % res)

	def set_autohangup(self, secs):
		"""agi.set_autohangup(secs) --> None

		Cause the channel to automatically hangup at <secs> seconds in the
		future.  Of course it can be hungup before then as well.   Setting to
		0 will cause the autohangup feature to be disabled on this channel.
		"""
		self.execute('SET AUTOHANGUP', secs)

	def hangup(self, channel=''):
		"""agi.hangup(channel='')
		Hangs up the specified channel.
		If no channel name is given, hangs up the current channel
		"""
		self.execute('HANGUP', channel)

	def appexec(self, application, options=''):
		"""agi.appexec(application, options='')
		Executes <application> with given <options>.
		Returns whatever the application returns, or -2 on failure to find
		application
		"""
		result = self.execute('EXEC', application, self._quote(options))
		res = result['result'][0]
		if res == '-2':
			raise exceptions.AGIAppError('Unable to find application: %s' % application)
		return res

	def set_callerid(self, number):
		"""agi.set_callerid(number) --> None
		Changes the callerid of the current channel.
		"""
		self.execute('SET CALLERID', number)

	def channel_status(self, channel=''):
		"""agi.channel_status(channel='') --> int
		Returns the status of the specified channel.  If no channel name is
		given the returns the status of the current channel.

		Return values:
		0 Channel is down and available
		1 Channel is down, but reserved
		2 Channel is off hook
		3 Digits (or equivalent) have been dialed
		4 Line is ringing
		5 Remote end is ringing
		6 Line is up
		7 Line is busy
		"""
		try:
			result = self.execute('CHANNEL STATUS', channel)
		except exceptions.AGIHangup:
			raise
		except exceptions.AGIAppError:
			result = {'result': ('-1', '')}

		return int(result['result'][0])

	def set_variable(self, name, value):
		"""Set a channel variable.
		"""
		self.execute('SET VARIABLE', self._quote(name), self._quote(value))

	def get_variable(self, name):
		"""Get a channel variable.

		This function returns the value of the indicated channel variable.  If
		the variable is not set, an empty string is returned.
		"""
		try:
			result = self.execute('GET VARIABLE', self._quote(name))
		except exceptions.AGIResultHangup:
			result = {'result': ('1', 'hangup')}

		_, value = result['result']
		return value

	def get_full_variable(self, name, channel=None):
		"""Get a channel variable.

		This function returns the value of the indicated channel variable.  If
		the variable is not set, an empty string is returned.
		"""
		try:
			if channel:
				result = self.execute('GET FULL VARIABLE', self._quote(name), self._quote(channel))
			else:
				result = self.execute('GET FULL VARIABLE', self._quote(name))

		except exceptions.AGIResultHangup:
			result = {'result': ('1', 'hangup')}

		_, value = result['result']
		return value

	def verbose(self, message, level=1):
		"""agi.verbose(message='', level=1) --> None
		Sends <message> to the console via verbose message system.
		<level> is the the verbose level (1-4)
		"""
		self.execute('VERBOSE', self._quote(message), level)

	def database_get(self, family, key):
		"""agi.database_get(family, key) --> str
		Retrieves an entry in the Asterisk database for a given family and key.
		Returns 0 if <key> is not set.  Returns 1 if <key>
		is set and returns the variable in parenthesis
		example return code: 200 result=1 (testvariable)
		"""
		family = '"%s"' % family
		key = '"%s"' % key
		result = self.execute('DATABASE GET', self._quote(family), self._quote(key))
		res, value = result['result']
		if res == '0':
			raise exceptions.AGIDBError('Key not found in database: family=%s, key=%s' % (family, key))
		if res == '1':
			return value
		raise exceptions.AGIError('Unknown exception for : family=%s, key=%s, result=%s' % (family, key, pprint.pformat(result)))

	def database_put(self, family, key, value):
		"""agi.database_put(family, key, value) --> None
		Adds or updates an entry in the Asterisk database for a
		given family, key, and value.
		"""
		result = self.execute('DATABASE PUT', self._quote(family), self._quote(key), self._quote(value))
		res, value = result['result']
		if res == '0':
			raise exceptions.AGIDBError('Unable to put value in database: family=%s, key=%s, value=%s' % (family, key, value))

	def database_del(self, family, key):
		"""agi.database_del(family, key) --> None
		Deletes an entry in the Asterisk database for a
		given family and key.
		"""
		result = self.execute('DATABASE DEL', self._quote(family), self._quote(key))
		res, _ = result['result']
		if res == '0':
			raise exceptions.AGIDBError('Unable to delete from database: family=%s, key=%s' % (family, key))

	def database_deltree(self, family, key=''):
		"""agi.database_deltree(family, key='') --> None
		Deletes a family or specific keytree with in a family
		in the Asterisk database.
		"""
		result = self.execute('DATABASE DELTREE', self._quote(family), self._quote(key))
		res, _ = result['result']
		if res == '0':
			raise exceptions.AGIDBError('Unable to delete tree from database: family=%s, key=%s' % (family, key))

	def noop(self):
		"""agi.noop() --> None
		Does nothing
		"""
		self.execute('NOOP')
