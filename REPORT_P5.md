STATUS: IN PROGRESS — phase 5 (all three merged; R40 done; reviewer next)
Branch p5-ref @ (see `git log`); worker branches p5-viewer @ 785073d, p5-engine @ 1f97fe7, p5-opensta @ 4b33b9e (all merged with --no-ff); started 2026-11-05 21:46 CST, last update 2026-11-05 23:10 CST

## 1. Result table
| ID | status (done / partial / skipped) | commit(s) | note |
|----|-----------------------------------|-----------|------|
| R32 | done | 98ef8a2, 7451c05 (merged) | W1; window from the screen, one scale `s` (`--scale`, `px()`, `font()`), overlap + cut-off check at 3 scales × 3 widths × 8 designs |
| R33 | done | 98ef8a2, c394ca0 (merged) | W1; Profile removed, largest incr bold, bundles without instances an error again, edge labels in `model.waveform`, near-critical = 1 % of period |
| R34 | done | 98ef8a2, 05a00e3, 785073d (merged), b46e9df (lead: bundle `fanout`) | W1; lookup grid (engine mode only: bundles hold no tables), FANOUT column and inspector `fanout` |
| R35 | done | d399f2a, 59d4fbc (merged) | W2; ignored arcs counted, `--check-timing` |
| R36 | done | d399f2a, ce8eee3 (merged) | W2; `--trace PIN` from the engine log |
| R37 | done | a50ce00, 1f97fe7 (merged) | W2; both protected libraries already declare ns / pF |
| R38 | done | 5b312c9 (merged) | W3; s1423 from a public mirror, 748 instances, period 75.6 |
| R39 | done | 66632d7, 8b8af9b, 4b33b9e (merged), 588f756 (lead: run.sh path fix) | W3; OpenSTA 3.1.0 source build in 25 of 90 min; s1423 kept as a snapshot (oracle rule) |
| R40 | done | 3ff042e | lead; 5 policy classes, 0 toy-bug, 0 adapter (numbers); cases in `ref/cases/` |
| R41 | pending | | lead, optional |
| R42 | pending | | lead, optional |
| R43 | pending | | lead |

## 2. Tests
before (viewer-v2 @ ed316ad): 155 (4 skipped) on /usr/bin/python3 (3.9.6), 155 (1 skipped) on ~/.local/bin/python3.12
after interface commit bbb685d: 159 (4 skipped) / 159 (1 skipped) — 4 new lookup_detail tests
after merge of p5-engine: 183 (4 skipped) / 183 (1 skipped)
after merge of p5-viewer + bundle fanout: 194 (6 skipped) / 194 (2 skipped)
after merge of p5-opensta + R40 cases: 214 (6 skipped) / 214 (1 skipped) — the OpenSTA tests (test_ref.OpenStaTests, test_ref_cases) and the s1423 Tk smoke test run
skips: /usr/bin/python3 skips the 5 `TkSmokeTests` (Tk cannot open a window) and `ViewerCliTests.test_no_tkinter` (this Python has tkinter); python3.12 skips only `test_no_tkinter`
time: /usr/bin/python3 ≈ 11 s; python3.12 ≈ 190 s (almost all in W1's mapped-window overlap / cut-off check)
commands:
    /usr/bin/python3 -m unittest discover -s tests
    ~/.local/bin/python3.12 -m unittest discover -s tests

## 3. Viewer
- `--scale S` (0.6–2.0; out of range or not a number: one stderr line, exit 1). Default 1.0 on aqua, else `tk scaling · 72/96` clamped. Pixel constants via `px()` (× s), fonts via `font()` (× s / s_default; on aqua × s — W1 decision, §6.6).
- Window: width `min(1520·s, 0.92·screen)`, height `min(940·s, 0.90·screen)`, centred; `minsize` from the pane minimums at s (1066×414 at s = 1). On 1280×800 at s = 1 the window is 1177×720 (`sizing.geometry`, `test_viewer.SizingTests`).
- Screenshots: none. `screencapture` exits 0 but records only the wallpaper (this process has no Screen Recording permission); W1 stopped after one try as the brief says.
- Removed: the Profile view (key `3` unbound, reserved for R41), `model.profile`, its tests and contract text; the compatibility path for bundles without `instances` (now `error: bundle has no instances: write it again with --bundle`, exit 1) and `source.note`.
- Added: largest data-path cell `INCR` in bold; waveform rising-edge labels (`ff2_holdviol` `FF2/D` capture: `3.5000`, `13.5000`); near-critical threshold 1 % of the period shown as `near-critical: margin < 0.1000`; lookup grid under each lookup (engine mode); FANOUT column and inspector `fanout`.
- s1423 Tk smoke test (open, worst setup endpoint, both views, 3 steps, Hold, `[`, `]`): 1.09 s against the 10 s bound (`~/.local/bin/python3.12 -m unittest -v tests.test_viewer.TkSmokeTests.test_s1423_in_10_seconds`).

## 4. OpenSTA correlation
Install: route 2 (Docker is not available on this Mac), OpenSTA **3.1.0**, commit `444cfc701ce34e0cf3dc73bbad3a9c2b56ad8c08` (The-OpenROAD-Project/OpenSTA), binary `~/tools/opensta/build/sta`, built from source with Homebrew `cmake`, `swig`, `tcl-tk@8` (built from source: Tier 3 Intel macOS), `bison`, `flex`, `eigen` and CUDD 3.0.0 under `~/tools/cudd`; 25 of the 90 minutes. Details: `ref/README.md`.
Settings (`ref/opensta/run.tcl`): ideal clocks, no parasitics, `set_delay_calculator lumped_cap`, the toy's own SDC files unchanged (all nine read without a warning); per-pin values through `get_property`, paths through `find_timing_paths`.
Run: `ref/run_all.sh` (3.6 s for all nine; re-run on the merged p5-ref, identical to W3's run). Pin and endpoint sets are identical on all nine designs (`ref/results/<d>/missing.txt` empty).

Cell = max |Δ| / over 1 ps / one-sided NA; Δ = engine − OpenSTA (`correlate.py` with OpenSTA as GOLDEN).

| file · column | ff2_default | ff2_swap | ff2_setupviol | ff2_holdviol | ff2_skew | ff2_unc | inv2 | s27 | s1423 |
|---|---|---|---|---|---|---|---|---|---|
| pins · at_late_r | 0.0000 / 0 / 1 | 1.5000 / 6 / 1 | 0.0000 / 0 / 1 | 3.5000 / 1 / 1 | 0.5000 / 1 / 1 | 0.0000 / 0 / 1 | 0.0000 / 0 / 1 | 0.2000 / 29 / 1 | 0.0001 / 0 / 1 |
| pins · at_late_f | 0.0000 / 0 / 3 | 0.3000 / 4 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 2 | 0.2000 / 26 / 4 | 0.0001 / 0 / 75 |
| pins · at_early_r | 0.0000 / 0 / 1 | 1.5000 / 8 / 1 | 0.0000 / 0 / 1 | 3.5000 / 1 / 1 | 0.5000 / 1 / 1 | 0.0000 / 0 / 1 | 0.0000 / 0 / 1 | 2.5000 / 18 / 3 | 0.0000 / 0 / 1 |
| pins · at_early_f | 0.0000 / 0 / 3 | 0.3000 / 6 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 2 | 2.2800 / 15 / 6 | 0.0000 / 0 / 75 |
| pins · rat_late_r | 0.0000 / 0 / 1 | 0.3000 / 3 / 1 | 0.0000 / 0 / 1 | 0.0000 / 0 / 1 | 0.0000 / 0 / 1 | 0.5000 / 3 / 1 | 0.0000 / 0 / 1 | 0.1000 / 30 / 3 | 0.0001 / 0 / 1 |
| pins · rat_late_f | 0.0000 | 0.3000 / 2 / 0 | 0.0000 | 0.0000 | 0.0000 | 0.5000 / 2 / 0 | 0.0000 | 0.1000 / 27 / 2 | 0.0001 |
| pins · rat_early_r | 0.0000 / 0 / 1 | 0.3000 / 1 / 1 | 0.0000 / 0 / 1 | 0.0000 / 0 / 1 | 0.0000 / 0 / 1 | 0.3000 / 1 / 1 | 0.0000 / 0 / 1 | 1.1000 / 7 / 5 | 0.0000 / 0 / 1 |
| pins · rat_early_f | 0.0000 | 0.3000 / 1 / 0 | 0.0000 | 0.0000 | 0.0000 | 0.3000 / 1 / 0 | 0.0000 | 1.1000 / 7 / 4 | 0.0000 |
| pins · slew_late_r | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 1 / 1 | 0.0000 / 0 / 1 | 0.0500 / 74 / 1 |
| pins · slew_late_f | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 2 | 0.0000 / 0 / 4 | 0.0000 / 0 / 75 |
| pins · slew_early_r | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 2 / 1 | 0.0500 / 1 / 1 | 0.0000 / 0 / 1 | 0.0500 / 74 / 1 |
| pins · slew_early_f | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 3 | 0.0000 / 0 / 2 | 0.0000 / 0 / 4 | 0.0000 / 0 / 75 |
| endpoints · setup_at | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2000 / 3 / 0 | 0.0001 |
| endpoints · setup_rat | 0.0000 | 0.3000 / 1 / 0 | 0.0000 | 0.0000 | 0.0000 | 0.5000 / 1 / 0 | 0.0000 | 0.1000 / 1 / 0 | 0.0001 |
| endpoints · setup_slack | 0.0000 | 0.3000 / 1 / 0 | 0.0000 | 0.0000 | 0.0000 | 0.5000 / 1 / 0 | 0.0000 | 0.2000 / 3 / 0 | 0.0001 |
| endpoints · hold_at | 0.0000 | 0.3000 / 1 / 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2000 / 2 / 0 | 0.0000 |
| endpoints · hold_rat | 0.0000 | 0.3000 / 1 / 0 | 0.0000 | 0.0000 | 0.0000 | 0.3000 / 1 / 0 | 0.0000 | 0.0000 | 0.0000 |
| endpoints · hold_slack | 0.0000 | 0.3000 / 2 / 0 | 0.0000 | 0.0000 | 0.0000 | 0.3000 / 1 / 0 | 0.0000 | 0.2000 / 2 / 0 | 0.0000 |

Paths (node sequences; `slack over tol` = same sequence, slack differs by more than 1 ps):

| design | same | mismatch | OpenSTA only | engine only | slack over tol | first line of correlate.txt |
|---|---|---|---|---|---|---|
| ff2_default | 6 | 0 | 0 | 0 | 0 | `FAIL  tol 0.001  cells over/NA 22  rows only one side 0  paths bad 0` |
| ff2_swap | 6 | 0 | 0 | 0 | 3 | `FAIL  tol 0.001  cells over/NA 59  rows only one side 0  paths bad 3` |
| ff2_setupviol | 6 | 0 | 0 | 0 | 0 | `FAIL  tol 0.001  cells over/NA 22  rows only one side 0  paths bad 0` |
| ff2_holdviol | 6 | 0 | 0 | 0 | 0 | `FAIL  tol 0.001  cells over/NA 24  rows only one side 0  paths bad 0` |
| ff2_skew | 6 | 0 | 0 | 0 | 0 | `FAIL  tol 0.001  cells over/NA 24  rows only one side 0  paths bad 0` |
| ff2_unc | 6 | 0 | 0 | 0 | 2 | `FAIL  tol 0.001  cells over/NA 33  rows only one side 0  paths bad 2` |
| inv2 | 4 | 0 | 0 | 0 | 0 | `FAIL  tol 0.001  cells over/NA 16  rows only one side 0  paths bad 0` |
| s27 | 7 | 0 | 0 | 0 | 5 | `FAIL  tol 0.001  cells over/NA 208  rows only one side 0  paths bad 5` |
| s1423 | 134 | 24 | 0 | 0 | 0 | `FAIL  tol 0.001  cells over/NA 454  rows only one side 0  paths bad 24` |

Reading the table (classes from §7; every cell over 1 ps is accounted for):
- ff2_default, ff2_setupviol, inv2, s1423: only P5-1 (CK-pin slew 0.05 vs 0, CK-pin / clock-port fall arrivals and clock-port values, the one-sided NA counts). All endpoints and all data pins agree.
- ff2_holdviol, ff2_skew: P5-1 plus the CK-pin arrival with pin latency (3.5, 0.5): OpenSTA's pin `arrival` property excludes ideal latency, its checks include it (report: "clock network delay (ideal) 3.5"). Endpoints agree.
- ff2_swap: P5-1 and P5-2 (clock-level latency 0.3 on the input delay of `x` and on the required time of `y`); the 3 path slacks over tol follow from it.
- ff2_unc: P5-1 and P5-3 (`y`: setup RAT 7.5 vs 8.0, hold RAT −0.2 vs −0.5).
- s27: P5-1, P5-2 (latency 0.2 on G0/G2/G3 arrivals and G17's RAT), P5-3 (G17 setup uncertainty), P5-4 (G1 without input delay and G3 with `-max` only are undefined for OpenSTA's early analysis, 0 for the toy: early values downstream differ by up to 2.5).
- s1423: data columns within 0.0001 (6-digit → fmt4 rounding), including 24 out-of-grid load lookups above the table (`--check-timing`), so OpenSTA extrapolates linearly there as the toy does (ROADMAP D9, extrapolation part: agrees). 24 of 158 paths differ in sequence, all with equal slack (max |Δ| 0.0001): P5-5.
- Evidence that nothing else hides: with P5-2..P5-4 neutralised in copies of the SDC files (`ref/cases/aligned/`), every non-CK cell of s27, ff2_swap and ff2_unc agrees within 1 ps and every path matches (`tests/test_ref_cases.py::test_aligned_designs_have_no_other_difference`).

s1423: **snapshot**, not golden (`tests/snapshot/s1423/`, byte-exact test `test_ref.S1423SnapshotTests`). The brief's oracle rule needs the eight small designs within 1 ps on every column; P5-1 alone fails that on all eight. If the owner aligns P5-1 (or decides the adapter should report OpenSTA's clock-path values for CK pins), s1423 qualifies: its data columns already agree within 0.0001 and only P5-1 / P5-5 differ.

Adapter defect found and fixed (588f756): `ref/opensta/run.sh` passed the absolute `run.tcl` path to `sta -exit`, which splits a path with a space; from the main checkout (`7-STA Timer`) every run failed and `test_ref.OpenStaTests` skipped instead of running. Not a numeric adapter issue.

## 5. Engine
`--check-timing` on s27 (`tests/golden/check_timing/s27.txt`, hand-reviewed by W2):

    unconstrained endpoints: 0
    unclocked registers: 0
    input ports without set_input_delay: 1
      G1
    input ports without set_input_transition: 1
      G2
    output ports without set_load: 0
    ignored timing arcs: 0
    lookups outside the table grid: 60 of 262
      cell_fall input_net_transition below 16 above 0 query 0.0000..0.0000 grid 0.0100..0.2000
      cell_rise input_net_transition below 16 above 0 query 0.0000..0.0000 grid 0.0100..0.2000
      fall_constraint related_pin_transition below 6 above 0 query 0.0000..0.0000 grid 0.0100..0.2000
      fall_transition input_net_transition below 8 above 0 query 0.0000..0.0000 grid 0.0100..0.2000
      rise_constraint related_pin_transition below 6 above 0 query 0.0000..0.0000 grid 0.0100..0.2000
      rise_transition input_net_transition below 8 above 0 query 0.0000..0.0000 grid 0.0100..0.2000

All 60 come from slew 0 (no `set_clock_transition` on the CK pins; G2 has no input transition).

`--trace FF2/D` on ff2_default (`tests/golden/trace/ff2_default_FF2_D.txt`, 153 lines), excerpt:

    trace FF2/D (ff2, ff2_default.sdc)
    cone: 10 pins
    U2/Y late r at 4.0000 slew 0.0500
        U2/A(f) 1.0000 + 2.0000 = 3.0000 slew 0.0500
      * U2/B(f) 2.0000 + 2.0000 = 4.0000 slew 0.0500
    FF2/D setup r rat 9.7000 = ck_at 0.0000 + period 10.0000 - t 0.3000 - uncertainty 0.0000; t at d_slew 0.0500 ck_slew 0.0500 (FF2/CK)
    FF2/D setup r at 4.0000 rat 9.7000 slack 5.7000
    setup : x(f) -> U1/A(f) -> U1/Y(f) -> U2/B(f) -> U2/Y(r) -> FF2/D(r)

Every number in every endpoint's trace on the eight designs is cross-checked against the P2 goldens (`test_trace.TraceCrossCheckTests`).

Units (R37): `test_cli.UnitTests.test_converted_library` runs ff2 with `BUF_P`/`NAND2_P`/`DFF_P` from a ps/fF copy of toy2.lib and gets `endpoints.tsv` identical to ff2_default.

s1423 (`data/s1423.v`, 748 instances: AND2 206, DFF 74, INV 167, NAND2 64, NOR2 92, OR2 145; period 75.6):

    $ python3 -m sta_toy --lib data/toy2.lib --verilog data/s1423.v --sdc data/sdc/s1423.sdc --report-summary
    check          wns       tns   nvp
    setup      -3.7856   -7.4814     3
    hold        2.6000    0.0000     0

setup WNS −3.7856 = −5.0 % of the period, hold met. `--check-timing` on s1423:

    unconstrained endpoints: 0
    unclocked registers: 0
    input ports without set_input_delay: 0
    input ports without set_input_transition: 0
    output ports without set_load: 0
    ignored timing arcs: 0
    lookups outside the table grid: 72 of 15356
      cell_fall total_output_net_capacitance below 0 above 24 query 0.0165..0.0680 grid 0.0010..0.0160
      cell_rise total_output_net_capacitance below 0 above 24 query 0.0165..0.0680 grid 0.0010..0.0160
      fall_transition total_output_net_capacitance below 0 above 12 query 0.0165..0.0680 grid 0.0010..0.0160
      rise_transition total_output_net_capacitance below 0 above 12 query 0.0165..0.0680 grid 0.0010..0.0160

Engine run time on s1423 with `--dump-tsv` (wall clock, `/usr/bin/time -p`, this Mac): 0.32 s (`/usr/bin/python3`), 0.19 s (python3.12); W3 measured 0.8 s / 1.2 s on its first run. Bound: 5 s.

R42 (tokenizer): not done (§9).

## 6. Decisions I made (ambiguities resolved on my own)
Lead:
1. Worktree location. Section 9 step 3 names `../p5-wt/w1` (outside the repo), while section 1 allows new directories only under the repo and `~/tools/`. I took the explicit step-3 path, `../p5-wt/{w1,w2,w3}` next to the repo, as the more specific rule; the worktrees are removed at the end (section 8.5).
2. `.gitignore` did not exist on viewer-v2. Section 1 allows adding `ref/results/`, `out/`, `*.pyc`; I created it with `*.pyc` (the untracked `__pycache__/` directories hold only `.pyc` files). W3 added `ref/results/` and `out/`.
3. Docker is not available on this Mac (`docker info` fails), so W3 was told to use route 2 (source build) within the 90-minute box, else route 3. Route 2 worked.
4. The Tk smoke test on `s1423` (section 6) belongs to W1's `tests/test_viewer.py`, but `data/s1423.v` is W3's; W1 wrote it to skip while the files are absent. It runs after the merge (1.09 s).
5. Section 8.3's protected-path command lists `data/sdc` as a whole, but W3's brief requires the new `data/sdc/s1423.sdc`. I read the protection as "the eight existing files" (section 1 says so). The command's only output is that new file; each of the eight is unchanged (`git diff --quiet viewer-v2..p5-ref -- data/sdc/<f>.sdc` for each). §10 has both commands.
6. W1's request for a bundle node `fanout` field (bundle.py has no worker owner): added by the lead, additively, with a contract "Changes in P5" section and a test (b46e9df). The deletion of `docs/notes/p5_w1.md` landed in that same commit instead of the docs-fold commit (index state); no content effect.
7. R40 classification: CK-pin arrival / slew under an ideal clock is classed `policy` (the brief's list names "CK-pin slew source"), not `adapter`: the adapter writes OpenSTA's pin properties as they are, and making it put the clock's transition or latency on CK pins would be the adapter computing the toy's model. Whether the adapter should take those values from OpenSTA's clock paths instead is part of decision P5-1.
8. The `run.sh` path fix (588f756) is the only lead fix under R40: an `adapter` (infrastructure) defect. No `toy-bug` was found, so no engine code changed under R40.
9. R40 evidence: besides the smallest cases I ran copies of three P2 SDC files with the P5-2..P5-4 policies neutralised (`ref/cases/aligned/`) — the P2 SDC files themselves are untouched (N34).

Engine (W2; recorded in DECISIONS.md R35–R37 and its contracts):
10. "D pins whose capture CK pin has no arrival": every CK pin gets the ideal-clock arrival (p2_semantics.md §5), so this never happens literally; read as the parenthesis says — a CK pin that is not a load of the clock port's net is *unclocked*. Such a register is still timed (N30), and `--check-timing` lists it.
11. Ignored-arc key is (cell, pin, related_pin, type), where `type` is the `timing_type`, or `combinational:<sense>` when the sense is the reason; count = arcs ignored.
12. Out-of-grid count `m` covers forward, check and backward lookups only. Backward now looks up only the delay table (it used to look up the transition too and discard it): same floats, one lookup fewer — goldens byte-exact.
13. Trace: "late before early" is per pin in engine order (late r, late f, early r, early f); the slack and path sections hold the endpoint only; the header names the SDC by base name.
14. R37: the units check sits in `design.load` (CLI and viewer path), not in `liberty.loads`, so the parser unit tests that build unit-less libraries stay unchanged; conversion factors are exact fractions; both protected libraries already declare ns / pF, so no golden run can hit the new error.
15. `trace.py` imports the private `bundle._cone` so the cone definition cannot drift; I left the name private.

Viewer (W1; DECISIONS.md R32–R34):
16. Fonts scale by `s / s_default` (Tk points already follow the display's dpi); on aqua that is exactly `s`. Hairlines stay 1 px.
17. Edge labels are `(t, text, anchor)` instead of `(t, text)`: a label moves left of its edge when the right side would cross a mark line; without it the required `3.5000` label on `ff2_holdviol` would be dropped (the hold line at 3.6 runs through it). The "8.5000 at the 3.5 edge" bug the brief mentions was not present.
18. The brief's R34 example (`s27` `U14/Y` extrapolated below) is wrong: U14 is driven by G0 with input transition 0.05, inside the grid. The test asserts the true slew-0 cases (`FF7/Q`, `U13/Y`, the constraints' CK-slew axis) and that U14/Y has none.
19. Lookup grid in engine mode only: bundles carry delays, not tables.
20. Overlap / cut-off fixes found by the new check: waveform arrow lanes 46 px apart (was 34); merge-card margin and long table-axis values wrap; near-critical threshold on its own line.

Reference (W3; DECISIONS.md R38–R39):
21. s1423 converts to 748 instances (the brief's "≈1000" read as an order of magnitude; no padding). Instance names drop a leading `G` before a digit, as `data/s27.v` does, so the s27 round-trip test compares all three files at `--tol 0`.
22. s1423 SDC: input / output delay 0.5 on every PI / PO; period 75.6 chosen from a first run at 100 (WNS −5.0 %).
23. The "golden-format CLI test" for s1423 lives in `tests/test_bench2v.py` (`S1423Tests`), not `tests/test_cli.py` (W2's file).
24. `to_golden.py` writes OpenSTA's numbers as they come (no substitution of the toy's CK conventions); endpoints are those OpenSTA reports a path end for; `--toy-pins` adds NA rows and `missing.txt`.
25. `correlate.py` reads Verilog / Liberty with its own small readers so it does not import `sta_toy` (it judges the engine).

## 7. Decisions for you
None of these is a toy bug: in each, both tools follow their own rules. Each changes P2 golden values if aligned, so I did not change anything (N30). Run all cases: `ref/cases/run_cases.sh`; re-check the classification: `python3 -m unittest tests.test_ref_cases` (skips without OpenSTA).

1. **P5-1 · CK-pin and clock-port values under an ideal clock** (class `policy`; ROADMAP D11).
   Case: `ref/cases/ck_conventions/` (`reg1.v`: one DFF, `ck_slew.sdc`: clock transition 0.05).
   Toy: `FF1/CK` slew 0.0500 (r), arrival `L` (pin or clock latency), f columns NA, clock port all NA. OpenSTA (pin properties): slew 0.0000, arrival 0.0000 without the ideal latency (its checks still use it: "clock network delay (ideal) 3.5" in `ff2_holdviol`), f arrival T/2 = 5.0000, clock port carries the CK-pin values.
   Contract: p2_semantics.md §5 (sources table). Effect: affects only CK-pin rows and the clock port; every endpoint value agrees.
   If aligned: either the toy's §5 table changes (CK slew 0 in pins.tsv while delay calc keeps the clock transition — every P2 golden's CK rows change), or — cheaper and golden-neutral — the adapter takes CK-pin arrival and slew from OpenSTA's clock paths and writes NA for CK f columns and the clock port. My recommendation: keep the toy and change the adapter (decide that this is a reporting convention, not a semantic one); that would also make s1423 qualify as an OpenSTA golden.
2. **P5-2 · Ideal clock latency on input and output delays** (class `policy`).
   Case: `ref/cases/io_latency/` (`latency.sdc`: `set_clock_latency 0.3 [get_clocks clk]`).
   Toy: `d` arrival 0.5000; `q` setup RAT 8.0000, hold RAT −2.0000. OpenSTA: `d` arrival 0.8000 (input delay + latency); `q` setup RAT 8.3000, hold RAT −1.7000 (output delay relative to the latency-shifted edge). FF1/D hold slack 0.4 vs 0.1.
   Contract: p2_semantics.md §5 (PI AT = input delay) and §7 ("Neither clock latency nor uncertainty enters a PO required time"). Seen in ff2_swap, s27.
   If aligned: PI arrivals and PO RATs gain the clock-level latency (pin-level latency on a CK pin stays local to that register); goldens of ff2_swap and s27 change. My recommendation: align (PrimeTime also references input / output delays to the latency-shifted ideal clock edge, unless told the delay includes it); the engine change is small (`set_sources` and the PO branch of `check`), but the goldens must be regenerated through the independent oracle, which this stage may not touch.
3. **P5-3 · Clock uncertainty on output-port checks** (class `policy`).
   Case: `ref/cases/po_uncertainty/` (`po_unc.sdc`: uncertainty 0.3, setup 0.5).
   Toy: `q` setup RAT 8.0000, hold RAT −0.5000. OpenSTA: 7.5000 and −0.2000 (T − output delay − U_s; −output delay + U_h).
   Contract: p2_semantics.md §7 (same sentence as P5-2). Seen in ff2_unc, s27.
   If aligned: PO RATs subtract / add the uncertainty like D-pin checks; ff2_unc and s27 goldens change. Recommendation: align.
4. **P5-4 · Unset `set_input_delay` facets** (class `policy`; DECISIONS R13 "Later: stage 2 confirms these defaults against OpenSTA").
   Cases: `ref/cases/input_delay_facets/max_only.sdc` (`-max 2.0` only) and `no_input_delay.sdc` (none).
   Toy: a facet never set reads 0 — `d` early arrival 0.0000, FF1/D hold slack −0.1000; with no input delay at all `d` is still timed against the clock (FF1/D setup slack 9.7000, hold −0.1000). OpenSTA: an unset `-min` facet leaves the early arrival undefined (FF1/D has no hold check: NA); a port with no input delay is unclocked, so paths from it are unconstrained (FF1/D not an endpoint).
   Contract: p2_semantics.md §5 ("A facet never set is 0"), sdc_subset.md "Facets and overriding". Seen in s27 (G1, G3: early values downstream differ by up to 2.5).
   If aligned: unset facets become NA instead of 0 (and an input without any input delay starts no constrained path); s27's goldens change, and `--check-timing` already lists such ports. Recommendation: align, since 0 silently makes hold optimistic or pessimistic.
5. **P5-5 · Tie-break between equal candidates** (class `policy`).
   Case: `ref/cases/tie_break/` (`tie2.v`: inputs `a`, `b` with equal delay into one NAND2).
   Toy: `FF1/D setup 7.2000 : a(f) -> U1/A(f) -> ...` (first by pin name, p2_semantics.md §6 / §11). OpenSTA: same slack, `b(f) -> U1/B(f) -> ...`. Seen in s1423 (24 of 158 paths, all equal slack).
   If aligned: the tie rule would follow OpenSTA's internal order, which is not documented and may change between versions. Recommendation: keep the toy's rule and teach `correlate.py` to count an equal-slack sequence difference as a tie, not a mismatch.

## 8. Reviewer findings
(pending)

## 9. Not done
(pending)

## 10. How to reproduce every number above
From the repo root on `p5-ref` (OpenSTA at `~/tools/opensta/build/sta`, else set `STA_BIN`):

    # §2 tests
    /usr/bin/python3 -m unittest discover -s tests                 # 214, 6 skipped
    ~/.local/bin/python3.12 -m unittest discover -s tests          # 214, 1 skipped (≈190 s)
    git checkout viewer-v2 && /usr/bin/python3 -m unittest discover -s tests && git checkout p5-ref   # 155, 4 skipped
    # §8.3 protected paths (only output: the new data/sdc/s1423.sdc, §6.5)
    git diff --stat viewer-v2..p5-ref -- data/toy2.lib data/ff2.v data/inv2.v data/s27.v data/c17.v data/toy.lib data/sdc tests/golden/ff2_default tests/golden/ff2_swap tests/golden/ff2_setupviol tests/golden/ff2_holdviol tests/golden/ff2_skew tests/golden/ff2_unc tests/golden/inv2 tests/golden/s27 tests/golden/c17_graph.txt tests/golden/reports tools/oracle tools/diff_ref.py docs/contracts/golden_format.md
    for f in ff2_default ff2_holdviol ff2_setupviol ff2_skew ff2_swap ff2_unc inv2 s27; do git diff --quiet viewer-v2..p5-ref -- data/sdc/$f.sdc || echo CHANGED $f; done   # no output
    # §3 viewer
    ~/.local/bin/python3.12 -m unittest -v tests.test_viewer.TkSmokeTests.test_s1423_in_10_seconds
    ~/.local/bin/python3.12 -m sta_toy.viewer --lib data/toy2.lib --verilog data/s27.v --sdc data/sdc/s27.sdc --scale 1.25
    # §4 correlation (tables built from ref/results/<d>/correlate.txt)
    ref/opensta/run.sh --probe
    ref/run_all.sh
    ref/cases/run_cases.sh
    python3 -m unittest -v tests.test_ref_cases tests.test_ref
    # §5 engine
    python3 -m sta_toy --lib data/toy2.lib --verilog data/s27.v --sdc data/sdc/s27.sdc --check-timing
    python3 -m sta_toy --lib data/toy2.lib --verilog data/ff2.v --sdc data/sdc/ff2_default.sdc --trace FF2/D
    python3 -m sta_toy --lib data/toy2.lib --verilog data/s1423.v --sdc data/sdc/s1423.sdc --check-timing
    python3 -m sta_toy --lib data/toy2.lib --verilog data/s1423.v --sdc data/sdc/s1423.sdc --report-summary
    /usr/bin/time -p python3 -m sta_toy --lib data/toy2.lib --verilog data/s1423.v --sdc data/sdc/s1423.sdc --dump-tsv out/s1423
    python3 tools/bench2v.py data/bench/s1423.bench out/s1423.v --top s1423 && cmp out/s1423.v data/s1423.v
