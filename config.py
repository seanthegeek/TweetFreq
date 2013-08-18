"""Flask configuration"""
# Ignore "unused" import
# pylint: disable=W0611
from secrets import SECRET_KEY

DEBUG = True

BABEL_DEFAULT_LOCALE = 'en_US'
BABEL_DEFAULT_TIMEZONE = 'UTC'

if DEBUG is False:
    SERVER_NAME = "tweetfreq.py.net"
