#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TweetFreq - A flask-based web application for analyzing tweets
"""

from datetime import datetime, timedelta
from time import sleep

from redis import StrictRedis
from flask import Flask, render_template, flash, jsonify, redirect, url_for
from flask.json import loads, dumps
from flask_wtf import Form
from wtforms import StringField
from wtforms.validators import DataRequired, Length

from twitter import get_count, get_full_timeline, get_tweet_datetimes,\
    get_words_from_tweets, get_next_reset, convert_timestamp,\
    TwitterRateLimitException, NoTweetsException

from flask_babel import Babel
from babel.numbers import format_number
from babel.dates import format_timedelta

from twython import TwythonAuthError
from celery import Celery

__author__ = "Sean Whalen"
__license___ = "MIT"
__version__ = '0.1.0'

APP = Flask(__name__)
APP.config.from_pyfile("config.py")
BABEL = Babel(APP)

REDIS_PREFIX = "tweetfreq"
CACHE_HOURS = 1

CELERY = Celery(REDIS_PREFIX, broker=APP.config["BROKER_URL"])
CELERY.conf.CELERY_TASK_SERIALIZER = 'json'
CELERY.conf.CELERY_RESULT_SERIALIZER = 'json'
CELERY.conf.CELERY_ACCEPT_CONTENT = ['json']

LOCALE = APP.config['BABEL_DEFAULT_LOCALE']


class UserForm(Form):
    """Form to search by username"""
    name = StringField(label="Username", validators=[Length(max=16),
                           DataRequired()])


def flash_errors(form):
    """Flashes form errors"""
    for field, errors in form.errors.items():
        for error in errors:
            flash("Error in the %s field - %s" % (
                getattr(form, field).label.text, error), 'error')


@APP.errorhandler(500)
def server_error(e):
    """Handles server errors"""
    # Ignore unused arguments
    # pylint: disable=W0613
    return render_template("errors/500.html"), 500


@APP.errorhandler(404)
def not_found_error(e):
    """HTTP 404 view"""
    # Ignore unused arguments
    # pylint: disable=W0613
    return render_template("errors/404.html"), 404


@CELERY.task
def load_tweets(username):
    """Loads json results into redis as a cache"""
    redis = StrictRedis()
    redis_key = "%s.user.%s" % (REDIS_PREFIX, username)
    status = redis.get(redis_key)

    # Prevent DoS
    if status is not None and loads(status)['status'] != 'queued':
        return None
    try:
        created = datetime.utcnow()
        status = dumps(dict(stats='running', header="Retrieving tweets",
                            message='', code=200))
        redis.set(redis_key, status)
        redis.expire(redis_key, 2*60)
        timeline = get_full_timeline(username)
        start = timeline[-1]
        start = dict(id=start['id'],
                     timestamp=convert_timestamp(start['created_at']))
        end = timeline[0]
        end = dict(id=end['id'],
                   timestamp=convert_timestamp(end['created_at']))
        total = len(timeline)
        formatted_total = format_number(total, locale=LOCALE)
        status = dumps(dict(stats='running', header="Processing tweets",
                            message='Received %s tweets' % formatted_total,
                            code=200))
        redis.set(redis_key, status)
        redis.expire(redis_key, 10*60)
        total = dict(int=total, formatted=formatted_total)

        words = get_count(get_words_from_tweets(timeline), limit=300)
        dates = get_count(get_tweet_datetimes(timeline, date_only=True),
                          order_by=0, reverse=False)
        sum = 0
        for date in dates:
            sum += date[1]
        avg = float(sum) / float(len(dates))
        avg = dict(int=avg, formatted=format_number(avg, locale=LOCALE))

        _max = sorted(dates, key=lambda x: x[1], reverse=True)[0][1]

        _max = dict(int=_max, formatted=format_number(_max, locale=LOCALE))

        expires = datetime.utcnow() + timedelta(hours=CACHE_HOURS)

        stats = dict(avg_per_day=avg, max_per_day=_max, total=total)

        status = 'done'

        status = dict(status=status, code=200,
                      data=dict(start=start, end=end, dates=dates, words=words,
                                stats=stats, created=created,
                                expires=expires, users=[username],
                                search_terms=[]))
        status = dumps(status)
        redis.set(redis_key, status)
        redis.expire(redis_key, CACHE_HOURS*60*60)

    except TwythonAuthError:
        status = 'error'
        header = "Tweets not available"
        message = "That user's timeline is protected/private"
        status = dict(status=status, header=header, message=message,
                      code=403)
        status = dumps(status)
        redis.set(redis_key, status)
        redis.expire(redis_key, 60*5)

    except ValueError:
        status = 'error'
        header = "User not found"
        message = "The specified Twitter username does not exist"
        status = dict(status=status, header=header, message=message,
                      code=404)
        status = dumps(status)
        redis.set(redis_key, status)
        redis.expire(redis_key, 60*5)

    except TwitterRateLimitException:
        status = 'error'
        header = "Resources exhausted"
        reset = format_timedelta(get_next_reset() - datetime.utcnow(),
                                 locale=LOCALE)
        message = "TweetFreq is under a heavy load. Try again in %s." % reset
        status = dict(status=status, header=header, message=message, code=503)
        status = dumps(status)
        redis.set(redis_key, status)
        redis.expire(redis_key, 2)

    except NoTweetsException:
        status = 'error'
        header = "No tweets found"
        message = ""
        status = dict(status=status, header=header, message=message,
                      code=404)
        status = dumps(status)
        redis.set(redis_key, status)
        redis.expire(redis_key, 60*5)

@APP.context_processor
def inject_status():
    """Injects status info into templates"""
    return dict(version=__version__,
                status=StrictRedis().get('tweetfreq.status'))


@APP.route('/', methods=('GET', 'POST'))
def index():
    """The index view"""
    form = UserForm()
    if form.validate_on_submit():
        username = form.name.data.lower()
        if username.startswith('@'):
            username = username[1:]
        return redirect(url_for('view_user_report', username=username),
                        301)
    return render_template("index.html", form=form)


@APP.route("/about/")
def about():
    """he about view"""
    return render_template("about.html")


@APP.route('/u/<username>.json')
def view_user_json(username):
    """The twitter user JSON view"""
    username = username.lower()
    redis_key = "%s.user.%s" % (REDIS_PREFIX, username)
    redis = StrictRedis()
    cache = redis.get(redis_key)
    if not cache:
        cache = dict(status='queued', header='Queued',
                     message="Your request will be processed shortly",
                     code=200)
        redis.set(redis_key, dumps(cache))
        redis.expire(redis_key, CACHE_HOURS*60*60)
        load_tweets.delay(username)
        sleep(.5)
    cache = loads(redis.get(redis_key))

    return jsonify(cache)

@APP.route('/u/<username>/')
def view_user_report(username):
    """The twitter user report view"""
    return render_template('user.html', username=username)

if __name__ == '__main__':
    APP.run()
