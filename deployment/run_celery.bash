#!/usr/bin/env bash

export C_FORCE_ROOT=1

CELERY_CMD=${CELERY_CMD:-worker}
CELERY_LOGLEVEL=${CELERY_LOGLEVEL:-INFO}

case $CELERY_CMD in
    worker)
        celery worker \
            -n $CELERY_PROCESS_NAME \
            -Q $CELERY_QUEUE \
            -A pebbles.tasks.celery_app $CELERY_APP_ARGS \
            -Ofair \
            --loglevel=$CELERY_LOGLEVEL \
            --concurrency=8 \
            --maxtasksperchild=50
    ;;
    beat)
        celery beat \
            -A pebbles.tasks.celery_app $CELERY_APP_ARGS
    ;;
esac