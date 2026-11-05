# P4 viewer, v2 (contract)

A Tkinter debug viewer, standard library only, with one focus: the selected endpoint's worst
path, drawn as **cells (modules) wired pin to pin**, with a stage table under it. v2 replaces
the first viewer (endpoint Treeview, report text + timeline, name-box cone), which was
judged cluttered.

Tk is optional at import time: every module except `sta_toy/viewer/app.py` imports without
`tkinter`, and the tests that need a window skip when a probe (`tkinter.Tk()` in a
subprocess) fails, because some system Tk builds abort the process instead of raising
`TclError`. On this machine Tk works under `~/.local/bin/python3.12` (Tk 9.0).

## Start

```
python -m sta_toy.viewer --lib LIB [--lib LIB ...] --verilog TOP.v --sdc FILE.sdc [--theme NAME]
python -m sta_toy.viewer --bundle FILE.json [--theme NAME]
```
`NAME` is `light` (default), `dark` or `contrast`. Errors follow `cli_p2.md`: one stderr line,
exit 1 (argument errors, unreadable / non-JSON / wrong-schema bundles, bundles without
`instances`, engine errors with the CLI's messages, no tkinter). Bundle mode lists only the
bundle's endpoint and can expand only inside its cone.

## Sources (`source.py`, no Tk)

`EngineSource(lib_paths, verilog_path, sdc_path)` and `BundleSource(path)` answer the same
questions: `rows()`, `summary(check)` (`None` in bundle mode), `paths(endpoint)` →
`{"setup", "hold"}` path objects of `json_v1.md` (or `None`), `instance(inst)` → cell and
library pins `{name, direction, clock}` in library order, `driver(pin)` (the net driver of an
input pin, or `None`), `arrival(pin, check)` → `(AT, rf)` of the check's mode, worse
transition, ties to `r`, `pin(name)` → AT / RAT / SLEW per mode and rf, setup and hold slack
(minimum over rf), load when the pin drives a net; `arcs(inst)` → the instance's timing arcs
with per-pair delays. Attributes `design_name`, `clock_name`, `period`, `mode`.

## Model (`model.py`, no Tk)

- `EndpointList(rows)`: `check` and `text` select the view — worst slack first for the check,
  undefined last, ties by pin, case-insensitive substring filter; `neighbour(pin, step)`
  moves in the view and wraps (a pin not shown → the first shown).
- `stages(path)`: one row per path point, pin to pin: `index, pin, cell, kind, arc`
  (`input` / `clock` for the start, `net`, or `A→Y`-style for a cell arc), `rf` (`f`, or
  `f→r` across a cell), `delta` (row 0: the launch time, so the deltas add up to the
  arrival), `at`, `slew`, `share` (cell delta over the largest cell delta of the path).
- `capture_rows(path)`: `{label, delta, value}` — clock edge, then clock latency, clock
  uncertainty and library setup/hold time for a flop (or output delay for a port), then
  required, arrival and slack (`slack (MET)` / `slack (VIOLATED)` by the report rule).
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
    bundle) or `clock` (CK pins: `L <latency>`); with the driver name and the pin's arrival.
  - Badges `AT rf` on the on-path output pins, the PI start and the endpoint.

## Window (`app.py`)

`App(root, source, theme_name)`:
- **Header**: endpoint, `SETUP|HOLD slack … MET|VIOLATED` chip, design and clock, SETUP / HOLD
  toggle, previous / next endpoint, WNS / TNS / NVP of the check (engine mode), theme menu.
- **Endpoints** (left): filter box and the `EndpointList` view; click to select.
- **Schematic** (centre top): modules, ports, wires, stubs, badges; in each path module a
  dashed in-cell arc `+delay`; the path in the accent colour; the selected pin ringed and the
  selected hop (net wire or cell arc) in the focus colour. Click a pin → select it; a module
  header → select the cell; ⊕ → expand; a link → select its driver. Drag to pan, wheel and
  trackpad scroll, ⌘/Ctrl-wheel zoom, Fit (never below zoom 0.7: long paths are panned),
  Collapse (drop the expansions of this endpoint and check).
- **Stage table** (centre bottom): `#, PIN, CELL, ARC, RF, Δ, AT, SLEW` and a bar of `share`,
  then the capture rows; click a row to select that pin.
- **Inspector** (right): the selected pin (cell, direction, AT / RAT / SLEW late / early ×
  r / f, setup and hold slack, load, driver) or cell (its arcs with late delays).
- **Keys**: ←/→ step the signal pin to pin (auto-pans the schematic), ↑/↓ previous / next
  endpoint, F fit.
- Expansions are kept per (endpoint, check). Themes come from `theme.py` (`light`, `dark`,
  `contrast`, identical keys) and switch at runtime by rebuilding the widgets; state is kept.
- Only labels and canvases carry colours (Aqua ignores `tk.Button` colours); no images, no
  threads, no other dependencies. Test hooks: `select_endpoint`, `set_check`, `expand`,
  `step`, `select_stage`, `select_pin`, `select_cell`, `set_theme`, `set_zoom`, `fit`,
  `collapse`; Tk callback errors are collected in `app.errors`.
