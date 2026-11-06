# Reference tool (contract, P5)

OpenSTA runs the toy's own inputs (Liberty, Verilog, SDC) and its results are
rewritten in the golden format (`golden_format.md`), so the engine, the P2
oracle and OpenSTA can be compared with the same tools. OpenSTA is the
reference, not the truth: differences are classified by R40, never "fixed"
here.

Pipeline for one design `D` (Verilog `V`, SDC `S`):

```
ref/opensta/run.sh V S ref/results/D/raw          # OpenSTA -> raw dump
python3 ref/opensta/to_golden.py ref/results/D/raw ref/results/D/opensta
python3 -m sta_toy --lib data/toy2.lib --verilog V --sdc S --dump-tsv ref/results/D/toy
python3 tools/correlate.py ref/results/D/opensta ref/results/D/toy --design V --lib data/toy2.lib
```

`ref/run_all.sh` does this for the eight P2 designs and `s1423`.
Everything under `ref/results/` is git-ignored.

## `ref/opensta/run.sh`

```
ref/opensta/run.sh [--lib LIB] VERILOG SDC OUT_DIR
ref/opensta/run.sh --probe
```

- Finds the binary: `$STA_BIN` if set, else `~/tools/opensta/build/sta`.
- Resolves the repo root from its own location, so it works from any
  checkout and any working directory. `--lib` defaults to
  `<repo>/data/toy2.lib`. The top module is the Verilog file's base name.
- Runs `sta -no_init -no_splash -exit ref/opensta/run.tcl` with the inputs
  passed in environment variables (`REF_LIB`, `REF_VERILOG`, `REF_TOP`,
  `REF_SDC`, `REF_OUT`), writes OpenSTA's log to `OUT_DIR/sta.log`, and exits
  with OpenSTA's exit code (1 if the binary is missing).
- `--probe` exits 0 only if the binary exists and `read_liberty
  data/toy2.lib` succeeds; it prints the OpenSTA version. Tests use it to
  decide whether to skip.

## `ref/opensta/run.tcl`

`read_liberty`, `read_verilog`, `link_design`, then the toy's SDC file is read
with `read_sdc` unchanged. Settings chosen to match the toy's model
(`p2_semantics.md`):

| setting | why |
|---|---|
| ideal clocks (no `set_propagated_clock`) | the toy's clock net is not timed (§2, §5) |
| no parasitics, no wire load | the toy's LOAD is pin capacitance + `set_load` (§2) |
| `set_delay_calculator lumped_cap` when the command exists | NLDM lookup at the lumped load, the toy's §3 |
| `set_cmd_units -time ns -capacitance pF` | `toy2.lib` units, no conversion (§0) |

Any adaptation of an SDC construct OpenSTA rejects is listed in
`ref/README.md` with the reason; none of the SDC files is edited (N34).

It writes three raw files into `OUT_DIR`:

- `version.txt`: `sta::version`, and `sta::git_sha1` when it exists.
- `pins.tsv` (raw, OpenSTA user units, 6 digits as OpenSTA prints them):
  `name kind at_max_r at_max_f at_min_r at_min_f slack_max_r slack_max_f
  slack_min_r slack_min_f slew_max_r slew_max_f slew_min_r slew_min_f`, one
  row per top-level port (`kind = port`, through its top-level pin) and per
  instance pin (`kind = pin`; pins with direction `internal`, the Liberty
  `ff` nodes `IQ` / `IQN`, are skipped), from `get_property` (`arrival_*`,
  `slack_*`, `slew_*`). OpenSTA's text for an undefined or infinite value is
  kept as is.
- `paths.txt` (raw): for every path end of `find_timing_paths -path_delay
  max` and `min` with `-group_path_count 1000000 -endpoint_path_count 1`, a
  line `END <endpoint> <setup|hold> <slack>` followed by one line
  `PT <pin> <edge> <arrival>` per point of `get_property $end points`, in path
  order. A register path's points start at Q; its launching CK pin (the pin
  before Q in the path's pin chain `[$path pins]`) is written first as
  `PT <CK pin> ^ NA`: the clock network before it (the clock port) is left out,
  as the toy's clock net is not timed, and the edge is not reachable from Tcl,
  so rise is written, which holds for `toy2.lib` (only `rising_edge` flops).
- `units.txt`: `report_units`.
- `report_max.txt`, `report_min.txt`: `report_checks -format
  full_clock_expanded -fields {input_pins slew capacitance fanout} -digits 6`
  over the same paths, for people only (no tool reads them).

## `ref/opensta/to_golden.py RESULTS_DIR OUT_DIR`

Writes `endpoints.tsv`, `pins.tsv`, `paths.txt` exactly in
`golden_format.md` (fmt4, `NA`, sorted rows) from the raw files:

- A raw value is undefined (`NA`) when it is not a finite number or its
  magnitude is at least 1e10 (OpenSTA's INF / -INF).
- `at_late_* = arrival_max_*`, `at_early_* = arrival_min_*`,
  `slew_late_* = slew_max_*`, `slew_early_* = slew_min_*`.
- Required times are not exposed per pin, so they come from slack:
  `rat_late = at_late + slack_max`, `rat_early = at_early - slack_min`, per
  rf, defined only when both terms are.
- Endpoints are the endpoints of the raw `paths.txt` (an endpoint whose path
  end appears in either check). For each check the worst transition `rf*` is
  the one with the smaller pin slack (`slack_max_*` for setup, `slack_min_*`
  for hold), ties (|Δ| < 1e-9) to `r`, exactly as `p2_semantics.md` §9; its
  three cells are `AT`, `RAT`, slack of that rf; `NA` if neither rf has a
  slack.
- `paths.txt`: one line per raw `END` record, endpoints in name order, setup
  before hold, `<endpoint> <check> <slack> : n(rf) -> ...` with `^` / `rise`
  read as `r` and `v` / `fall` as `f`.
- With `--toy-pins DIR` (a toy `--dump-tsv` directory, optional; `ref/run_all.sh`
  passes it): the row set of `pins.tsv` becomes the union of both tools' pins.
  A pin only one tool has is written as an all-`NA` row in the other's file and
  listed in `RESULTS_DIR/../missing.txt` as `opensta-only <pin>` or
  `toy-only <pin>`; the same for endpoints. Without `--toy-pins`, nothing is
  added.

## `tools/correlate.py GOLDEN_DIR ACTUAL_DIR [--tol T] [--design V --lib L]`

Compares two golden-format directories; `GOLDEN_DIR` is the reference.
Exit 0 when every numeric cell is within `T` (default 0.001 ns = 1 ps),
every `NA` matches, the row sets match and every path matches; 1 otherwise.

Printed, in this order:

1. `PASS` or `FAIL` with the counts of failing cells, rows and paths.
2. Per column of `pins.tsv` and of `endpoints.tsv`: `count` (cells where both
   sides are numbers), `max|d|`, `mean|d|`, `over` (count over `T`), `na`
   (cells where exactly one side is `NA`).
3. The 20 largest |Δ| over both files: file, pin, column, golden value,
   actual value, Δ (actual − golden).
4. Pins only in one file (each file), at most 20 listed, with the counts.
5. Paths: compared per `<endpoint> <check>` as node sequences (names and rf);
   lines `path-mismatch <endpoint> <check>` with both sequences (at most 20),
   then counts of matching / mismatching / missing paths. Path slacks are
   compared numerically with `T`.
6. With `--design V --lib L`: mean |Δ| of `pins.tsv` over all numeric columns
   grouped by cell type (the cell of the pin's instance; `port` for ports) and
   by logic level: level 0 is a PI, the clock port or a CK pin (a pin named
   by a Liberty `clock : true`); an instance input pin or an output port has
   the level of its net's driver; an instance output pin has 1 + the maximum
   level of the `related_pin`s of the `timing ()` groups inside its Liberty
   pin group (a gate is one level; CK→Q gives Q level 1). A pin whose level
   cannot be found (a loop, an unknown cell) is grouped as `?`. The grouping
   reads the Verilog and the Liberty with its own small readers and does not
   import `sta_toy`.

## Test rules

- `tests/test_ref.py` is skipped unless `ref/opensta/run.sh --probe` exits 0.
  It checks that `to_golden.py` output for `ff2_default` is well formed and
  that its pin and endpoint sets equal the engine's. Numeric agreement is not
  asserted here (R40).
- `to_golden.py` and `correlate.py` are also tested without OpenSTA, on
  hand-made raw files and on perturbed copies of the P2 golden directories.

## Known gaps

- The launching CK pin's edge in `paths.txt` is written as rise (see above).
- `get_property` reports the graph's values at clock pins under an ideal
  clock: CK pin slew 0 when the clock port has no input transition (the
  `report_checks` text shows `set_clock_transition` there), CK pin arrival
  without the ideal latency, a fall arrival at half the period, and values at
  the clock port. They are written as OpenSTA gives them; R40 classifies them.
- Route, version and the differences seen in the first runs are in
  `ref/README.md`.
