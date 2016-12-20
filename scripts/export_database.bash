#!/bin/bash

# bail out on non-zero exit codes
set -e

# did we get a filename as an argument?
if [ "xxx$1" == "xxx" ]; then
  # nope, make one up
  export_date=$(/bin/date --iso-8601=seconds)
  export_file=postgresql.$export_date.gz
else
  export_file=$1
fi

if [ -e $export_file ]; then
  echo "Export file $export_file already exists, remove it first"
  exit 1
fi

echo "Exporting to $export_file"

docker exec db pg_dump -d pebbles -U postgres | gzip -c > $export_file
