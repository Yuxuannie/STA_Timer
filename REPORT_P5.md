STATUS: IN PROGRESS — phase 3 (p5-engine merged; W1, W3 running)
Branch p5-ref @ bbb685d; worker branches p5-viewer, p5-engine, p5-opensta @ bbb685d (created); started 2026-11-05 21:46 CST, last update 2026-11-05 21:55 CST

## 1. Result table
| ID | status (done / partial / skipped) | commit(s) | note |
|----|-----------------------------------|-----------|------|
| R32 | pending | | W1 |
| R33 | pending | | W1 |
| R34 | pending | | W1 |
| R35 | done | d399f2a, 59d4fbc (merged) | W2; ignored arcs counted, `--check-timing` |
| R36 | done | d399f2a, ce8eee3 (merged) | W2; `--trace PIN` from the engine log |
| R37 | done | a50ce00, 1f97fe7 (merged) | W2; both protected libraries already declare ns / pF |
| R38 | pending | | W3 |
| R39 | pending | | W3 |
| R40 | pending | | lead |
| R41 | pending | | lead, optional |
| R42 | pending | | lead, optional |
| R43 | pending | | lead |

## 2. Tests
before (viewer-v2 @ ed316ad): 155 (4 skipped) on /usr/bin/python3 (3.9.6), 155 (1 skipped) on ~/.local/bin/python3.12
after interface commit bbb685d: 159 (4 skipped) / 159 (1 skipped) — 4 new lookup_detail tests
after merge of p5-engine: 183 (4 skipped) / 183 (1 skipped)
after:  (pending)
commands:
    /usr/bin/python3 -m unittest discover -s tests
    ~/.local/bin/python3.12 -m unittest discover -s tests

## 3. Viewer
(pending)

## 4. OpenSTA correlation
(pending)

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

(s1423 run time and check_timing: after the W3 merge.)

## 6. Decisions I made (ambiguities resolved on my own)
1. Worktree location. Section 9 step 3 names `../p5-wt/w1` (outside the repo), while section 1 allows new directories only under the repo and `~/tools/`. I took the explicit step-3 path, `../p5-wt/{w1,w2,w3}` next to the repo, as the more specific rule; the worktrees are removed at the end (section 8.5).
2. `.gitignore` did not exist on viewer-v2. Section 1 allows adding `ref/results/`, `out/`, `*.pyc`; I created it with `*.pyc` (the untracked `__pycache__/` directories hold only `.pyc` files). W3 adds `ref/results/` and `out/`.
3. Docker is not available on this Mac (`docker info` fails), so W3 was told to use route 2 (OpenSTA source build under `~/tools/opensta`, Homebrew dependencies) within the 90-minute box, else route 3.
5. Engine readings (W2, recorded in DECISIONS.md R35–R37 entries and the contracts it wrote):
   a. "D pins whose capture CK pin has no arrival": every CK pin gets the ideal-clock arrival (p2_semantics.md §5), so this never happens literally; read as the parenthesis says — a CK pin that is not a load of the clock port's net is *unclocked*. Such a register is still timed (N30), and `--check-timing` lists it.
   b. Ignored-arc key is (cell, pin, related_pin, type), where `type` is the `timing_type`, or `combinational:<sense>` when the sense is the reason; count = arcs ignored.
   c. Out-of-grid count `m` covers forward, check and backward lookups only. Backward now looks up only the delay table (it used to look up the transition too and discard it): same floats, one lookup fewer — goldens byte-exact.
   d. Trace: "late before early" is per pin in engine order (late r, late f, early r, early f); the slack and path sections hold the endpoint only; the header names the SDC by base name.
   e. R37: the units check sits in `design.load` (CLI and viewer path), not in `liberty.loads`, so the parser unit tests that build unit-less libraries stay unchanged. Conversion factors are exact fractions.
   f. `trace.py` imports the private `bundle._cone` so the cone definition cannot drift; renaming it public is left as is (bundle.py is not changed in this stage).
4. The Tk smoke test on `s1423` (section 6) belongs to W1's `tests/test_viewer.py`, but `data/s1423.v` is made by W3 on another branch; W1 was told to write it so it skips while the files are absent. It runs after the merge.

## 7. Decisions for you
(pending)

## 8. Reviewer findings
(pending)

## 9. Not done
(pending)

## 10. How to reproduce every number above
    git checkout viewer-v2
    /usr/bin/python3 -m unittest discover -s tests          # 155 tests, 4 skipped
    ~/.local/bin/python3.12 -m unittest discover -s tests   # 155 tests, 1 skipped
