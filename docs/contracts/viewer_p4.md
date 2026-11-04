# P4 viewer (contract)

A Tkinter debug viewer, standard library only. Tk is optional at import time: every
module except `sta_toy/viewer/app.py` must import without `tkinter`, and the tests that
need a display skip when `tkinter` is missing or `Tk()` fails. (On this machine only the
system `/usr/bin/python3` has Tk.)

## Start

```
python -m sta_toy.viewer --lib LIB [--lib LIB ...] --verilog TOP.v --sdc FILE.sdc
python -m sta_toy.viewer --bundle FILE.json
```
In-process mode runs the engine (same error contract as the CLI: one stderr line,
exit 1) and builds a bundle for any endpoint on demand, with depth 3 and 300 nodes
unless the user changes them in the window. Bundle mode loads one saved bundle (only its
endpoint is listed). Errors in bundle mode (unreadable file, not JSON, wrong `schema`)
are `error: ...` lines, exit 1.

## Model (`sta_toy/viewer/model.py`, no Tk)

- `EndpointTable(rows)`, rows = dicts `{pin, kind, setup_slack, hold_slack}` (floats or
  None). `sort(column, descending=False)` (None sorts last in either direction, ties by
  pin), `filter(text)` (case-insensitive substring of pin; "" = all), `page(n,
  size=50)` → the rows of page n (0-based) after sort and filter, `pages(size=50)` → the
  page count (≥ 1). `from_graph(g)` and `from_bundle(b)` build it.
- `timeline(path, width, margin=40)` → a list of drawing items for one path object
  (json_v1.md), each `{"kind", "x0", "x1", "label"}` with x in pixels: the time span is
  `[min(0, launch edge, all point at), max(capture edge + latency, required, arrival)]`
  mapped linearly onto `[margin, width − margin]`. Items: `launch_edge` (x0 = x1),
  `capture_edge`, `arrival`, `required`, `data` (x0 = launch AT, x1 = arrival), and for a
  D endpoint `window` (setup: x0 = required, x1 = capture edge + latency; hold: x0 =
  capture latency, x1 = required), labels with fmt4 numbers.
- `cone_layout(bundle, width, height, margin=40)` → `{"nodes": {pin: (x, y)}, "edges":
  [(u, v, kind, on_path)], "path_pins": set}`: one column per depth, depth 0 (the
  endpoint and its capture CK pins) on the right, deeper to the left, columns evenly
  spaced; in a column, pins sorted by name and evenly spaced top to bottom.
  `on_path` is true when both ends are consecutive points of a bundle path.
- `node_details(bundle, pin)` → text lines: kind, cell, depth, cap and the AT / RAT /
  SLEW table (late/early × r/f, fmt4 or NA), setup and hold slack.

## Window (`sta_toy/viewer/app.py`)

Three views in one window (a `ttk.PanedWindow` or notebook is fine):
1. **Endpoints**: a `ttk.Treeview` with pin, kind, setup slack, hold slack; clicking a
   heading sorts (again: reverse); a filter entry; previous / next page buttons and a
   "page i / n" label. Selecting a row loads that endpoint in the other two views.
   Negative slacks are shown in red.
2. **Path**: setup / hold switch; the report_p3.md text of the path in a read-only
   `Text`; below it a `Canvas` drawing `timeline(...)`.
3. **Cone**: a `Canvas` drawing `cone_layout(...)`: each node a box with its pin name
   and the worst AT / RAT / slack of the selected check; path edges thicker and in
   another color; a visible "TRUNCATED" banner when the bundle says so; clicking a node
   shows `node_details` in a side `Text`; depth and max-nodes spinboxes plus a reload
   button (in-process mode only).

No other dependencies, no images, no threads. `App(root, source)` builds the window
for a source object (in-process or bundle), so tests can create it with a hidden root.
