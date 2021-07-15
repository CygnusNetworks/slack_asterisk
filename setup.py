#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

import slack_asterisk

setup(
	name='slack-asterisk',
	version=slack_asterisk.__version__,
	description='Cygnus Networks GmbH Slack Asterisk App',
	author='Torge Szczepanek',
	author_email='debian@cygnusnetworks.de',
	maintainer='Torge Szczepanek',
	maintainer_email='debian@cygnusnetworks.de',
	license='Apache-2.0',
	entry_points={'console_scripts': ['slack-asterisk = slack_asterisk.main:main']},
	packages=find_packages(),
	install_requires=['configobj', 'slackclient', 'falcon']
)
