#!/bin/sh
# OpenSTA vs the engine on the eight P2 designs and s1423; see docs/contracts/reference.md.
#   ref/run_all.sh [DESIGN ...]          (default: all nine)
# Per design D: ref/results/D/{raw,opensta,toy,missing.txt,correlate.txt}.
# PYTHON overrides the interpreter (default python3).
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
PY=${PYTHON:-python3}
cd "$ROOT" || exit 1

design_files() {
  case $1 in
    ff2_*) echo "data/ff2.v data/sdc/$1.sdc" ;;
    inv2) echo "data/inv2.v data/sdc/inv2.sdc" ;;
    s27) echo "data/s27.v data/sdc/s27.sdc" ;;
    s1423) echo "data/s1423.v data/sdc/s1423.sdc" ;;
    *) return 1 ;;
  esac
}

DESIGNS=${*:-"ff2_default ff2_swap ff2_setupviol ff2_holdviol ff2_skew ff2_unc inv2 s27 s1423"}
status=0
for d in $DESIGNS; do
  files=$(design_files "$d") || { echo "error: unknown design $d" >&2; exit 1; }
  set -- $files
  out=ref/results/$d
  rm -rf "$out"; mkdir -p "$out"
  if ! "$HERE/opensta/run.sh" "$1" "$2" "$out/raw"; then status=1; continue; fi
  "$PY" -m sta_toy --lib data/toy2.lib --verilog "$1" --sdc "$2" --dump-tsv "$out/toy" || { status=1; continue; }
  "$PY" "$HERE/opensta/to_golden.py" "$out/raw" "$out/opensta" --toy-pins "$out/toy" || { status=1; continue; }
  "$PY" tools/correlate.py "$out/opensta" "$out/toy" --design "$1" --lib data/toy2.lib > "$out/correlate.txt"
  echo "$d: $(head -1 "$out/correlate.txt")"
done
exit $status
