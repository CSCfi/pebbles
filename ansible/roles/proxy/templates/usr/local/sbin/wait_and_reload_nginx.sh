#!/bin/bash

inotifywait -e modify,close_write,moved_to,create $1

/etc/init.d/nginx reload
