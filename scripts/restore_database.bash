#!/bin/bash

# bail out on non-zero exit codes
set -e

DB_FILE=/webapps/pouta_blueprints/run/db.sqlite

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

echo "Stopping gunicorn http server workers"
ssh www sudo supervisorctl stop gunicorn_app

echo "Creating a copy of old database file"
ssh www sudo cp $DB_FILE $DB_FILE.$current_date

echo "Truncating database"
ssh www sudo truncate --size 0 $DB_FILE

echo "Loading backup $backup_file into database"
zcat $backup_file | ssh www sudo sqlite3 $DB_FILE

echo "Starting gunicorn http server workers"
ssh www sudo supervisorctl start gunicorn_app

