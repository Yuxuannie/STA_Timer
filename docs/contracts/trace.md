# Trace (contract, P5 R36)

`--trace PIN` (`cli_p5.md`) prints the engine's own record of how the values of one
endpoint were obtained: forward propagation, the check, backward propagation, the
slacks and the worst paths.

## The engine log

`timer.set_sources`, `forward`, `check`, `backward`, `slack` and `worst_path` take an
optional `log` (a list, default `None`). With `None` nothing changes. With a list, the
engine appends one dict per step **at the moment it computes it**, holding the values
it computed (full floats, never rounded):

| phase | when | keys |
|---|---|---|
| `forward` | a source value set from the SDC (§5), per pin, mode, rf with a defined AT | `pin, mode, rf, at, slew, candidates: [], winner: None, source` (`"input"` for a PI, `"clock"` for a CK pin) |
| `forward` | a non-source node, mode, rf with at least one candidate (§6) | `pin, mode, rf, at, slew, candidates: [{src, rf, at, delay, value, slew}], winner, source: None` |
| `check` | a D-pin check per check group and D rf (§7) | `pin, kind, rf, ck, d_slew, ck_slew, t, ck_at, period, uncertainty, output_delay: None, rat` |
| `check` | a PO required time per facet and rf (§7) | `pin, kind, rf, ck: None, d_slew: None, ck_slew: None, t: None, ck_at: None, period, uncertainty: None, output_delay, rat` |
| `backward` | a node, mode, rf with at least one candidate (§8) | `pin, mode, rf, rat, candidates: [{dst, rf, rat, delay, value}], winner` |
| `slack` | each call of `timer.slack` | `pin, kind, rf, at, rat, slack` (`None` when undefined) |
| `path` | each call of `timer.worst_path` | `kind, pin, rf, points: [[name, rf], ...]` from the startpoint |

Every dict also has `phase`. Forward candidates are in the engine's tie order (source
name, `r` before `f`); `winner` is the index of the candidate that set the AT, `value`
is `at + delay`, `slew` the candidate's output slew, and the node's `slew` the
worst-slew result. Backward candidates are in fanout order; `value = rat − delay` and
`winner` is the first candidate equal to the result (min late, max early). `kind` is
`setup` (late) or `hold` (early). Entries come in engine order: sources in node order,
then forward in topological order, the check in node order, backward in reverse
topological order, then whatever slack / path calls follow.

## Filtering

The trace keeps the entries whose `pin` is in the endpoint's cone: the fan-in cone of
`bundle._cone` with unlimited depth, which includes the capture CK pins of a D
endpoint. Check, slack and path entries are kept only for the endpoint itself. After
the run, the CLI calls `timer.slack(e, kind, rf, log)` for `kind` in setup, hold and
`rf` in r, f, then `timer.worst_path(e, kind, worst_rf(e, kind), log)` for setup then
hold when that transition exists. The formatter never calls `lookup`, never computes a
value and prints only numbers found in the log.

## Text format

Numbers with `fmt4` (`NA` for `None`). Lines end with `\n`, no trailing spaces, no blank
lines. `<design>` is the netlist module name, `<sdc>` the base name of the SDC file.

```
trace <endpoint> (<design>, <sdc>)
cone: <n> pins
forward
<pin> <mode> <rf> at <at> slew <slew> source <input|clock>
<pin> <mode> <rf> at <at> slew <slew>
<mark> <src>(<rf>) <at> + <delay> = <value> slew <slew>
...
check
<pin> setup <rf> rat <rat> = ck_at <ck_at> + period <period> - t <t> - uncertainty <u>; t at d_slew <d_slew> ck_slew <ck_slew> (<ck>)
<pin> hold <rf> rat <rat> = ck_at <ck_at> + t <t> + uncertainty <u>; t at d_slew <d_slew> ck_slew <ck_slew> (<ck>)
<pin> setup <rf> rat <rat> = period <period> - output_delay <d>
<pin> hold <rf> rat <rat> = 0.0000 - output_delay <d>
backward
<pin> <mode> <rf> rat <rat>
<mark> <dst>(<rf>) <rat> - <delay> = <value>
...
slack
<pin> <kind> <rf> at <at> rat <rat> slack <slack>
path
<kind> : <pin>(<rf>) -> ... -> <endpoint>(<rf>)
```

- One forward block per forward entry, one backward block per backward entry, in log
  order (so a pin's late r, late f, early r, early f follow each other, and every
  candidate's source has its own block earlier in the section). `<n>` counts the cone
  pins.
- `<mark>` is `*` for the winner and a space otherwise; candidate lines start with two
  spaces before the mark (`  * U2/B(f) ...`, `    U2/A(f) ...`).
- A section header is printed even when the section is empty.
