# Stages P3 + P4 — reports, JSON, debug bundle and a Tk viewer

Written 2026-11-04 from `ROADMAP.md` §2 (P3, P4) and §4 (4.1, 4.2, 4.4), on request of
the user ("push all the way to a GUI that can debug, multi-agent mode"). The contracts
under `docs/contracts/` (`report_p3.md`, `json_v1.md`, `bundle_v1.md`, `viewer_p4.md`,
`cli_p3.md`) are part of this spec and win over it. Everything from stage 1 and P2 stays
as it is: every earlier test passes and no P2 input, golden or contract changes.

## Requirements

| ID | Requirement | Module |
|----|-------------|--------|
| R21 | Path model: points with arc kind, incr and path AT; capture values; the json_v1 path object | `sta_toy/paths.py` |
| R22 | Worst path (PRED), K-worst enumeration, endpoint selection with from / to / through | `sta_toy/paths.py` |
| R23 | report_timing text, exactly `report_p3.md` §4, from path objects | `sta_toy/report.py` |
| R24 | Summary WNS / TNS / NVP and its text form | `sta_toy/paths.py`, `sta_toy/report.py` |
| R25 | JSON report schema v1 | `sta_toy/jsonout.py` |
| R26 | CLI options of `cli_p3.md` | `sta_toy/__main__.py` |
| R27 | Debug bundle v1 | `sta_toy/bundle.py` |
| R28 | Viewer model without Tk (v3): endpoint list, pin-to-pin stages, capture rows, path schematic with cells as gate symbols, slack formula, histogram, profile, path table, waveform; sources with forward / backward merges; themes | `sta_toy/viewer/model.py`, `sta_toy/viewer/source.py`, `sta_toy/viewer/theme.py` |
| R29 | Tk window (v3): header, histogram and endpoint list, slack summary, schematic / waveform / profile, path table, inspector, resizable and collapsible panels, switchable themes; engine and bundle modes | `sta_toy/viewer/app.py`, `sta_toy/viewer/__main__.py` |
| R30 | Tests for R21–R29 | `tests/test_paths.py`, `test_report.py`, `test_json.py`, `test_bundle.py`, `test_viewer.py`, `test_cli_p3.py` |
| R31 | Docs: README, TRACE, DECISIONS | — |

## Module interfaces (fixed before the parallel work)

```
design.load(lib_paths, verilog_path) -> (lib, netlist, linked)
design.timed(lib, netlist, linked, sdc_path) -> g          # g.sdc, g.lib, g.netlist set

paths.worst_path(endpoint_node, check) -> Path | None      # check: "setup" | "hold"
paths.enumerate_paths(endpoint_node, check, k=1, frm=None, through=None) -> [Path]
paths.select(g, check, max_paths=1, nworst=1, frm=None, to=None, through=None) -> [Path]
paths.summary(g) -> {"setup": {"wns", "tns", "nvp"}, "hold": {...}}   # raw floats
paths.path_json(path, sdc, pid) -> dict                    # json_v1.md path object
paths.num(v) -> float(fmt4(v)) | None

report.format_path(path_obj, transition=False, capacitance=False) -> str   # one block, ends "\n"
report.report_timing(path_objs, transition=False, capacitance=False) -> str  # blocks or "No paths.\n"
report.format_summary(summary) -> str

jsonout.units(lib) -> {"time": .., "cap": ..}
jsonout.report_json(g, design_info) -> dict   # design_info = json_v1 "design" object
jsonout.dumps(obj) -> str                      # indent 2, final "\n"
jsonout.write(obj, path)                       # OSError -> P2Error "cannot write ..."

bundle.debug_bundle(g, endpoint_name, depth=3, max_nodes=300) -> dict

viewer.source.EngineSource(lib_paths, verilog_path, sdc_path)   # raises StaError subclasses
viewer.source.BundleSource(path)                                # raises P2Error
  (v3: rows, summary, paths, instance, fanin, fanout, driver, arrival, pin, arcs — viewer_p4.md "Sources")
  .rows() -> [{pin, kind, setup_slack, hold_slack}]
  .bundle(endpoint, depth=3, max_nodes=300) -> dict
  .clock_name, .mode ("engine" | "bundle")
viewer.model.EndpointList / stages / capture_rows / schematic / ...   (viewer_p4.md v3)
viewer.app.App(root, source, theme_name="light")
python -m sta_toy.viewer ...                                    (viewer_p4.md "Start")
```

## Oracle

- `tests/golden/reports/*.txt`: hand-written report blocks (ff2_default FF2/D setup and
  hold, inv2 `y` setup with and without the Cap / Trans columns).
- Every number in reports, JSON and bundles is cross-checked against the P2 golden files
  (`tests/golden/<design>/`), which an independent oracle produced.
- Bundles and the viewer model are checked against hand-built expectations from the
  contracts; the Tk window gets a smoke test that skips without Tk or a display.

## Process

Branch `p3p4-viewer` from `p2-engine`. One commit per requirement ID or small group,
messages starting with the IDs, full suite green before each commit. Standard library
only, Python 3.8+ (the viewer needs a Python with Tk: `/usr/bin/python3` here).
