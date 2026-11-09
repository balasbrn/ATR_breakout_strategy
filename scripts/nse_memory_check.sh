#!/bin/sh
set -eu

if [ "$#" -lt 2 ] || [ "$#" -gt 4 ]; then
    echo "Usage: $0 WORK_DIR SCHEMA_JSON [YEARS=1] [SYMBOLS=233]" >&2
    exit 2
fi

work_dir=$1
schema=$2
years=${3:-1}
symbols=${4:-233}
time_bin=${GNU_TIME:-/usr/bin/time}
mkdir -p "$work_dir"

python -m synthetic.generate --nse-memory --years "$years" --symbols "$symbols" --out "$work_dir/fixture"
LC_ALL=C "$time_bin" -v -o "$work_dir/cards.time.txt" \
    atr-bo cards --market NSE --data "$work_dir/fixture/minutes.json" \
    --sessions "$work_dir/fixture/sessions.json" --schema "$schema" --out "$work_dir/cards"

awk -F ': *' '
    /Maximum resident set size \(kbytes\)/ {
        printf "Peak RSS: %d KiB (%.2f GiB)\n", $2, $2 / 1048576
        found = 1
    }
    END { if (!found) exit 1 }
' "$work_dir/cards.time.txt"
