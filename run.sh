#!/bin/bash

pkill gunicorn > /dev/null 2>&1
pkill celery > /dev/null 2>&1
 
gunicorn --reload -D -w 4 -b 127.0.0.1:8000 tweetfreq:APP
celery worker --config=config > /dev/null 2>&1 &

