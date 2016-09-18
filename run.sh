#!/bin/bash

pkill gunicorn > /dev/null 2>&1
pkill celery > /dev/null 2>&1
 
/usr/local/bin/gunicorn -D --reload -w 4 -b 127.0.0.1:8000 tweetfreq:APP 
celery worker --autoreload --config=config > /dev/null 2>&1 &

