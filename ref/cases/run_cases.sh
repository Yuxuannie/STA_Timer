#!/bin/sh
# Run every R40 case (ref/cases/README.md) through OpenSTA, the engine and correlate.py.
#   ref/cases/run_cases.sh            results in ref/results/cases/<case>/
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
PY=${PYTHON:-python3}
cd "$ROOT" || exit 1
run() {  # NAME VERILOG SDC
  out=ref/results/cases/$1
  rm -rf "$out"; mkdir -p "$out"
  ref/opensta/run.sh "$2" "$3" "$out/raw" || return 1
  "$PY" -m sta_toy --lib data/toy2.lib --verilog "$2" --sdc "$3" --dump-tsv "$out/toy" || return 1
  "$PY" ref/opensta/to_golden.py "$out/raw" "$out/opensta" --toy-pins "$out/toy" > /dev/null || return 1
  "$PY" tools/correlate.py "$out/opensta" "$out/toy" > "$out/correlate.txt"
  echo "$1: $(head -1 "$out/correlate.txt")"
}
C=ref/cases
run ck_conventions $C/ck_conventions/reg1.v $C/ck_conventions/ck_slew.sdc
run io_latency $C/io_latency/reg1.v $C/io_latency/latency.sdc
run po_uncertainty $C/po_uncertainty/reg1.v $C/po_uncertainty/po_unc.sdc
run input_delay_max_only $C/input_delay_facets/reg1.v $C/input_delay_facets/max_only.sdc
run input_delay_none $C/input_delay_facets/reg1.v $C/input_delay_facets/no_input_delay.sdc
run tie_break $C/tie_break/tie2.v $C/tie_break/tie.sdc
run s27_aligned data/s27.v $C/aligned/s27_aligned.sdc
run ff2_swap_aligned data/ff2.v $C/aligned/ff2_swap_aligned.sdc
run ff2_unc_aligned data/ff2.v $C/aligned/ff2_unc_aligned.sdc
