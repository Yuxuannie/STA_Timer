# R40 smallest cases (OpenSTA 3.1.0 vs the engine)

Each directory holds a netlist and SDC small enough to read by hand, for one class of
difference found by `ref/run_all.sh` on the nine designs. P5-1a (CK-pin slew / arrival) is an
`adapter` gap: OpenSTA's analysis uses the toy's values, its pin properties do not; the others
are `policy` (both tools consistent with their own rules); none is a toy bug.
Write-up, both tools' values and what would change: `REPORT_P5.md` §7.

Run one case (from the repo root; `D` = case directory, `V` = its .v, `S` = its .sdc):

    ref/opensta/run.sh ref/cases/D/V ref/cases/D/S ref/results/cases/D/raw
    python3 -m sta_toy --lib data/toy2.lib --verilog ref/cases/D/V --sdc ref/cases/D/S --dump-tsv ref/results/cases/D/toy
    python3 ref/opensta/to_golden.py ref/results/cases/D/raw ref/results/cases/D/opensta --toy-pins ref/results/cases/D/toy
    python3 tools/correlate.py ref/results/cases/D/opensta ref/results/cases/D/toy

`ref/cases/run_cases.sh` does this for every case. `aligned/` holds copies of three P2 SDC
files with the P5-2 .. P5-4 policies neutralised (latency, PO uncertainty, unset input-delay
facets); with them every non-CK cell of s27, ff2_swap and ff2_unc agrees within 1 ps,
which is the evidence that no other class hides under those three
(`tests/test_ref_cases.py`).

| dir | class | §7 |
|---|---|---|
| ck_conventions | CK-pin slew (P5-1a, adapter) and CK fall / clock-port values (P5-1b) under an ideal clock | P5-1 |
| io_latency (FF1/CK row) | CK-pin arrival with latency | P5-1a |
| io_latency | ideal clock latency on input / output delays | P5-2 |
| po_uncertainty | clock uncertainty on output-port checks | P5-3 |
| input_delay_facets | unset `set_input_delay` facets (`-max` only; none at all) | P5-4 |
| tie_break | equal-arrival candidates | P5-5 |
