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
python -m sta_toy.viewer --lib LIB [--lib LIB ...] --verilog TOP.v --sdc FILE.sdc [--theme NAME] [--scale S]
python -m sta_toy.viewer --bundle FILE.json [--theme NAME] [--scale S]
```
`NAME` is `light` (default), `dark` or `contrast`; `S` is the UI scale, 0.6..2.0 (P5, R32). Errors follow `cli_p2.md`: one stderr line,
exit 1 (argument errors, unreadable / non-JSON / wrong-schema bundles, engine errors with the
CLI's messages, no tkinter). Bundle mode lists only the bundle's endpoint and can expand only
inside its cone. A bundle without `instances` is the error `error: bundle has no
instances: write it again with --bundle` (P5, R33).

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
  net, and `fanout` (net arcs leaving the pin) under the same rule (P5, R34);
  `arcs(inst)` → the instance's timing arcs with per-pair delays; `arc_lookup` and
  `check_lookup` → the table lookups behind a delay or a constraint (P5, R34, engine only).
- `fanin(pin, check, rf)` (forward merge): every candidate arrival into `(pin, rf)` in the
  check's mode, `{from, rf, kind, at, delay, value = at + delay, margin}`, the winner first
  (late: largest, early: smallest; ties by pin, then `r` before `f`); `margin` = distance
  from the winner. `fanout(pin, check, rf)` (backward merge): every candidate required time
  from the pin's fanout, `{to, rf, kind, rat, delay, value = rat − delay, margin}`, the
  binding one first (late: smallest, early: largest).
- Attributes `design_name`, `clock_name`, `period`, `mode`.

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
- `path_table(path, source)`: three sections — "Source clock path" (or "Input"), "Data
  path", "Destination clock path" (or "Output"); data rows carry `label, cell, arc, kind, rf,
  load, fanout, slew_in, slew, incr, value` (AT), `rat`, `slack` (worst through the pin),
  `largest` (P5, R33) and `index`.
- `waveform(setup, hold, period, check)`: `{span, rows, marks}` — launch and capture clock
  rows with their edges, the data row changing between the earliest (hold path) and latest
  (setup path) arrival, and per check a mark with its window, required time, arrival and slack;
  each clock row carries its edge `labels` (P5, R33).
- `lookups(path, source, k)`: the lookup grids behind path point `k` (P5, R34);
  `near_critical(period)`: the merge margin under which a candidate is near-critical (P5, R33).
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
- **Views** (tabs 1–2): *Schematic* — gates drawn from `symbol` (bubbles for inverting
  cells, flops as boxes with a clock wedge), cells and wires neutral, only the critical path
  (wires, leads, pins, AT badges) in the accent colour; each path cell's delay `+d` under it;
  the selected pin ringed and the selected hop drawn in the focus colour; side-input labels
  sit on the side away from the path. Click a pin → select it; a cell → the cell; ⊕ → expand;
  ↺ → select the driver. Drag to pan, wheel / trackpad to scroll, ⌘/Ctrl-wheel or − / + to
  zoom (shown in %), Fit (zoom 0.95–1.25: long paths are panned), Collapse; in a narrow centre
  the zoom readout and then Fit give way to the tabs. *Waveform* — the
  launch and capture clocks, the data at the endpoint (old → changing → new), the hold and
  setup windows, both slacks as arrows; each rising clock edge labelled with its time where the label
  fits (P5, R33).
- **Path table**: `path_table` sections, columns `pin, cell, arc, rf, load, fanout, slew, incr,
  AT, RAT, pin slack`, the largest cell `incr` in bold, the data-path total, and the final slack; click a row to select the stage.
- **Inspector** (right panel): for a pin — AT / RAT / slew (late / early × r / f), setup and
  hold slack, load and fanout; for a path stage the lookup behind it (input slew and load → delay and
  output slew; D slew and CK slew → t_setup / t_hold), each with its grid (P5, R34); "arrival set by" (`fanin`) and
  "required set by" (`fanout`) with each candidate's expression and its margin to the winner
  (red under 1 % of the period, shown in the heading); click a candidate to go there. For a cell — its arcs with late delays.
- **Panels**: every divider can be dragged (side panels, histogram / list, summary / views /
  table) down to the narrowest size whose columns still fit (left 280, centre 460, right
  320 px, times the UI scale); `[` and `]` or the header icons hide and show the left and right panels; sizes and
  hidden panels survive a theme switch.
- **Keys**: ←/→ step the signal pin to pin (the schematic follows), ↑/↓ previous / next
  endpoint, S / H setup / hold, 1 / 2 views (3 reserved), F fit, [ / ] panels.
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

## Changes in P5 (2026-11-05)

Written before the code (R32-R34, PROMPT_P5.md W1). Where this section and the text above
disagree, this section wins; the text above is updated to match.

**R32 - window size and UI scale.** Before: the window opened at a fixed 1520x940 with a
fixed minimum of 1200x760, larger than a 1280x800 or 1440x900 laptop screen.
- `python -m sta_toy.viewer ... [--scale S]`: `S` a decimal number in 0.6..2.0 (both ends
  included). Anything else is `error: --scale needs a number from 0.6 to 2.0` (one stderr
  line, exit 1), checked with the other arguments, before the design is loaded.
- One scale factor `s` for the whole UI: `--scale`, else 1.0 on aqua, elsewhere
  `tk scaling * 72 / 96` clamped to 0.6..2.0. `App(root, source, theme_name, scale=None)`
  (`None` = that default).
- Every pixel constant of `app.py` (pane minimums and default sizes, paddings, row
  heights, column widths, line widths, histogram and waveform geometry) goes through
  `App.px(v) = v * s`; the schematic is drawn at `zoom * s` (model coordinates stay at
  zoom 1, scale 1; the zoom is a separate factor on top of `s`). Every font goes through
  `App.font(kind, size)`, whose point size is `size * s / s0` with `s0` the default
  scale: Tk already scales points by the display's `tk scaling`, so at the default scale
  the fonts are the P4 fonts on every platform, and on aqua (`s0` = 1) a font is simply
  `size * s` points.
- Window: width `min(1520 s, 0.92 * screen width)`, height `min(940 s, 0.90 * screen
  height)`, centred on the screen. `minsize` is derived from the pane minimums at `s`:
  width = left + centre + right pane minimum + the two dividers, height = header + status
  bar + the taller of the left column (histogram + list minimums) and the centre column
  (summary + views + table minimums) + dividers. When that minimum is larger than the
  size above (a large `--scale` on a small screen), the window opens at the minimum. At
  `s` = 1 on 1280x800 the window is 1177x720 and its minimum 1066x414, so it opens fully (sizes are rounded down to whole pixels).
  The pure size arithmetic is `sta_toy/viewer/scale.py` (no Tk): `parse_scale(text)`,
  `default_scale(windowing_system, tk_scaling)`, `minimum(s)`, `geometry(s, screen_w,
  screen_h)`.
- Not built: runtime DPI changes, per-monitor handling, remembering sizes between runs.

**R33 - cleanup.**
- The Profile view is removed: `model.profile`, its drawing, its test and its contract
  text. Views: `1` schematic, `2` waveform; `3` is reserved (R41) and does nothing (no
  binding). In its place the path table makes the largest data-path `incr` bold: among
  the Data path rows of kind `cell` / `ckq`, every row whose `incr` is within 1e-9 of the
  largest one (`path_table` data rows carry `largest: bool`).
- Bundles without `instances` are an error again (the P4 compatibility path that rebuilt
  pins from nodes, edges and path points is removed, and with it `source.note`):
  `error: bundle has no instances: write it again with --bundle`, exit 1.
- Waveform edge labels are made by `model.waveform(setup, hold, period, check,
  text_width=None, axis_px=None)`: each clock row gets `labels = [(t, text, anchor)]`, one
  per rising edge `t` inside the span, `text = fmt4(t)`. A label is placed right of its
  edge (`anchor` `w`, covering `[t, t + width]`) or, if that overlaps, left of it
  (`anchor` `e`, `[t - width, t]`, never before the span start); if both overlap it is
  dropped, never drawn through. It overlaps another label of its row (labels are placed in
  time order) or, on the capture clock row, which the dashed mark lines cross, a mark's
  required time strictly inside its interval. `width` = `text_width(text)` pixels
  converted to time units over `axis_px` pixels for the span; without `text_width` labels
  have width 0. A row's rising edges are its first edge plus any whole number of periods.
  `ff2_holdviol` `FF2/D`: the capture labels are `3.5000` and `13.5000`.
- Near-critical threshold in the inspector merges: a margin under 1 % of the clock period
  (`model.near_critical(period)`, compared with 1e-9 tolerance) instead of the constant
  0.05; each merge heading shows it (`margin < 0.1000` at period 10).

**R34 - inspector: lookup grid and fanout.**
- `EngineSource.arc_lookup(from_pin, to_pin, check, rf_from, rf_to)` -> `{"delay": d,
  "slew": d}` with `d = lookup.lookup_detail(...)` of the cell / ckq arc's delay and
  transition tables at the arguments the engine used (source slew of the check's mode,
  load of the destination); of several arcs between the two pins, the one whose delay
  gives the arrival (late largest, early smallest; ties to the first). `check_lookup(pin,
  check, rf)` -> `d` of the D pin's setup / hold constraint table at (D slew, CK slew).
  `BundleSource` returns `None` for both (a bundle has no tables), so the grid is shown in
  engine mode only. `model.lookups(path, source, k)` -> `[(label, d)]` for path point `k`:
  `("delay", d), ("output slew", d)` for a cell / ckq arc, `("t_setup" | "t_hold", d)`
  for the capture D pin, else `[]`.
- Inspector: under each lookup result line (`-> delay`, `-> output slew`, `-> t_setup` /
  `-> t_hold`) one compact block from `d`: the two axis names (`row` = the table's first
  variable, `col` = its second) with the query values, the bracketing index values as the
  headers of a 2x2 of the four corner values, and per axis `extrapolated below` / `above`
  in the `bad` colour when set. Numbers in the mono font, `fmt4`.
- Fanout: `source.pin(name)["fanout"]` = the number of net arcs leaving the pin, `None`
  when it drives no net (as `load`). Engine: from the graph. Bundle: the node's `fanout`
  field when the bundle has one, else `None` (the bundle's edges stop at the cone, so
  they cannot give the count; adding `fanout` to bundle nodes is a request to the
  bundle owner). The path table gets a `fanout` column after `load` (empty for input pins
  and the capture pin, which drive no net); the inspector shows `fanout N` beside `load`
  for output pins and input ports.
