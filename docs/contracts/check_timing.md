# check_timing (contract, P5 R35)

`--check-timing` (`cli_p5.md`) prints what the run left unconstrained or could not
time. It reads the timed graph and the run's lookup record; it changes no value, and it
never turns a run that succeeds without it into an error. stdout only, exit 0.

## Format

Exactly seven sections, always all seven, in this order. Each section is a header line
`<title>: <count>` followed by its items, one per line, each indented by two spaces,
sorted by plain string order of the item's sort key (given per section). No blank
lines; every line ends with `\n`. Numbers are written with `fmt4`
(`p2_semantics.md` §11).

```
unconstrained endpoints: <n>
  <name>
unclocked registers: <n>
  <instance>
input ports without set_input_delay: <n>
  <port>
input ports without set_input_transition: <n>
  <port>
output ports without set_load: <n>
  <port>
ignored timing arcs: <n>
  <cell> <pin> <related_pin> <type> <arcs>
lookups outside the table grid: <k> of <m>
  <table kind> <axis> below <b> above <a> query <lo>..<hi> grid <lo>..<hi>
```

`<n>` is the number of items, except in section 6 (below).

## Definitions

A CK pin is **clocked** when it is a load of the clock port's net (the port named by
`create_clock`). The engine still gives every CK pin the ideal clock arrival
(`p2_semantics.md` §5, unchanged); this report is where an unclocked one shows.

1. **unconstrained endpoints** — every output port with no `set_output_delay` facet
   (it is not an endpoint, `p2_semantics.md` §7), and every D pin with at least one
   capture CK pin (the `related_pin` of its setup / hold groups) that is not clocked.
   Item: the port or pin name; sort key: the name.
2. **unclocked registers** — every instance with a CK pin that is not clocked. Item:
   the instance name; sort key: the name.
3. **input ports without set_input_delay** — every input port except the clock port
   with neither facet of `set_input_delay` (its AT is 0, §5). Sort key: the name.
4. **input ports without set_input_transition** — every input port except the clock
   port without `set_input_transition` (its slew is 0). Sort key: the name.
5. **output ports without set_load** — every output port without `set_load`. Sort key:
   the name.
6. **ignored timing arcs** — the `timing()` groups the timer ignored
   (`p2_semantics.md` "Changes in P5"), counted per instance of the cell in the
   netlist and per related pin. One item per `(cell, pin, related_pin, type)`:
   `<type>` is the `timing_type`, or `combinational:<timing_sense>` when the type is
   `combinational` and the sense cannot be mapped (`combinational:none` when the
   group has no `timing_sense`); `<arcs>` is the number of arcs ignored for that key
   (the number of instances of the cell, times the number of groups with that key in
   the cell — 1 in practice). `<n>` is the sum of `<arcs>`, which is the number in the
   `cli_p5.md` warning line. Sort key: `(cell, pin, related_pin, type)`.
7. **lookups outside the table grid** — `<m>` is the number of table lookups the run
   performed in forward propagation (a delay and a transition lookup per cell-arc
   candidate with a defined source AT), the check (one constraint lookup per D pin,
   check and D transition with a defined D slew and CK arrival) and backward
   propagation (one delay lookup per cell-arc candidate); lookups made later by
   reports, paths, bundles or the viewer are not counted. `<k>` is the number of those
   lookups with at least one query value outside its axis' grid (`p < x[0]` or
   `p > x[n-1]`, as `lookup_detail()["extrapolated"]` says). One item per
   `(table kind, axis)` with at least one lookup outside on that axis: table kind is
   the Liberty group (`cell_rise`, `cell_fall`, `rise_transition`, `fall_transition`,
   `rise_constraint`, `fall_constraint`), axis the template variable name; `below` /
   `above` count those lookups by side; `query` is the smallest..largest of their
   query values on that axis; `grid` is the smallest first index value..the largest
   last index value of the tables they used. A lookup outside on both axes counts in
   both items. Sort key: `(table kind, axis)`.

The warning line of `cli_p5.md` is the only thing written to stderr.

## Golden files

`tests/golden/check_timing/s27.txt` and `tests/golden/check_timing/ff2_default.txt`,
byte-exact, hand-reviewed against the SDC files (see the comments in
`data/sdc/s27.sdc`).
