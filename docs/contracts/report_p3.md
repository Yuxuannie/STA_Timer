# P3 paths, report_timing and summary (contract)

Builds on `p2_semantics.md`: every value below is computed from the P2 timed graph
(AT, SLEW, RAT, PRED, LOAD, arc delays). Nothing here changes a P2 value or file.
Numbers in text use `fmt4` (p2_semantics.md §11). All comparisons use 1e-9.

## 1. Path

A path for check `c ∈ {setup, hold}` (mode `m` = late for setup, early for hold)
at endpoint `e` is a sequence of `(node, rf)` points `(n0, rf0) → … → (nk, rfk)` with
`(nk, rfk) = (e, rf)`, where each consecutive pair is an arc pair of the P2 timing
graph (net edge or timing() arc; never a check arc) and `n0` is a source (a PI or a
CK pin) with `AT[m][rf0](n0)` defined.

- Point `i > 0` has `incr_i = delay of the arc pair (n_{i-1}, rf_{i-1}) → (n_i, rf_i)`
  in mode `m`, computed exactly as in forward propagation (the source node's own
  SLEW in mode `m`, LOAD of the arc's destination; 0 for a net edge). Point 0 has
  `incr_0 = 0`.
- `at_i = AT[m][rf0](n0) + incr_1 + … + incr_i` (the path's own arrival, which equals
  the node AT only on the worst path).
- `arrival = at_k`; `required = RAT[m][rf](e)`;
  setup `slack = required − arrival`, hold `slack = arrival − required`.
- A path exists only if `required` is defined.
- `arc_i` names the arc into point `i`: `start` for point 0, `net`, `cell`
  (combinational timing() arc) or `ckq` (rising_edge arc).

**Path key** (used for every ordering of paths): the list of `(name, rank(rf))`
read from the endpoint backwards, `(nk, rfk), (n_{k-1}, rf_{k-1}), …, (n0, rf0)`,
with `rank(r) = 0`, `rank(f) = 1`, compared lexicographically with plain string
order of names (a shorter list that is a prefix of a longer one comes first).

**Path order**: by `round(slack, 9)` ascending (worst first), then by path key.
This order agrees with the P2 rules: the first path for `(e, c)` over both
endpoint transitions is the P2 worst path of `paths.txt` (PRED chain from `rf*`).

## 2. Worst path and K worst paths

`worst_path(e, c)` = the PRED chain of p2_semantics.md §9 from `(e, rf*)`; it must
equal the first path of §1's order (tested).

`enumerate(e, c, k, from=P, through=Q)` = the first `k` paths in path order among the
paths at `e` for `c` (both endpoint transitions), keeping only paths whose `n0` is
`P` (if given) and that contain node `Q` at any position (if given). Fewer than `k`
paths may exist. Implementation: best-first search backwards from `e`, where a
partial path from `(v, rf_v)` to `e` with suffix delay `D` has the optimistic bound
`AT[m][rf_v](v) + D` (exact for its best completion); pop states by
`(round(bound slack, 9), path key)` and emit complete paths in pop order. Any other
algorithm must give the same list.

## 3. Endpoint selection (report_timing)

Options: `kind` (setup = `max`, hold = `min`), `max_paths N ≥ 1` (default 1),
`nworst K ≥ 1` (default 1), `from P`, `to E`, `through Q`.

1. Candidate endpoints: all endpoints (p2_semantics.md §7), or only `E` with `to`.
2. For each candidate, `enumerate(e, c, K, from, through)`; drop endpoints with no path.
3. Order endpoints by their first path's `(round(slack, 9), endpoint name)`; keep the
   first `N`.
4. Report all kept paths, endpoint by endpoint, each endpoint's paths in path order.

`from` must name a PI or CK pin, `through` any node, `to` an endpoint; anything else
is an error (`error: --from x is not a startpoint`, `… is not a node`,
`… is not an endpoint`).

## 4. Report text

The report is the path blocks separated by one blank line, ending with `\n`. With no
path at all the report is the single line `No paths.`.

Column layout of every table line (no trailing spaces; `rstrip` each line):

```
name.ljust(40) [cap.rjust(10) + " "] [trans.rjust(10) + " "] incr.rjust(10) + " " + path.rjust(10) [+ " " + rf]
```
The `cap` column appears only with `--capacitance`, `trans` only with
`--transition-time` (both: cap first). Empty cells are spaces. The header line uses
the same layout with `Point`, `Cap`, `Trans`, `Incr`, `Path`; separator lines are `-`
repeated to the full width of the header line (61 without the optional columns).

Block, in order:
```
Startpoint: <n0> (<start kind>)
Endpoint: <e> (<end kind>)
Path Group: <clock name>
Path Type: max|min
<blank>
<header>
<separator>
<launch rows>
<data rows>
data arrival time                     (path = arrival)
<blank>
<capture rows>
data required time                    (path = required)
<separator>
<final rows>
<separator>
slack (MET)|slack (VIOLATED)          (path = slack)
```
- start kind: `input port clocked by <clk>` (PI) or
  `rising edge-triggered flip-flop clocked by <clk>` (CK pin).
- end kind: `rising edge-triggered flip-flop clocked by <clk>` (D pin) or
  `output port clocked by <clk>` (PO).
- launch rows: `clock <clk> (rise edge)` incr 0, path 0; then for a PI start
  `input external delay` incr = path = `at_0`; for a CK-pin start
  `clock network delay (ideal)` incr = path = `at_0`.
- data rows: one per point, name `<node> (<cell>)` for an instance pin, `<port> (in)`
  for a PI, `<port> (out)` for a PO; incr `incr_i`, path `at_i`, rf of the point;
  cap = LOAD of the node if it drives a net (PI or cell output pin), else empty;
  trans = `SLEW[m][rf_i]` of the node.
- capture rows, D endpoint with capture CK pin `c`:
  setup: `clock <clk> (rise edge)` incr T path T; `clock network delay (ideal)` incr
  `L_c` path `T+L_c`; `clock uncertainty` incr `−U_s` path `T+L_c−U_s`;
  `<c> (<cell>)` incr empty path `T+L_c−U_s` rf `r`; `library setup time` incr `−t_su`
  path `required`.
  hold: `clock <clk> (rise edge)` incr 0 path 0; `clock network delay (ideal)` `L_c`;
  `clock uncertainty` `+U_h`; `<c> (<cell>)` (incr empty) path `L_c+U_h` rf `r`;
  `library hold time` incr `+t_h` path `required`.
  Here `t_su = (AT[late][r](c) + T − U_s) − required` and
  `t_h = required − (AT[early][r](c) + U_h)`; `L_c = AT[m][r](c)`.
- capture rows, PO endpoint: `clock <clk> (rise edge)` incr T (setup) or 0 (hold),
  path the same; `output external delay` incr `required − edge`, path `required`.
- final rows: setup `data required time` (path required), then `data arrival time`
  (path `−arrival`); hold `data arrival time` (path arrival), then
  `data required time` (path `−required`). Final rows have no incr.
- slack row: `slack (MET)` if `fmt4(slack)` does not start with `-`, else
  `slack (VIOLATED)`.

The block is formatted from the path object of `json_v1.md` (numbers already rounded
by fmt4), so the viewer can print it from a saved bundle. Path values not stored in the
object (`T+L_c`, `T+L_c−U_s`, `L_c+U_h`, negated finals) are computed from those
rounded numbers.

Golden: `tests/golden/reports/` holds hand-written reports (no tool produced them).

## 5. Summary

Per check, over the endpoints whose check has a defined slack at `rf*`
(p2_semantics.md §9): `wns` = the minimum slack (may be positive; `None` with no
such endpoint), `tns` = Σ min(slack, 0) (0.0 with none), `nvp` = the number of
endpoints with slack < −1e-9.

Text (`--report-summary`), one header and two rows, `\n` endings:
```
check".ljust(8) + "wns".rjust(10) + "tns".rjust(10) + "nvp".rjust(6)
"setup".ljust(8) + fmt4(wns).rjust(10) + fmt4(tns).rjust(10) + str(nvp).rjust(6)
"hold" ...
```
