#!/bin/bash

if [ "$#" -ne 1 ]; then
        echo "filename to watch is missing"
        exit 1
fi

while [ -e $1 ]; do
        now=$(date --rfc-3339=seconds); now=${now%\n}
        echo "$now waiting for changes in $1"

        inotifywait -q -t 60 -e modify,close_write,moved_to,create $1

        /etc/init.d/nginx reload
done

now=$(date --rfc-3339=seconds); now=${now%\n}
echo "$now exiting"
