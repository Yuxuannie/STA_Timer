# JSON report, schema v1 (contract)

Written by `--json FILE`. UTF-8, `json.dumps(obj, indent=2)` plus a final `\n`, keys in
the order listed here. Every time or capacitance is `float(fmt4(v))` (so `0.3` not
`0.30000000000000004`); undefined values are `null`. Units are the library's
(`time` from `time_unit`, `cap` from `capacitive_load_unit`), never converted.

```
{
  "schema": "sta_toy.report/1",
  "design": {"name": <module>, "libs": [<--lib paths as given>], "verilog": <path>,
             "sdc": <path>, "units": {"time": "1ns", "cap": "1pf"}},
  "clocks": [{"name": <clk>, "period": T, "port": <clock port>,
              "latency": <clock-level latency>, "pin_latency": {<pin>: L, ...},
              "transition": <clock transition>,
              "uncertainty": {"setup": U_s, "hold": U_h}}],
  "summary": {"setup": {"wns": .., "tns": .., "nvp": ..}, "hold": {...}},
  "endpoints": [{"pin": <name>, "kind": "D"|"PO", "clock": <clk>,
                 "setup": {"rf": rf*|null, "at": .., "rat": .., "slack": ..},
                 "hold":  {"rf": .., "at": .., "rat": .., "slack": ..},
                 "worst_path": {"setup": <path id>|null, "hold": <path id>|null}}],
  "paths": [<path>, ...]
}
```
`units.time` is the `time_unit` string of the first library with the quotes removed
(`"1ns"`); `units.cap` is `"{:g}{}".format(value, unit)` of its
`capacitive_load_unit` (`"1pf"`).

Endpoints are sorted by pin name (as `endpoints.tsv`). `paths` holds the worst setup
and the worst hold path of every endpoint (report_p3.md §2), endpoints in name order,
setup before hold, ids `"p1"`, `"p2"`, … in that order; a check with no path has no
entry and `worst_path` is `null`.

A **path object** (also used by the debug bundle):
```
{"id": "p1", "type": "max"|"min", "check": "setup"|"hold",
 "start": <n0>, "end": <e>, "launch_clock": <clk>, "capture_clock": <clk>,
 "points": [{"pin": <node>, "cell": <cell>|null, "arc": "start"|"net"|"cell"|"ckq",
             "rf": "r"|"f", "incr": .., "at": .., "slew": SLEW[m][rf], "cap": LOAD|null}],
 "launch": {"clock_edge": 0.0, "latency": L|null, "input_delay": d|null},
 "capture": {"clock_edge": T|0.0, "latency": L_c|null, "uncertainty": U|null,
             "check": t_su|t_h|null, "output_delay": .. |null, "rat": required,
             "pin": <capture CK pin>|null, "cell": <its cell>|null},
 "arrival": .., "required": .., "slack": ..}
```
- `launch.latency` is `at_0` for a CK-pin start (else null); `launch.input_delay` is
  `at_0` for a PI start (else null).
- `capture` for a D endpoint: `clock_edge` T (setup) or 0 (hold), `latency` `L_c`,
  `uncertainty` `U_s` (setup) or `U_h` (hold), `check` `t_su` or `t_h` as defined in
  report_p3.md §4, `output_delay` null. For a PO endpoint: `latency`, `uncertainty`,
  `check` null and `output_delay` = the facet used (`-max` for setup, `-min` for hold).
  `pin` / `cell` name the capture CK pin of a D endpoint (null for a PO).
- `cap` is the LOAD of the point's node if it drives a net, else null.
