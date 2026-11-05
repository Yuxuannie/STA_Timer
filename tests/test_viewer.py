"""R28, R29: the viewer v2 (viewer_p4.md) — endpoint list, pin-to-pin stages, capture rows,
path schematic, sources, themes, the viewer CLI and a Tk smoke test. Expected values come
from the contract by hand and from the P2 golden files."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from sta_toy import P2Error, bundle
from sta_toy.tsv import fmt4
from sta_toy.viewer import model, theme
from sta_toy.viewer.source import BundleSource, EngineSource

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "data", "toy2.lib")
FF2_V = os.path.join(ROOT, "data", "ff2.v")
DESIGNS = [("ff2_default", "ff2"), ("ff2_swap", "ff2"), ("ff2_setupviol", "ff2"),
           ("ff2_holdviol", "ff2"), ("ff2_skew", "ff2"), ("ff2_unc", "ff2"),
           ("inv2", "inv2"), ("s27", "s27")]
MODE = {"setup": "late", "hold": "early"}
_SOURCES = {}


def sdc(scenario):
    return os.path.join(ROOT, "data", "sdc", scenario + ".sdc")


def engine(scenario, netlist):
    if scenario not in _SOURCES:
        _SOURCES[scenario] = EngineSource([LIB], os.path.join(ROOT, "data", netlist + ".v"), sdc(scenario))
    return _SOURCES[scenario]


def golden(scenario, name):
    with open(os.path.join(ROOT, "tests", "golden", scenario, name)) as f:
        lines = f.read().splitlines()
    if name == "paths.txt":
        return lines
    header = lines[0].split("\t")
    return dict((r["pin"], r) for r in (dict(zip(header, line.split("\t"))) for line in lines[1:]))


class EndpointListTests(unittest.TestCase):
    """R28: worst first per check, undefined last, filter, previous / next."""

    ROWS = [{"pin": "b", "kind": "D", "setup_slack": 2.0, "hold_slack": None},
            {"pin": "a", "kind": "D", "setup_slack": 2.0, "hold_slack": 0.5},
            {"pin": "c", "kind": "PO", "setup_slack": None, "hold_slack": -1.0},
            {"pin": "d", "kind": "D", "setup_slack": -0.3, "hold_slack": 3.0}]

    def test_order_per_check(self):
        lst = model.EndpointList(self.ROWS)
        self.assertEqual([r["pin"] for r in lst.view()], ["d", "a", "b", "c"])
        lst.check = "hold"
        self.assertEqual([r["pin"] for r in lst.view()], ["c", "a", "d", "b"])

    def test_filter_and_neighbour(self):
        lst = model.EndpointList(self.ROWS)
        self.assertEqual(lst.neighbour("a", 1), "b")
        self.assertEqual(lst.neighbour("c", 1), "d")          # wraps
        self.assertEqual(lst.neighbour("d", -1), "c")
        lst.text = "B"
        self.assertEqual([r["pin"] for r in lst.view()], ["b"])
        self.assertEqual(lst.neighbour("a", 1), "b")          # not shown -> first shown
        lst.text = "zz"
        self.assertIsNone(lst.neighbour("a", 1))


class StageTests(unittest.TestCase):
    """R28: one row per pin, pin to pin, against the golden paths and pins."""

    def test_against_golden(self):
        for scenario, netlist in DESIGNS:
            src, pins = engine(scenario, netlist), golden(scenario, "pins.tsv")
            lines = golden(scenario, "paths.txt")
            for row in src.rows():
                found = src.paths(row["pin"])
                for check in ("setup", "hold"):
                    path = found[check]
                    line = [l for l in lines if l.startswith("%s %s " % (row["pin"], check))]
                    self.assertEqual(path is None, not line, (scenario, row["pin"], check))
                    if path is None:
                        continue
                    stages = model.stages(path)
                    self.assertEqual(" -> ".join("%s(%s)" % (r["pin"], r["rf"][-1]) for r in stages),
                                     line[0].split(" : ")[1])
                    for r in stages:
                        self.assertEqual(fmt4(r["at"]), pins[r["pin"]]["at_%s_%s" % (MODE[check], r["rf"][-1])])
                    self.assertEqual(fmt4(sum(r["delta"] for r in stages)), fmt4(path["arrival"]))

    def test_labels(self):
        path = engine("ff2_default", "ff2").paths("FF2/D")["setup"]
        rows = model.stages(path)
        self.assertEqual([(r["arc"], r["rf"]) for r in rows],
                         [("input", "f"), ("net", "f"), ("A→Y", "f→f"), ("net", "f"), ("B→Y", "f→r"),
                          ("net", "r")])
        self.assertEqual([fmt4(r["delta"]) for r in rows],
                         ["0.5000", "0.0000", "1.5000", "0.0000", "2.0000", "0.0000"])
        self.assertEqual([r["share"] for r in rows], [0.0, 0.0, 0.75, 0.0, 1.0, 0.0])
        hold = model.stages(engine("ff2_default", "ff2").paths("FF2/D")["hold"])
        self.assertEqual([r["arc"] for r in hold[:2]], ["clock", "CK→Q"])


class CaptureRowTests(unittest.TestCase):
    """R28: the requirement side adds up to the golden required time."""

    def rows(self, scenario, netlist, pin, check):
        return [(r["label"], None if r["delta"] is None else fmt4(r["delta"]), fmt4(r["value"]))
                for r in model.capture_rows(engine(scenario, netlist).paths(pin)[check])]

    def test_flop(self):
        # s27: period 10, latency 0.2, setup uncertainty 0.1, required 9.8222 (endpoints.tsv).
        self.assertEqual(self.rows("s27", "s27", "FF5/D", "setup"), [
            ("clock clk (rise edge)", None, "10.0000"), ("clock latency", "0.2000", "10.2000"),
            ("clock uncertainty", "-0.1000", "10.1000"), ("library setup time", "-0.2778", "9.8222"),
            ("required", None, "9.8222"), ("arrival", None, "8.6849"), ("slack (MET)", None, "1.1373")])

    def test_port_and_violation(self):
        self.assertEqual(self.rows("inv2", "inv2", "y", "hold")[:3], [
            ("clock clk (rise edge)", None, "0.0000"), ("output delay", "-1.0000", "-1.0000"),
            ("required", None, "-1.0000")])
        self.assertEqual(self.rows("ff2_setupviol", "ff2", "FF2/D", "setup")[-1],
                         ("slack (VIOLATED)", None, "-0.3000"))


def all_pins(sch):
    return dict(((p["pin"], p["x"], p["y"]), p) for e in sch["elements"] for p in e["pins"])


class SchematicTests(unittest.TestCase):
    """R28: cells as modules on a grid, wired pin to pin."""

    def test_ff2_path(self):
        src = engine("ff2_default", "ff2")
        sch = model.schematic(src.paths("FF2/D")["setup"], src)
        self.assertEqual([(e["kind"], e["name"], e["col"], e["lane"]) for e in sch["elements"]],
                         [("port", "x", 0, 0), ("module", "U1", 1, 0), ("module", "U2", 2, 0),
                          ("module", "FF2", 3, 0)])
        self.assertEqual([p["name"] for p in sch["elements"][3]["pins"]], ["CK", "D", "Q"])
        on_path = [p["pin"] for e in sch["elements"] for p in e["pins"] if p["on_path"]]
        self.assertEqual(on_path, ["x", "U1/A", "U1/Y", "U2/B", "U2/Y", "FF2/D"])
        self.assertEqual(sch["elements"][2]["arc"], {"from": "U2/B", "to": "U2/Y", "delay": 2.0})
        # The on-path pins of lane 0 sit on one baseline.
        self.assertEqual(len(set(p["y"] for e in sch["elements"] for p in e["pins"]
                                 if p["on_path"] and p["side"] == "in" or e["kind"] == "port")), 1)
        self.assertEqual([(s["pin"], s["state"], s["driver"], s["at"]) for s in sch["stubs"]],
                         [("U2/A", "expand", "FF1/Q", "1.0000 r"), ("FF2/CK", "clock", None, "L 0.0000")])
        self.assertEqual([b["text"] for b in sch["badges"]],
                         ["0.5000 f", "2.0000 f", "4.0000 r", "4.0000 r"])
        self.assertEqual([(w["from"], w["to"]) for w in sch["wires"]],
                         [("x", "U1/A"), ("U1/Y", "U2/B"), ("U2/Y", "FF2/D")])

    def test_expand_and_link(self):
        src = engine("ff2_default", "ff2")
        sch = model.schematic(src.paths("FF2/D")["setup"], src, ["U2/A", "U2/A", "nope"])
        self.assertEqual(sch["expanded"], ["U2/A"])
        ff1 = sch["elements"][-1]
        self.assertEqual((ff1["name"], ff1["col"], ff1["lane"]), ("FF1", 1, 1))   # U2/A is above the path
        self.assertEqual(sch["wires"][-1]["from"], "FF1/Q")
        # FF1/D is driven by FF2/Q, already drawn: a link, not a second FF2.
        self.assertIn(("FF1/D", "link", "FF2/Q"), [(s["pin"], s["state"], s["driver"]) for s in sch["stubs"]])

    def test_lanes_below(self):
        # s27 FF5/D: U8/B lies below the path line, so FF6 opens in a lane below.
        src = engine("s27", "s27")
        sch = model.schematic(src.paths("FF5/D")["setup"], src, ["U9/A", "U8/B"])
        lanes = dict((e["name"], e["lane"]) for e in sch["elements"])
        self.assertEqual((lanes["U16"], lanes["FF6"]), (1, -1))

    def test_same_instance_launch_and_capture(self):
        src = engine("s27", "s27")
        sch = model.schematic(src.paths("FF7/D")["setup"], src)
        self.assertEqual([e["name"] for e in sch["elements"]], ["FF7", "U12", "U13", "FF7"])
        self.assertIn(("FF7/D", "link"), [(s["pin"], s["state"]) for s in sch["stubs"]])

    def test_geometry_everywhere(self):
        """Every endpoint x check x design, expanding every side input for three rounds: no
        boxes overlap, no wire runs through a box, every wire end is a pin, deterministic."""
        for scenario, netlist in DESIGNS:
            src = engine(scenario, netlist)
            for row in src.rows():
                for check, path in src.paths(row["pin"]).items():
                    if path is None:
                        continue
                    expanded = []
                    for _ in range(3):
                        sch = model.schematic(path, src, expanded)
                        expanded += [s["pin"] for s in sch["stubs"] if s["state"] == "expand"]
                    sch = model.schematic(path, src, expanded)
                    self.check_geometry(sch, (scenario, row["pin"], check))
                    self.assertEqual(sch, model.schematic(path, src, expanded))

    def check_geometry(self, sch, where):
        boxes = [(e["x0"], e["y0"], e["x1"], e["y1"]) for e in sch["elements"]]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertFalse(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3], (where, a, b))
        pins = set((p["x"], p["y"]) for e in sch["elements"] for p in e["pins"])
        for w in sch["wires"]:
            self.assertIn(w["points"][0], pins, where)
            self.assertIn(w["points"][-1], pins, where)
            for (xa, ya), (xb, yb) in zip(w["points"], w["points"][1:]):
                for x0, y0, x1, y1 in boxes:   # strictly inside a box = through it
                    inside_x = max(xa, xb) > x0 and min(xa, xb) < x1
                    inside_y = max(ya, yb) > y0 and min(ya, yb) < y1
                    self.assertFalse(inside_x and inside_y and (xa == xb or ya == yb) and
                                     x0 < (xa + xb) / 2.0 < x1 and y0 < (ya + yb) / 2.0 < y1, (where, w))


class SourceTests(unittest.TestCase):
    """R28: one interface for the engine and for a saved bundle."""

    def test_engine(self):
        src = engine("ff2_default", "ff2")
        self.assertEqual(src.instance("FF1"), {"cell": "DFF", "pins": [
            {"name": "CK", "direction": "input", "clock": True},
            {"name": "D", "direction": "input", "clock": False},
            {"name": "Q", "direction": "output", "clock": False}]})
        self.assertEqual((src.driver("U2/A"), src.driver("FF1/CK"), src.driver("x")), ("FF1/Q", None, None))
        self.assertEqual(src.arrival("U2/Y", "setup"), (4.0, "r"))
        self.assertEqual(src.arrival("FF1/CK", "hold"), (0.0, "r"))
        pin = src.pin("U2/Y")
        self.assertEqual((fmt4(pin["rat"]["late"]["f"]), fmt4(pin["load"])), ("9.7000", "0.0020"))
        self.assertEqual([(a["from"], a["to"], a["kind"]) for a in src.arcs("U2")],
                         [("U2/A", "U2/Y", "cell"), ("U2/B", "U2/Y", "cell")])
        self.assertEqual(fmt4(src.arcs("U2")[0]["delay"]["late"]["rf"]), "2.0000")
        self.assertEqual(src.summary("setup")["nvp"], 0)

    def test_bundle_matches_engine(self):
        src = engine("s27", "s27")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.json")
            with open(path, "w") as f:
                json.dump(bundle.debug_bundle(src.g, "FF5/D", depth=2), f)
            b = BundleSource(path)
        self.assertEqual([r["pin"] for r in b.rows()], ["FF5/D"])
        self.assertEqual(b.paths("FF5/D")["setup"]["slack"], 1.1373)
        for pin in b.nodes:
            self.assertEqual(b.arrival(pin, "setup")[1], src.arrival(pin, "setup")[1], pin)
            if "/" in pin:
                self.assertEqual(b.instance(pin.split("/")[0]), src.instance(pin.split("/")[0]))
            if b.driver(pin) is not None:
                self.assertEqual(b.driver(pin), src.driver(pin))
        # The path reaches past depth 2; its cells are still in "instances".
        for q in b.paths("FF5/D")["setup"]["points"]:
            if q["cell"]:
                b.instance(q["pin"].split("/")[0])
        self.assertIsNone(b.summary("setup"))

    def test_bundle_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = {"x.json": "{not json", "y.json": '{"schema": "x"}',
                     "z.json": '{"schema": "sta_toy.bundle/1"}'}
            for name, text in cases.items():
                with open(os.path.join(tmp, name), "w") as f:
                    f.write(text)
            for name, message in (("x.json", "is not JSON"), ("y.json", "is not a sta_toy.bundle/1 bundle"),
                                  ("z.json", "has no instances"), ("missing.json", "cannot read")):
                with self.assertRaises(P2Error) as cm:
                    BundleSource(os.path.join(tmp, name))
                self.assertIn(message, cm.exception.message)


class ThemeTests(unittest.TestCase):
    def test_palettes(self):
        keys = set(theme.THEMES["light"])
        for name in theme.NAMES:
            self.assertEqual(set(theme.THEMES[name]), keys, name)
            for v in theme.THEMES[name].values():
                self.assertRegex(v, r"^#[0-9a-f]{6}$")

    def test_fonts(self):
        self.assertEqual(theme.pick_font(("A", "B", "C"), {"B", "C"}), "B")
        self.assertEqual(theme.pick_font(("A", "B"), set()), "B")


def run_viewer(*args):
    return subprocess.run([sys.executable, "-m", "sta_toy.viewer"] + list(args), cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)


class ViewerCliTests(unittest.TestCase):
    """R29: start-up errors follow cli_p2.md (one stderr line, exit 1)."""

    def assertError(self, result, line):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr.decode(), line + "\n")

    def test_options(self):
        self.assertError(run_viewer("--lib", LIB, "--verilog", FF2_V, "--sdc", sdc("ff2_default"),
                                    "--depth", "2"), "error: unknown option --depth")
        self.assertError(run_viewer("--lib", LIB, "--verilog", FF2_V), "error: missing --sdc")
        self.assertError(run_viewer("--bundle"), "error: missing value for --bundle")
        self.assertError(run_viewer("--bundle", "b.json", "--lib", LIB),
                         "error: --bundle cannot be combined with --lib, --verilog or --sdc")
        self.assertError(run_viewer("--lib", LIB, "--verilog", FF2_V, "--sdc", sdc("ff2_default"),
                                    "--theme", "neon"), "error: --theme needs one of light, dark, contrast")

    def test_load_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w") as f:
                f.write("{not json")
            self.assertError(run_viewer("--bundle", bad), "error: %s is not JSON" % bad)
            missing = os.path.join(tmp, "nope.lib")
            self.assertError(run_viewer("--lib", missing, "--verilog", FF2_V, "--sdc", sdc("ff2_default")),
                             "ERROR %s: cannot read file: No such file or directory" % missing)

    def test_no_tkinter(self):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("this Python has tkinter")
        self.assertError(run_viewer("--lib", LIB, "--verilog", FF2_V, "--sdc", sdc("ff2_default")),
                         "error: the viewer needs a Python with tkinter")


def tk_works():
    """Whether this Python can open a Tk window. Probed in a subprocess: some Tk builds
    abort the whole process instead of raising TclError (the macOS system Tk 8.5)."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False
    probe = subprocess.run([sys.executable, "-c", "import tkinter; tkinter.Tk().destroy()"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    return probe.returncode == 0


@unittest.skipUnless(tk_works(), "tkinter missing or Tk() cannot open a window")
class TkSmokeTests(unittest.TestCase):
    """R29: build the window on a withdrawn root and drive it without clicks."""

    def setUp(self):
        import tkinter
        from sta_toy.viewer.app import App
        self.App = App
        self.root = tkinter.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_engine_mode_in_every_theme(self):
        for name in theme.NAMES:
            app = self.App(self.root, engine("s27", "s27"), name)
            self.assertEqual(app.endpoint, "G17")                       # worst setup first
            app.select_endpoint("FF5/D")
            rows = len(model.stages(app.path())) + len(model.capture_rows(app.path()))
            self.assertEqual(len(app.table.find_withtag("all")) > rows, True)
            app.expand("U9/A")
            app.set_check("hold")
            app.set_check("setup")
            self.assertEqual(app.expansions[("FF5/D", "setup")], ["U9/A"])   # kept per check
            app.step(-1)
            self.assertEqual(app.selected, "U10/Y")              # FF5/D <- U10/Y over the net
            app.select_pin("U15/Y")
            self.assertIn("U15/Y", app.inspector.get("1.0", "end"))
            app.select_cell("U9")
            self.assertIn("NAND2", app.inspector.get("1.0", "end"))
            app.set_zoom(1.5)
            app.fit()
            app.select_endpoint("G17")
            app.set_check("hold")                                        # no hold path
            self.assertIsNone(app.layout)
            self.assertTrue(app.sch.find_all())
            app.set_theme("dark")
            self.assertEqual(app.errors, [], name)

    def test_bundle_mode(self):
        src = engine("ff2_default", "ff2")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.json")
            with open(path, "w") as f:
                json.dump(bundle.debug_bundle(src.g, "FF2/D", depth=1), f)
            app = self.App(self.root, BundleSource(path), "contrast")
        self.assertEqual(app.endpoint, "FF2/D")
        app.expand("U2/A")
        self.assertTrue(any(e["name"] == "FF1" for e in app.layout["elements"]))
        self.assertEqual(app.errors, [])


if __name__ == "__main__":
    unittest.main()
