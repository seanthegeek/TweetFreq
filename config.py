"""Flask configuration"""
# Ignore "unused" import
# pylint: disable=W0611
from secrets import SECRET_KEY

DEBUG = False

BABEL_DEFAULT_LOCALE = 'en_US'
BABEL_DEFAULT_TIMEZONE = 'UTC'

# Celery settings
CELERY_ACCEPT_CONTENT = [ 'json']
BROKER_URL = "redis://localhost:6379/1"
CELERYD_CONCURRENCY = 3
CELERY_IMPORTS = ('tweetfreq', )
