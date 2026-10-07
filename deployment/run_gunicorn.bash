#!/usr/bin/env bash

# Instead of using s2i to start gunicorn, we define our own application startup
# script to be able to redirect the access logs to a file instead of stdout.
# This is required for central logging.

# Become the gunicorn process for executing as pid 1 for cleaner processes and better signal handling.
# No control socket: its default path is under $HOME, which the container does not have.
exec gunicorn --bind=0.0.0.0:8080 --no-control-socket ${APP_MODULE}
