#!/usr/bin/env bash

# Instead of using s2i to start gunicorn, we define our own application startup
# script to be able to redirect the access logs to a file instead of stdout.
# This is required for central logging.

/opt/app-root/bin/python3 /opt/app-root/bin/gunicorn --bind=0.0.0.0:8080 ${APP_MODULE}
