# Toy STA, stage 1

Parses a Liberty library and a flat gate-level Verilog netlist, links them into a
pin-level timing graph and prints it as text. Python 3.8+, standard library only.

    python -m sta_toy --lib data/toy.lib --verilog data/c17.v
    python -m unittest discover -s tests

Run both from the repo root. Errors go to stderr as `ERROR <file>:<line>: <message>`, exit code 1.

## Timing analysis (stage P2)

With `--sdc` the tool times a flat design with D flip-flops under one ideal clock
(rules: `docs/contracts/`) and writes three files instead of printing the graph:

    python -m sta_toy --lib data/toy2.lib --verilog data/ff2.v \
        --sdc data/sdc/ff2_default.sdc --dump-tsv out/ff2_default

`--sdc` needs at least one output option (`--dump-tsv`, `--report-timing`,
`--report-summary`, `--json`, `--bundle`; see below); `--lib` may repeat. With only
`--dump-tsv` stdout stays empty. Any error is one line on stderr with exit code 1.

| file | content |
|---|---|
| `endpoints.tsv` | one row per D pin and constrained output port: setup and hold AT, RAT, slack at the worst transition |
| `pins.tsv` | every port and pin: AT, RAT and slew for late/early × rise/fall (`NA` = undefined) |
| `paths.txt` | the worst setup and hold path of each endpoint, traced through the predecessors |

Worked example, `ff2_default` (period 10, `FF2/D` captures the NAND of `FF1/Q` and the
buffered input `x`):

    $ cat out/ff2_default/endpoints.tsv
    pin	setup_at	setup_rat	setup_slack	hold_at	hold_rat	hold_slack
    FF1/D	1.0000	9.7000	8.7000	1.0000	0.1000	0.9000
    FF2/D	4.0000	9.7000	5.7000	3.0000	0.1000	2.9000
    y	1.0000	8.0000	7.0000	1.0000	-0.5000	1.5000
    $ grep FF2/D out/ff2_default/paths.txt
    FF2/D setup 5.7000 : x(f) -> U1/A(f) -> U1/Y(f) -> U2/B(f) -> U2/Y(r) -> FF2/D(r)
    FF2/D hold 2.9000 : FF1/CK(r) -> FF1/Q(f) -> U2/A(f) -> U2/Y(r) -> FF2/D(r)

The slow route through `x` (arrival 4.0) sets the setup slack 9.7 − 4.0; the fast route from
`FF1` (arrival 3.0) sets the hold slack 3.0 − 0.1. Compare any run with its golden files:

    python3 tools/diff_ref.py tests/golden/ff2_default out/ff2_default --tol 0

Tests (stage 1 and P2, including all eight golden designs): `python3 -m unittest discover -s tests`.

## Reports, JSON and the debug viewer (stages P3, P4)

Rules: `docs/contracts/report_p3.md`, `json_v1.md`, `bundle_v1.md`, `viewer_p4.md`,
`cli_p3.md` (overview in `SPEC_P3P4.md`).

    # PrimeTime-style path reports: worst setup path, or K worst paths of N endpoints
    python -m sta_toy --lib data/toy2.lib --verilog data/s27.v --sdc data/sdc/s27.sdc \
        --report-timing --max-paths 2 --nworst 3 --transition-time --capacitance
    # hold paths into one pin, only those through a given pin
    python -m sta_toy ... --report-timing --path-delay min --to FF5/D --through U14/Y
    # WNS / TNS / NVP for setup and hold
    python -m sta_toy ... --report-summary
    # everything as JSON (schema sta_toy.report/1), and one endpoint's fan-in cone
    python -m sta_toy ... --json out/s27.json --bundle FF5/D --bundle-out out/FF5_D.json --depth 4

The viewer needs a Python with a working Tk. On this Mac the system `/usr/bin/python3`
(Tk 8.5) aborts when it opens a window; `~/.local/bin/python3.12` (Tk 9.0) works:

    ~/.local/bin/python3.12 -m sta_toy.viewer --lib data/toy2.lib --verilog data/s27.v --sdc data/sdc/s27.sdc --theme dark
    ~/.local/bin/python3.12 -m sta_toy.viewer --bundle out/FF5_D.json

Debugging an endpoint: on the left, the slack histogram of the check chosen in the header
(Setup / Hold; click a bar to filter) and every endpoint, worst slack first. The centre opens
with the endpoint's slack worked out term by term (input delay or launch latency + ck→q + data
path = arrival; edge + capture latency − setup time − uncertainty = required, or + hold time +
uncertainty for hold), then three
views of the worst path: *Schematic* (gate symbols wired pin to pin, the critical path in the
accent colour, each cell's `+delay`, each output's arrival), *Waveform* (both clocks, the data
window, the setup and hold windows and slacks) and *Profile* (where the path spends its time),
and under them the path table in three sections (source clock, data path, destination clock)
with load, slew, incr, AT, RAT and pin slack. ←/→ walk the signal pin to pin, ↑/↓ change
endpoint, S / H the check, 1 / 2 / 3 the view. A side input ends in ⊕: click it to draw the
cell driving it (and keep digging backwards); ↺ marks a side input whose driver is already on
screen. Click a pin: the inspector shows its AT / RAT / slew, the lookup behind its delay
(input slew and load → delay) and which input set its arrival and which fanout set its
required time, with each loser's margin. Drag any divider to resize; `[` and `]` hide the side
panels. Themes: light, dark, contrast (header switch or `--theme`).

## Engine health, trace and units (stage P5)

Rules: `docs/contracts/cli_p5.md`, `check_timing.md`, `trace.md`, `p2_semantics.md` "Changes in P5".

    python -m sta_toy --lib data/toy2.lib --verilog data/s27.v --sdc data/sdc/s27.sdc --check-timing
    python -m sta_toy --lib data/toy2.lib --verilog data/ff2.v --sdc data/sdc/ff2_default.sdc --trace FF2/D

**check_timing.** `--check-timing` (with `--sdc`) prints what the run left
unconstrained or could not time: outputs without `set_output_delay`, registers whose CK
pin is not on the clock net, inputs without `set_input_delay` / `set_input_transition`,
outputs without `set_load`, the `timing()` groups the timer ignored, and how many table
lookups fell outside their grid (per table kind and axis). A run that ignored any
`timing()` group (recovery, removal, min_pulse_width, falling_edge, ...) still succeeds
and prints one warning line on stderr.

**Library units.** Every library must declare `time_unit` and
`capacitive_load_unit`. The first `--lib` sets the units of the run (SDC values and
every output); a further library in other units (say ps / fF) is converted to them
when loaded. `python3 tools/gen_toy2_lib.py --time ps --cap ff --suffix _P` writes a
ps / fF copy of toy2.lib with suffixed cell names to try it.

**trace.** `--trace PIN` prints, for one endpoint, the engine's own log of how its
values were obtained: every forward merge in its fan-in cone with each candidate
(`AT + delay = value`, the winner marked `*`), the check (constraint, clock arrival,
period, uncertainty), every backward merge, the endpoint's slacks and its worst setup
and hold paths. The numbers are the engine's, logged as it computed them.
