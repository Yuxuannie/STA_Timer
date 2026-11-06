#!/bin/sh
# Run OpenSTA on one toy design; see docs/contracts/reference.md.
#   ref/opensta/run.sh [--lib LIB] VERILOG SDC OUT_DIR
#   ref/opensta/run.sh --probe
# The binary is $STA_BIN, else ~/tools/opensta/build/sta.  Works from any
# checkout and any working directory (the repo root comes from this file).
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
STA=${STA_BIN:-$HOME/tools/opensta/build/sta}
LIB=$ROOT/data/toy2.lib

if [ ! -x "$STA" ]; then
  echo "error: OpenSTA binary not found: $STA (set STA_BIN)" >&2
  exit 1
fi

abspath() { (cd "$(dirname "$1")" && echo "$(pwd)/$(basename "$1")"); }

if [ "$1" = "--probe" ]; then
  TMP=$(mktemp -d)
  REF_PROBE=1 REF_LIB=$LIB REF_OUT=$TMP "$STA" -no_init -no_splash -exit "$HERE/run.tcl" > "$TMP/sta.log" 2>&1
  rc=$?
  grep -q '^probe ok' "$TMP/sta.log" || rc=1
  if [ $rc -eq 0 ]; then cat "$TMP/version.txt"; else cat "$TMP/sta.log" >&2; fi
  rm -rf "$TMP"
  exit $rc
fi

if [ "$1" = "--lib" ]; then LIB=$2; shift 2; fi
if [ $# -ne 3 ]; then
  echo "usage: ref/opensta/run.sh [--lib LIB] VERILOG SDC OUT_DIR | --probe" >&2
  exit 1
fi
mkdir -p "$3" || exit 1
OUT=$(cd "$3" && pwd)
VERILOG=$(abspath "$1")
TOP=$(basename "$1" .v)
REF_LIB=$(abspath "$LIB") REF_VERILOG=$VERILOG REF_TOP=$TOP REF_SDC=$(abspath "$2") REF_OUT=$OUT \
  "$STA" -no_init -no_splash -exit "$HERE/run.tcl" > "$OUT/sta.log" 2>&1
rc=$?
if [ $rc -ne 0 ] || grep -q '^Error' "$OUT/sta.log"; then
  echo "error: OpenSTA failed on $VERILOG (see $OUT/sta.log)" >&2
  tail -5 "$OUT/sta.log" >&2
  exit 1
fi
exit 0
