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

    ~/.local/bin/python3.12 -m sta_toy.viewer --lib data/toy2.lib --verilog data/s27.v --sdc data/sdc/s27.sdc
    ~/.local/bin/python3.12 -m sta_toy.viewer --bundle out/FF5_D.json

Debugging an endpoint: the table (top) lists every endpoint with its setup and hold slack,
worst setup first, violations in red; click a heading to sort, type in the filter box to
narrow it. Selecting a row shows, for the chosen check (setup / hold), the full path report
and a timeline of launch edge, data arrival, required time and the setup or hold window;
the cone view draws the endpoint's fan-in cone by depth with the worst path in bold
orange, each box giving AT / RAT / slack, and clicking a box lists all its AT / RAT /
SLEW values and its fan-in edges. Raise the depth or max-nodes and press reload to look
further back.
