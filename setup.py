#!/usr/bin/env python
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
	license='FIXME',
	entry_points={'console_scripts': ['slack-asterisk = slack_asterisk.fastagi:main']},
	packages=find_packages(),
	install_requires=['pyst', 'slackclient']
)
