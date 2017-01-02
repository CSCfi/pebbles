#!/bin/bash

# bail out on non-zero exit codes
set -e

DB_FILE=/webapps/pebbles/run/db.sqlite

if [ "xxx$1" == "xxx" ]; then
  echo "Usage: $0 <database_backup_file>"
  exit 1
fi

backup_file=$1

if [ ! -e $backup_file ]; then
  echo "Backup file $backup_file not found"
  exit 1
fi

current_date=$(/bin/date --iso-8601=seconds)
current_ts=$(/bin/date +%s)

echo "Stopping api container"
docker stop api

echo "Renaming current database"
echo "ALTER DATABASE pebbles RENAME TO pebbles_$current_ts" | docker exec -i db psql -U postgres

echo "Creating a blank database"
echo "CREATE DATABASE pebbles" | docker exec -i db psql -U postgres

echo "Loading backup $backup_file into database"
zcat $backup_file | docker exec -i db psql -d pebbles -U postgres

echo "Starting api container"
docker start api
