#!/bin/sh

MYDIR="$(dirname "$0")"
. "$MYDIR/venv/bin/activate"

YEAR="${1:-$(date +%Y)}"
FILENAME="$MYDIR/amazon-$YEAR"

set -x
python3 "$MYDIR/amazon_orders.py" -v -j "$FILENAME.json" -c "$FILENAME.csv" --single_year "$YEAR"