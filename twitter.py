#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Twitter analysis helpers. Command line interface is a work in progress.

Usage:
  twitter.py init <app_key> <app_secret>
  twitter.py [options] user <username> words [minimum] [maximum] [limit] [words | count]
  twitter.py [options] user <username> dates [minimum] [maximum] [limit] [times | count]

Options:
--output FILENAME
--pretty
"""

from re import match
from math import ceil
from time import mktime, strptime
from datetime import datetime
try:
    from html.parser import HTMLParser
except ImportError:
    from HTMLParser import HTMLParser

import docopt
import redis
from twython import Twython, TwythonError

from nltk import download
from nltk.corpus import stopwords

__author__ = "Sean Whalen"
__license___ = "MIT"
__version__ = '0.1.0'

# Prefix to avoid naming conflicts
REDIS_PREFIX = 'tweetferq'

_REDIS = redis.StrictRedis()
_APP_KEY = _REDIS.get("%s.twitter.app_key" % REDIS_PREFIX)
_ACCESS_TOKEN = _REDIS.get("%s.twitter.access_token" % REDIS_PREFIX)

TWITTER = Twython(_APP_KEY, access_token=_ACCESS_TOKEN)

# The oldest number of available tweets fom a user timeline.
_MAX_TWEETS = 3200

# Maximum tweets to receive per request. Twitter API upper limit.
_MAX_TWEETS_PER_REQUEST = 200

PARSER = HTMLParser()

# Adapted from http://www.textfixer.com/resources/english-contractions-list.txt
CONTRACTIONS = """ain't,aren't,can't,could've,couldn't,didn't,doesn't,don't,
hasn't,he'd,he'll,he's,here's,how'd,how'll,how's,i'd,i'll,i'm,i've,isn't,
it's,might've,mightn't,must've,mustn't,shan't,she'd,she'll,she's,should've,
shouldn't,that'll,that's,there's,they'd,they'll,they're,they've,wasn't,we'd,
we'll,we're,weren't,what'd,what's,when,when'd,when'll,when's,where'd,where'll,
where's,who'd,who'll,who's,why'd,why'll,why's,won't,would've,wouldn't,y'all,
you'd,you'll,you're,you've"""

CONTRACTIONS = CONTRACTIONS.replace("\n", "").split(",")


class NoTweetsException(Exception):
    """Raise when a no tweets were found"""

class TwitterRateLimitException(Exception):
    """Raise when a Twitter rate limit has been or would be reached"""


def get_rate_limits(resource_families=None):
    """Saves rate limit values in redis"""
    pipeline = _REDIS.pipeline()
    resources = TWITTER.get_application_rate_limit_status(
        resources=resource_families)
    resources = resources['resources']
    reset = TWITTER._last_call['headers']['X-Rate-Limit-Reset']
    pipeline.set("twitter.reset", reset)
    for resource_family in resources:
        for resource in resources[resource_family].keys():
            limit = resources[resource_family][resource]['limit']
            remaining = resources[resource_family][resource]['remaining']
            pipeline.set("%s.twitter.%s.limit" % (REDIS_PREFIX, resource),
                         limit)
            pipeline.set("%s.twitter.%s.remaining" % (REDIS_PREFIX, resource),
                         remaining)
            pipeline.execute()


def init(app_key, app_secret):
    """Sets up redis for use with Twitter"""
    global TWITTER, _ACCESS_TOKEN, _APP_KEY
    _APP_KEY = app_key
    try:
        TWITTER = Twython(app_key, app_secret, oauth_version=2)
        _ACCESS_TOKEN = TWITTER.obtain_access_token()
        TWITTER = Twython(_APP_KEY, access_token=_ACCESS_TOKEN)
        _REDIS.set("%s.twitter.app_key" % REDIS_PREFIX, _APP_KEY)
        _REDIS.set("%s.twitter.access_token" % REDIS_PREFIX, _ACCESS_TOKEN)
        _REDIS.save()
        get_rate_limits()
        download("stopwords")

    except KeyError:
        raise ValueError("Application key and/or secret is invalid")


def save_twitter_headers(resource):
    """Saves information from the last Twitter response in redis"""

    # Access to 'protected' member required. Disable warning.
    # pylint: disable=W0212
    headers = TWITTER._last_call['headers']
    _REDIS.set('%s.twitter.%s.limit' % (REDIS_PREFIX, resource),
               headers['X-Rate-Limit-Limit'])
    _REDIS.set('%s.twitter.%s.remaining' % (REDIS_PREFIX, resource),
               headers['X-Rate-Limit-Remaining'])
    _REDIS.set('twitter.reset',
               headers['X-Rate-Limit-Reset'])


def get_remaining_calls(resource):
    """Return the number of remaining calls for a given Twitter REST API
     method stored by _save_twitter_headers()."""

    return int(_REDIS.get('%s.twitter.%s.remaining' % (REDIS_PREFIX,
                                                       resource)))


def get_next_reset():
    """Returns a datetime of the next Twitter REST API rate limit rest."""
    reset = datetime.utcfromtimestamp(float(_REDIS.get('twitter.reset')))

    if reset < datetime.utcnow():
        get_rate_limits()
        reset = datetime.utcfromtimestamp(float(_REDIS.get('twitter.reset')))

    return reset


def get_older_tweets(screen_name, _id):
    """Returns a list of up to 200 tweets from the of the given screen name,
    including replies and retweets, that are older than the given tweet ID."""

    if get_remaining_calls('/statuses/user_timeline') < 1:
        raise TwitterRateLimitException("Not enough APIs calls remaining")

    older_tweets = TWITTER.get_user_timeline(screen_name=screen_name,
                                             count=_MAX_TWEETS_PER_REQUEST,
                                             include_rts=True,
                                             max_id=_id)

     # max_id is inclusive, so remove the first element

    try:
        del older_tweets[0]
    except IndexError:
        # Twitter returned bad data, try again
        return get_older_tweets(screen_name, _id)

    save_twitter_headers('/statuses/user_timeline')

    return older_tweets


def calculate_timeline_calls(screen_name):
    """Returns the number of "statuses" requests needed to get all available
    tweets from a timeline"""

    if get_remaining_calls('/users/show/:id') < 1:
        raise TwitterRateLimitException("Not enough APIs calls remaining")

    try:
        tweets = TWITTER.show_user(screen_name=screen_name)['statuses_count']

        # Limited to last _MAX_TWEETS tweets by Twitter API
        if tweets > _MAX_TWEETS:
            tweets = _MAX_TWEETS

        # Overhead from checking for end of available tweets
        overhead = 1
        if tweets <= _MAX_TWEETS_PER_REQUEST:
            overhead += 1

        save_twitter_headers('/users/show/:id')

        return int(ceil(float(tweets)/200) + overhead)
    except TwythonError:
        raise ValueError("The user account specified does not exist")


def get_full_timeline(screen_name):
    """Returns a list of all available tweets from the timeline of the given
    screen name, including replies and retweets. Limited by the Twitter API to
    about the last 3,200 tweets."""

    screen_name = screen_name.replace(u'@', u'')

    remaining_calls = get_remaining_calls('/statuses/user_timeline')
    needed_calls = calculate_timeline_calls(screen_name)

    if remaining_calls < needed_calls:
        raise TwitterRateLimitException("Not enough APIs calls remaining")

    tweets = TWITTER.get_user_timeline(screen_name=screen_name,
                                       count=_MAX_TWEETS_PER_REQUEST,
                                       include_rts=True)
    if len(tweets) is 0:
        raise NoTweetsException("%s has no tweets" % screen_name)

    older_tweets = get_older_tweets(screen_name, tweets[-1]['id'])

    while len(older_tweets) > 0:
        tweets += older_tweets
        older_tweets = get_older_tweets(screen_name, tweets[-1]['id'])

    save_twitter_headers('/statuses/user_timeline')

    return tweets


def number(word):
    """Returns a boolean indicating if the given word is a number"""
    return match(r'\d', word) is not None


def useful_word(word):
    """Returns a boolean indicating if the given word is not a digit or
    stopword"""

    twitter_stops = [u'rt', u'ff', u'&', u'\u002B', u'w', u're', u'cc', u'et',
                     u'al', u'\u2026', u'u', u'via', u'a.m.', u'p.m.', u'@',
                     u'-', u'\u2013', u'\u2014', u'|', u'\u0166']

    stops = stopwords.words("english")

    return not number(word) and word not in stops and \
        word not in CONTRACTIONS and word not in twitter_stops


def normalize_word(word):
    """Returns a lowercase version of the given string, with sentence-ending
    punctuation removed"""
    word = word.lower()

    # Replace single right quotation mark with apostrophe
    word = word.replace(u'\u2019', u'\u0027')

    # Remove some punctuation
    starting_punctuation = ('"', "'", '\\', '/', u'\u201C')
    ending_punctuation = ('?', '!', '.', ',', ':', ';', '-', '"',  "'", '/',
                          '\\', u'\u201D')
    ending_exceptions = ['a.m.', 'p.m.', 'u.s.']

    if len(word) > 3:
        # Probably not an emoticon, remove brackets
        starting_punctuation += ('(', '[', '}', '<', u"\u00AB")
        ending_punctuation += (')', ']', '}', '>', u"\u00BB")

    word = PARSER.unescape(word)
    while word.startswith(starting_punctuation):
        word = word[1:]
    if word not in ending_exceptions:
        while word.endswith(ending_punctuation):
            word = word[:-1]

    return word


def get_words_from_tweets(timeline, normalize=True, useful_only=True):
    """Returns a list of strings separated by whitespace (i.e. "words") from
    the given Twitter timeline, including duplicates"""

    words = []

    for tweet in timeline:
        words += tweet['text'].split()

    if normalize:
        for i in range(len(words)):
            words[i] = normalize_word(words[i])

    while "" in words:
        words.remove("")

    if useful_only:
        useful_words = []

        for word in words:
            if useful_word(word):
                useful_words.append(word)

        words = useful_words

    return words


def convert_timestamp(timestamp):
    """Returns a Python datetime, given a Twitter timestamp"""

    # Convert to timestruct
    tstruct = strptime(timestamp, '%a %b %d %H:%M:%S +0000 %Y')

    # Convert timestruct to datetime
    return datetime.fromtimestamp(mktime(tstruct))


def get_tweet_datetimes(timeline, date_only=False):
    """Returns a list of Tweet datetimes, given a timeline"""

    datetimes = []

    for tweet in timeline:
        timestamp = convert_timestamp(tweet['created_at'])
        if date_only:
            timestamp = unicode(timestamp.date())
        datetimes.append(timestamp)

    return datetimes


def get_count(items, order_by=1, minimum=None, maximum=None, limit=None,
              reverse=True):
    """Given a list of items, return a list of tuples, with the first value
    containing an item, and the second value containing the number of times
    that item appears in the list of items
    :rtype : list
    :param items: A list of items
    :param order_by: The tuple position to order by
    :param minimum: An inclusive minimum value to filter by
    :param maximum: An inclusive maximum value to filter by
    :param limit: The maximum number of results to return
    :param reverse: Sort the list in descending order (true by default)
    occurrences of of that item in the given list"""
    counts = dict()
    for item in items:
        if item not in counts.keys():
            counts[item] = 1
        else:
            counts[item] += 1
    results = counts.items()
    filtered_list = []
    for item in results:
        value = item[order_by]
        if (maximum is None or value >= minimum) and (maximum is None
                                                      or value <= maximum):
            filtered_list.append(item)
    results = filtered_list
    results = sorted(results, key=lambda x: x[order_by], reverse=reverse)
    if limit:
        results = results[:limit]

    return results


if __name__ == "__main__":
    OPTIONS = docopt.docopt(__doc__)
    if OPTIONS['init'] is True:
        init(OPTIONS['<app_key>'].strip(),
             OPTIONS['<app_secret>'].strip())
        print("All set!")
