#!/bin/bash

if [ ! -z "$BOOTSTRAP_URL" ]; then
    echo "downloading $BOOTSTRAP_URL"
    su $NB_USER -c "wget $BOOTSTRAP_URL"
    filename=$(basename $BOOTSTRAP_URL)
    case $filename in
        *.bash|*.sh)
            echo "executing $filename"
            /usr/bin/bash $filename
        ;;
    esac
fi

exec /usr/local/bin/start-notebook.sh $*
