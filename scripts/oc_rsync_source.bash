#!/usr/bin/env bash

#
# This script watches for changes and synchronizes current directory contents
# to pods matching 'name' labels given by the command line.
#
# The script is useful when you want to test changes quickly in a development
# environment deployed in OpenShift.
#
# Requires inotifywait
#

EXCLUDE='*.pyc,.idea,.git,target,.vagrant,__pycache__'

if [[ "xxx$1" == "xxx" ]]; then
    echo
    echo "Usage: $0 <pod_name_label_1> [<pod_name_label_2> ...]"
    echo
    echo "  Example: in pebbles source root directory, run"
    echo "    scripts/oc_rsync_source.bash pebbles-api pebbles-worker"
    echo
    exit 1
fi

# loop with a one second backoff
while sleep 1; do
    # synchronize current directory with pods matching given arguments
    for name in $*; do
        pod_name=$(oc get pod -l name=$name | tail -1 | cut -f 1 -d ' ')
        echo
        echo "$(date -Is) rsyncing to $pod_name"
        echo
        oc rsync --exclude=$EXCLUDE . $pod_name:.
    done

    # wait for modifications in files
    inotifywait -r -e modify .

done
