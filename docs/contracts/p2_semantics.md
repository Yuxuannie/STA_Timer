# P2 timing semantics (contract)

This file defines what the stage P2 engine computes. The golden files in
`tests/golden/` were produced from these rules by `tools/oracle/`. When the
implementation and this file disagree, this file wins; when this file is
ambiguous, stop and ask — do not pick an interpretation silently.

Units: all times are in the library's `time_unit` (ns in `toy2.lib`), all
capacitances in `capacitive_load_unit` (pF). SDC values are in the same units.
No conversion anywhere.

## 1. Nodes

Every port and every instance pin is a node named exactly as in the netlist:
ports by their name (`x`, `clk`, `G17`), pins as `INST/PIN` (`U2/A`, `FF1/CK`).

Each node carries, for `mode ∈ {late, early}` and `rf ∈ {r, f}`:
`AT[mode][rf]`, `SLEW[mode][rf]`, `RAT[mode][rf]`, and a predecessor
`PRED[mode][rf] = (node, rf)`. Any of these may be undefined (written `NA`).

Node classes:

| class | which nodes |
|---|---|
| clock port | the input port named by `create_clock` |
| CK pin | instance input pin whose library pin has `clock : true` |
| PI | every other input port |
| PO | every output port |
| D pin | instance input pin that is the `pin` of a `setup_rising` / `hold_rising` timing group |
| other | all remaining instance pins |

## 2. Nets, drivers, loads

A net has exactly one driver (a PI, the clock port, or a cell output pin);
two drivers → error (stage 1 already reports this; keep its message). Its
loads are cell input pins and/or one output port.

`LOAD(driver) = Σ capacitance of the load input pins + set_load(port)` for an
output port on that net (0 if no `set_load`). Output ports have no pin
capacitance of their own.

The clock port's net is the clock net. Every load on it must be a CK pin;
otherwise error (`clock port X drives a non-clock pin Y`). The clock net is
**not** part of the timing graph: no edges are created for it.

## 3. Edges

The timing graph has exactly two kinds of edges, both listed here. Nothing
else connects nodes: in particular there is **no** D→Q edge inside a flop
(the `timing()` groups of `DFF` only give CK→Q and the CK→D check arcs), so a
register loop such as `FF1/Q → … → FF2/D, FF2/Q → FF1/D` is not a cycle. Do
not reuse any generic input→output pin edge the stage 1 graph may have; the
loop check (§6) runs on this graph only.

**Net edges** (every data net): driver → each load, pairs `(r→r), (f→f)`,
delay 0, slew copied unchanged.

**Cell arcs** come from `timing()` groups of the library pin, one arc per
group, from `related_pin` to the group's pin:

| `timing_type` | pairs (input rf → output rf) | delay / output-slew table |
|---|---|---|
| `combinational`, `positive_unate` | r→r, f→f | `cell_rise`/`rise_transition` for output r; `cell_fall`/`fall_transition` for output f |
| `combinational`, `negative_unate` | r→f, f→r | same, chosen by the **output** rf |
| `combinational`, `non_unate` | r→r, r→f, f→r, f→f | same, chosen by the output rf |
| `rising_edge` (CK→Q) | r→r, r→f | same, chosen by the output rf |
| `setup_rising`, `hold_rising` (CK→D) | none — a **check arc**, never traversed | `rise_constraint` for D rising, `fall_constraint` for D falling |

Any other `timing_type` or `timing_sense` → error naming the cell, pin and value.

Table lookup for an arc `u(rf_u) → v(rf_v)` in mode `m`:
`delay = T_delay(input_net_transition = SLEW[m][rf_u] of u, total_output_net_capacitance = LOAD(v))`
and the candidate output slew is `T_trans(...)` with the same arguments. The
axis each argument maps to is given by the table's template (`variable_1`,
`variable_2`), **never** assumed.

## 4. Table lookup

A 2-D table with `index_1 = x[0..n-1]`, `index_2 = y[0..m-1]`, `values[i][j]`
(row i follows index_1, column j follows index_2; the table's own
`index_1`/`index_2` override the template's when present).

For a query `(p, q)`:
1. Choose `i` with `x[i] ≤ p ≤ x[i+1]`; if `p < x[0]` use `i = 0`; if `p > x[n-1]` use `i = n-2`. Same for `j` along `y`.
2. `s = (p − x[i]) / (x[i+1] − x[i])`, `t = (q − y[j]) / (y[j+1] − y[j])` (may be < 0 or > 1: linear extrapolation).
3. `v = (1−s)(1−t)·v[i][j] + s(1−t)·v[i+1][j] + (1−s)t·v[i][j+1] + st·v[i+1][j+1]`.

Tables are at least 2×2. Clamping is **not** allowed.

## 5. Sources (what forward starts from)

| node | AT[late] | AT[early] | SLEW (both modes) |
|---|---|---|---|
| PI | `set_input_delay -max` (or the plain value) | `-min` (or the plain value) | `set_input_transition`, default 0 |
| CK pin, rf = r | `L` | `L` | `set_clock_transition` of the clock, default 0 |
| CK pin, rf = f | NA | NA | NA |
| clock port | NA | NA | NA |

A facet never set is 0: a PI with no `set_input_delay` has AT 0 in both
modes; `set_input_delay -max 2.0` alone gives `AT[late] = 2.0`,
`AT[early] = 0` (`s27` port `G3`); no `set_input_transition` gives slew 0
(`s27` port `G2`). `L` is `set_clock_latency` given on `[get_pins INST/CK]`
if present, else the value given on `[get_clocks clk]`, else 0. Both r and f
of a PI get the same values.

## 6. Forward propagation

Visit nodes in a topological order of the timing graph (net edges + cell
arcs). A cycle → error (`combinational loop`). For each non-source node `v`,
each mode `m`, each `rf_v`: collect every incoming arc pair `(u, rf_u) → rf_v`
whose `AT[m][rf_u]` of `u` is defined, with
`cand_at = AT[m][rf_u](u) + delay`, `cand_slew` from §3.

- `AT[m][rf_v] = max` of `cand_at` for late, `min` for early.
- `PRED[m][rf_v]` = the candidate that achieved it. Ties (|Δ| < 1e-9) go to the
  candidate that is first when candidates are sorted by `(u.name, rf_u)` with
  `r` before `f`, using plain string comparison of names.
- `SLEW[m][rf_v] = max` of all `cand_slew` for late, `min` for early
  (**worst-slew policy**: the slew is taken over all arcs, independently of
  which arc gave the AT). Golden discriminator: `s27` pin `U15/Y`
  `slew_late_r = 0.0560`, which comes from a different arc than its AT.

If a node has no defined candidates, its values stay NA.

## 7. Check (endpoint required times)

Let `T` be the clock period, `U_s = set_clock_uncertainty -setup` (default 0),
`U_h = -hold` (default 0). A plain `set_clock_uncertainty V` sets both.

**D pin**, with CK pin `c` of the same instance (`related_pin`):
```
t_su(rf) = constraint lookup of the setup_rising group table for rf
           (constrained_pin_transition = SLEW[late][rf] of D,
            related_pin_transition    = SLEW[late][r]  of c)
t_h(rf)  = constraint lookup of the hold_rising group table for rf
           (constrained_pin_transition = SLEW[early][rf] of D,
            related_pin_transition     = SLEW[early][r] of c)
RAT[late][rf]  = AT[late][r](c)  + T − t_su(rf) − U_s
RAT[early][rf] = AT[early][r](c) + t_h(rf) + U_h
```
defined only for rf where the corresponding slew of D is defined.

**PO** with `set_output_delay`, for both rf:
```
RAT[late][rf]  = T − output_delay_max       (only if the max facet was set)
RAT[early][rf] = 0 − output_delay_min       (only if the min facet was set)
```
A facet that was never set leaves that RAT NA (`s27` port `G17` has only
`-max`: its hold cells are NA and it has no hold path line). A PO without any
`set_output_delay` is unconstrained: no RAT, not an endpoint. Neither clock
latency nor uncertainty enters a PO required time.

Endpoints = all D pins + all constrained POs.

## 8. Backward propagation

Visit nodes in reverse topological order, skipping endpoints (their RAT comes
from §7). For each node `u`, mode `m`, `rf_u`: over every outgoing arc pair
`(rf_u → rf_v)` to `v` where `RAT[m][rf_v]` of `v` is defined and
`SLEW[m][rf_u]` of `u` is defined, `cand = RAT[m][rf_v](v) − delay` (delay
exactly as in forward, i.e. with `u`'s slew in mode `m`).

- `RAT[late][rf_u] = min` of cand; `RAT[early][rf_u] = max` of cand.
- No candidates → NA.

CK pins get RATs through their `rising_edge` arcs. The clock port never gets one.

## 9. Slack, worst transition, paths

```
setup_slack[rf] = RAT[late][rf]  − AT[late][rf]
hold_slack[rf]  = AT[early][rf]  − RAT[early][rf]
```
(defined only when both terms are). For an endpoint, the reported transition
`rf*` is the one with the smaller slack; ties (|Δ| < 1e-9) → `r`.

The worst path of an endpoint for a check is obtained by following `PRED`
from `(endpoint, rf*)` in the check's mode (late for setup, early for hold)
until a node with no predecessor (a PI or a CK pin).

## 10. Error order

Errors are detected and reported in this order, and the first one stops the
run: library parse → netlist parse → link (unknown cell, unknown pin, two
drivers) → SDC syntax → SDC semantics (§ "Errors" of `sdc_subset.md`) →
timing graph (clock port driving a non-clock pin; combinational loop). A
loop test therefore needs a valid library, netlist and SDC. An unsupported
`timing_type` or `timing_sense` is no longer an error (see "Changes in P5").

## 11. Number format and comparison

Every number written to the golden files uses exactly this rule
(Python, standard library):
```python
from decimal import Decimal, ROUND_HALF_UP
def fmt4(v):
    if v is None:
        return "NA"
    d = Decimal(repr(round(v, 9))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    s = str(d)
    return "0.0000" if s == "-0.0000" else s
```
All max/min/tie comparisons use an absolute tolerance of 1e-9.

## Changes in P5

2026-11-05 (W2, R35). §3's last rule ("any other `timing_type` or
`timing_sense` → error") and the matching §10 error are replaced by: a
`timing()` group whose `timing_type` is not `combinational`, `rising_edge`,
`setup_rising` or `hold_rising`, or a `combinational` group whose
`timing_sense` is missing or not one of the three of §3, is **ignored and
counted**: it creates no arc and no check, and its tables are not read. The
count is kept on the timing graph per `(cell, pin, related_pin, type)` and
instance, printed as a warning by the CLI and listed by `--check-timing`
(`cli_p5.md`, `check_timing.md`). Why: real libraries carry recovery /
removal / min_pulse_width / clear / preset arcs on every flop; refusing them
made every real library unusable, while ignoring them leaves every value of
the supported arcs unchanged (the eight goldens prove it). A missing or
non-2-D table of a supported group is still an error.

2026-11-05 (W2, R37). The "Units" paragraph at the top ("no conversion
anywhere") is replaced by `cli_p5.md` "Library units": every library declares
`time_unit` and `capacitive_load_unit`; the first `--lib` is the main
library, every other library is converted to its units when loaded, and all
times and capacitances of §1–§11, the SDC values and every output are in the
main library's units. For `toy2.lib` alone (ns, pF) nothing changes. Why: a
real flow mixes libraries characterized in ps / fF with ones in ns / pF, and
an unconverted mix gives values that are wrong by 1000 without any error.
