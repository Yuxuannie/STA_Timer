# P4 viewer, v3 (contract)

A Tkinter timing-debug workstation, standard library only: triage on the left (slack
histogram, endpoint list), the selected endpoint's worst path in the centre (slack worked out
term by term, three views of the path, the path table), and an inspector on the right that
explains one pin (its values, the table lookup behind its delay, and which input and which
fanout set its arrival and required time). v3 replaces v2 (schematic + stage table only), which
the user judged ugly and not usable for debugging; references chosen by the user: Vivado path
details, a Quartus-style waveform, a PrimeTime / Tempus workstation, PathView gate symbols.

Tk is optional at import time: every module except `sta_toy/viewer/app.py` imports without
`tkinter`, and the tests that need a window skip when a probe (`tkinter.Tk()` in a
subprocess) fails, because some system Tk builds abort the process instead of raising
`TclError`. On this Mac Tk works under `~/.local/bin/python3.12` (Tk 9.0).

## Start

```
python -m sta_toy.viewer --lib LIB [--lib LIB ...] --verilog TOP.v --sdc FILE.sdc [--theme NAME]
python -m sta_toy.viewer --bundle FILE.json [--theme NAME]
```
`NAME` is `light` (default), `dark` or `contrast`. Errors follow `cli_p2.md`: one stderr line,
exit 1 (argument errors, unreadable / non-JSON / wrong-schema bundles, engine errors with the
CLI's messages, no tkinter). Bundle mode lists only the bundle's endpoint and can expand only
inside its cone. A bundle written before `instances` existed still loads: each instance's
pins are rebuilt from the bundle's nodes, edges and path points (only the pins it mentions,
inputs then outputs by name) and the status bar says so (`source.note`).

## Sources (`source.py`, no Tk)

`EngineSource(lib_paths, verilog_path, sdc_path)` and `BundleSource(path)` answer the same
questions:
- `rows()`, `summary(check)` (`{wns, tns, nvp}`; `None` in bundle mode), `paths(endpoint)` →
  `{"setup", "hold"}` path objects of `json_v1.md` (or `None`).
- `instance(inst)` → `{cell, sequential, pins: [{name, direction, clock, function}]}` in
  library order (`function` is the Liberty pin function or `None`).
- `driver(pin)` (the net driver of an input pin, or `None`); `arrival(pin, check)` →
  `(AT, rf)` of the check's mode, worse transition, ties to `r`; `pin(name)` → AT / RAT /
  SLEW per mode and rf, setup and hold slack (minimum over rf), load when the pin drives a
  net; `arcs(inst)` → the instance's timing arcs with per-pair delays.
- `fanin(pin, check, rf)` (forward merge): every candidate arrival into `(pin, rf)` in the
  check's mode, `{from, rf, kind, at, delay, value = at + delay, margin}`, the winner first
  (late: largest, early: smallest; ties by pin, then `r` before `f`); `margin` = distance
  from the winner. `fanout(pin, check, rf)` (backward merge): every candidate required time
  from the pin's fanout, `{to, rf, kind, rat, delay, value = rat − delay, margin}`, the
  binding one first (late: smallest, early: largest).
- Attributes `design_name`, `clock_name`, `period`, `mode`, `note`.

## Model (`model.py`, no Tk)

- `EndpointList(rows)`: `check` and `text` select the view — worst slack first for the check,
  undefined last, ties by pin, case-insensitive substring filter; `neighbour(pin, step)`
  moves in the view and wraps (a pin not shown → the first shown).
- `stages(path)`: one row per path point, pin to pin: `index, pin, cell, kind, arc`
  (`input` / `clock` for the start, `net`, or `A→Y`-style for a cell arc), `rf` (`f`, or
  `f→r` across a cell), `delta` (row 0: the launch time, so the deltas add up to the
  arrival), `at`, `slew`, `share` (cell delta over the largest cell delta of the path).
- `capture_rows(path)`: `{label, delta, value}` — clock edge, clock latency, clock
  uncertainty and library setup / hold time for a flop (or output delay for a port), then
  required, arrival and slack.
- `symbol(instance)`: the gate symbol from the output pin's function — `inv`, `buf`, `and`,
  `nand`, `or`, `nor`, `xor`, `xnor`, `flop` (sequential cells) or `box`.
- `summary(path)`: check, slack, arrival, required, edge, launch latency or input delay, ck→q,
  data path, capture latency, library setup / hold, uncertainty, output delay, skew
  (`L_capture − L_launch`, `None` from an input port), logic levels, start, end.
- `formula(path)`: `{arrival: [(label, value)], required: [(label, signed value)], slack,
  check}`; the terms add up to arrival and required; slack = required − arrival (setup) or
  arrival − required (hold).
- `histogram(values, bins=12)`: `{lo, hi, count}` bins of equal width over
  `[min(values, 0), max(values, 0)]`, `None` skipped, the last bin closed.
- `profile(path)`: one bar per stage on the time axis — the launch, then every cell arc —
  `{label, kind, t0, t1, delay, index}`.
- `path_table(path, source)`: three sections — "Source clock path" (or "Input"), "Data
  path", "Destination clock path" (or "Output"); data rows carry `label, cell, arc, kind, rf,
  load, slew_in, slew, incr, value` (AT), `rat`, `slack` (worst through the pin) and `index`.
- `waveform(setup, hold, period, check)`: `{span, rows, marks}` — launch and capture clock
  rows with their edges, the data row changing between the earliest (hold path) and latest
  (setup path) arrival, and per check a mark with its window, required time, arrival and slack.
- `schematic(path, source, expanded)`: the drawing, deterministic, pixel coordinates at zoom 1:
  - Grid of columns `W_MOD + GAP` wide. Lane 0 holds the path left to right, one element per
    column: a port for a PI start / PO end, a module per cell hop, the launch flop for a CK
    start (CK and Q on the path), the capture flop for a D endpoint. A module shows all
    library signal pins (inputs left, outputs right, library order); each lane-0 element is
    shifted so its on-path input pin sits on one baseline.
  - Each pin of `expanded` (in order) that is a drawn, unwired side input whose driver is not
    yet drawn gets its driver one column left of the consumer, in a new lane outside all
    lanes on the consumer's side of the path (above for a pin above the baseline or a module
    in an upper lane, else below). The result lists the expansions applied.
  - Wires are orthogonal and bend only inside column gaps (path wires at the gap middle,
    expansion wires 10 px steps left of it), so no wire crosses a box and boxes never
    overlap. Path wires carry `on_path`.
  - Stubs: every other module input is a stub with state `expand` (driver not drawn), `link`
    (driver already drawn: reconvergence, no duplicate), `none` (unconnected, or outside the
    bundle) or `clock` (CK pins, with the clock latency); each with the driver and the pin's
    arrival.
  - Badges `AT rf` on the on-path output pins (an input's AT equals its driver's).

## Window (`app.py`)

`App(root, source, theme_name)`, everything drawn on canvases:
- **Header**: the left-panel toggle, `STA Timer`, design, clock and period; WNS / TNS / NVP
  for setup and hold (engine mode; the worst slack only when the window is narrow; click to
  switch check); the Setup / Hold toggle; the theme switch; the right-panel toggle.
- **Left panel**: the slack histogram of the current check (click a bin to filter the list,
  again to clear) and the endpoint list (filter box; endpoint, slack, start point, logic
  levels; click to select).
- **Summary**: endpoint, check, start point, logic levels, clock skew; the slack in large
  type with MET / VIOLATED; then arrival and required as their terms (`formula`) and the slack
  line, totals in one column. Terms that do not fit wrap onto an indented line, and the strip
  grows to keep every line visible (its divider cannot hide them).
- **Views** (tabs 1–3): *Schematic* — gates drawn from `symbol` (bubbles for inverting
  cells, flops as boxes with a clock wedge), cells and wires neutral, only the critical path
  (wires, leads, pins, AT badges) in the accent colour; each path cell's delay `+d` under it;
  the selected pin ringed and the selected hop drawn in the focus colour; side-input labels
  sit on the side away from the path. Click a pin → select it; a cell → the cell; ⊕ → expand;
  ↺ → select the driver. Drag to pan, wheel / trackpad to scroll, ⌘/Ctrl-wheel or − / + to
  zoom (shown in %), Fit (zoom 0.95–1.25: long paths are panned), Collapse; in a narrow centre
  the zoom readout and then Fit give way to the tabs. *Waveform* — the
  launch and capture clocks, the data at the endpoint (old → changing → new), the hold and
  setup windows, both slacks as arrows. *Profile* — one bar per stage on the time axis, the
  largest cell delay in the accent colour, arrival and required as lines.
- **Path table**: `path_table` sections, columns `pin, cell, arc, rf, load, slew, incr, AT,
  RAT, pin slack`, the data-path total, and the final slack; click a row to select the stage.
- **Inspector** (right panel): for a pin — AT / RAT / slew (late / early × r / f), setup and
  hold slack, load; for a path stage the lookup behind it (input slew and load → delay and
  output slew; D slew and CK slew → t_setup / t_hold); "arrival set by" (`fanin`) and
  "required set by" (`fanout`) with each candidate's expression and its margin to the winner
  (red under 0.05); click a candidate to go there. For a cell — its arcs with late delays.
- **Panels**: every divider can be dragged (side panels, histogram / list, summary / views /
  table) down to the narrowest size whose columns still fit (left 280, centre 460, right
  320 px); `[` and `]` or the header icons hide and show the left and right panels; sizes and
  hidden panels survive a theme switch.
- **Keys**: ←/→ step the signal pin to pin (the schematic follows), ↑/↓ previous / next
  endpoint, S / H setup / hold, 1 / 2 / 3 views, F fit, [ / ] panels.
- **Style**: one neutral palette and a single accent per theme (`light`, `dark`, `contrast`,
  identical keys); green and red only on slack figures; hierarchy from type size, spacing and
  hairlines (no bordered cards, pills or row rules). Words use the platform UI font (SF Pro on
  macOS, via Tk's default font; elsewhere the `UI_FONTS` chain); every number uses the mono
  chain so columns line up; small tracked capitals for section labels; one size scale
  (9, 10–12, 13, 16–18, 28 pt).
- Expansions are kept per (endpoint, check). Themes switch at runtime by rebuilding the
  widgets; state is kept. Only canvases and frames carry colours (Aqua ignores `tk.Button`
  colours); no images, no threads, no other dependencies. Test hooks: `select_endpoint`,
  `set_check`, `set_tab`, `set_filter`, `filter_bin`, `next_endpoint`, `step`,
  `select_stage`, `select_pin`, `select_cell`, `expand`, `collapse`, `set_zoom`, `fit`,
  `set_theme`, `toggle_panel`; Tk callback errors are collected in `app.errors`.
