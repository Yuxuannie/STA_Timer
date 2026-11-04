"""R28, R29: the viewer model, the sources, the viewer CLI and a Tk smoke test.
Expected values come from viewer_p4.md / bundle_v1.md by hand and from the P2 golden files."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

from sta_toy import P2Error, StaError
from sta_toy.tsv import fmt4
from sta_toy.viewer import model
from sta_toy.viewer.source import BundleSource, EngineSource

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "data", "toy2.lib")
FF2_V = os.path.join(ROOT, "data", "ff2.v")


def sdc(scenario):
    return os.path.join(ROOT, "data", "sdc", scenario + ".sdc")


def golden_endpoints(scenario):
    with open(os.path.join(ROOT, "tests", "golden", scenario, "endpoints.tsv")) as f:
        lines = f.read().splitlines()
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"))) for line in lines[1:]]


def four(late_r, late_f, early_r, early_f):
    return {"late": {"r": late_r, "f": late_f}, "early": {"r": early_r, "f": early_f}}


def node(pin, cell, kind, depth, at, rat, slack, cap):
    slew = four(*[None if v is None else 0.05 for v in at])
    return {"pin": pin, "cell": cell, "kind": kind, "depth": depth, "at": four(*at),
            "rat": four(*rat), "slew": slew, "slack": {"setup": slack[0], "hold": slack[1]},
            "cap": cap}


def edge(u, v, kind):
    if kind == "check":
        return {"u": u, "v": v, "kind": kind, "delay": None,
                "check": {"setup": {"r": 0.3, "f": 0.3}, "hold": {"r": 0.1, "f": 0.1}}}
    pairs = {"net": {"rr": 0.0, "rf": None, "fr": None, "ff": 0.0},
             "cell": {"rr": None, "rf": 2.0, "fr": 2.0, "ff": None}}[kind]
    return {"u": u, "v": v, "kind": kind, "delay": {"late": dict(pairs), "early": dict(pairs)},
            "check": None}


def point(pin, cell, arc, rf, incr, at, cap=None):
    return {"pin": pin, "cell": cell, "arc": arc, "rf": rf, "incr": incr, "at": at, "slew": 0.05,
            "cap": cap}


# ff2_default FF2/D, worst setup and hold paths: tests/golden/reports/ff2_default_FF2_D_*.txt.
SETUP_PATH = {
    "id": "setup", "type": "max", "check": "setup", "start": "x", "end": "FF2/D",
    "launch_clock": "clk", "capture_clock": "clk",
    "points": [point("x", None, "start", "f", 0.0, 0.5, 0.0015),
               point("U1/A", "BUF", "net", "f", 0.0, 0.5),
               point("U1/Y", "BUF", "cell", "f", 1.5, 2.0, 0.002),
               point("U2/B", "NAND2", "net", "f", 0.0, 2.0),
               point("U2/Y", "NAND2", "cell", "r", 2.0, 4.0, 0.002),
               point("FF2/D", "DFF", "net", "r", 0.0, 4.0)],
    "launch": {"clock_edge": 0.0, "latency": None, "input_delay": 0.5},
    "capture": {"clock_edge": 10.0, "latency": 0.0, "uncertainty": 0.0, "check": 0.3,
                "output_delay": None, "rat": 9.7, "pin": "FF2/CK", "cell": "DFF"},
    "arrival": 4.0, "required": 9.7, "slack": 5.7}
HOLD_PATH = {
    "id": "hold", "type": "min", "check": "hold", "start": "FF1/CK", "end": "FF2/D",
    "launch_clock": "clk", "capture_clock": "clk",
    "points": [point("FF1/CK", "DFF", "start", "r", 0.0, 0.0),
               point("FF1/Q", "DFF", "ckq", "f", 1.0, 1.0, 0.002),
               point("U2/A", "NAND2", "net", "f", 0.0, 1.0),
               point("U2/Y", "NAND2", "cell", "r", 2.0, 3.0, 0.002),
               point("FF2/D", "DFF", "net", "r", 0.0, 3.0)],
    "launch": {"clock_edge": 0.0, "latency": 0.0, "input_delay": None},
    "capture": {"clock_edge": 0.0, "latency": 0.0, "uncertainty": 0.0, "check": 0.1,
                "output_delay": None, "rat": 0.1, "pin": "FF2/CK", "cell": "DFF"},
    "arrival": 3.0, "required": 0.1, "slack": 2.9}
# ff2_default y setup (FF2/CK -> FF2/Q -> y), a PO endpoint: no capture CK pin.
PO_PATH = {
    "id": "p5", "type": "max", "check": "setup", "start": "FF2/CK", "end": "y",
    "launch_clock": "clk", "capture_clock": "clk",
    "points": [point("FF2/CK", "DFF", "start", "r", 0.0, 0.0),
               point("FF2/Q", "DFF", "ckq", "r", 1.0, 1.0, 0.004),
               point("y", None, "net", "r", 0.0, 1.0)],
    "launch": {"clock_edge": 0.0, "latency": 0.0, "input_delay": None},
    "capture": {"clock_edge": 10.0, "latency": None, "uncertainty": None, "check": None,
                "output_delay": 2.0, "rat": 8.0, "pin": None, "cell": None},
    "arrival": 1.0, "required": 8.0, "slack": 7.0}

# The bundle of ff2_default FF2/D with depth 1, by bundle_v1.md and pins.tsv: U2/Y reaches
# FF2/D over a net edge (depth 0), U2/A, U2/B one cell arc further, FF1/Q and U1/Y over nets.
# The endpoint comes first, then (depth, name).
BUNDLE = {
    "schema": "sta_toy.bundle/1", "endpoint": "FF2/D", "depth": 1, "max_nodes": 300,
    "truncated": False, "clock": {"name": "clk", "period": 10.0},
    "nodes": [node("FF2/D", "DFF", "D", 0, (4.0, 4.0, 3.0, 3.0), (9.7, 9.7, 0.1, 0.1), (5.7, 2.9), None),
              node("FF2/CK", "DFF", "CK", 0, (0.0, None, 0.0, None), (7.0, None, -0.9, None), (7.0, 0.9), None),
              node("U2/Y", "NAND2", "other", 0, (4.0, 4.0, 3.0, 3.0), (9.7, 9.7, 0.1, 0.1), (5.7, 2.9), 0.002),
              node("FF1/Q", "DFF", "other", 1, (1.0, 1.0, 1.0, 1.0), (7.7, 7.7, -1.9, -1.9), (6.7, 2.9), 0.002),
              node("U1/Y", "BUF", "other", 1, (2.0, 2.0, 2.0, 2.0), (7.7, 7.7, -1.9, -1.9), (5.7, 3.9), 0.002),
              node("U2/A", "NAND2", "other", 1, (1.0, 1.0, 1.0, 1.0), (7.7, 7.7, -1.9, -1.9), (6.7, 2.9), None),
              node("U2/B", "NAND2", "other", 1, (2.0, 2.0, 2.0, 2.0), (7.7, 7.7, -1.9, -1.9), (5.7, 3.9), None)],
    "edges": [edge("FF2/CK", "FF2/D", "check"), edge("U2/Y", "FF2/D", "net"),
              edge("FF1/Q", "U2/A", "net"), edge("U1/Y", "U2/B", "net"),
              edge("U2/A", "U2/Y", "cell"), edge("U2/B", "U2/Y", "cell")],
    "paths": [SETUP_PATH, HOLD_PATH]}


def pins(rows):
    return [r["pin"] for r in rows]


class EndpointTableTests(unittest.TestCase):
    """R28: sort (None last, ties by pin), filter, paging."""

    ROWS = [{"pin": "b", "kind": "D", "setup_slack": 1.0, "hold_slack": None},
            {"pin": "a", "kind": "PO", "setup_slack": 1.0, "hold_slack": 0.5},
            {"pin": "C/D", "kind": "D", "setup_slack": None, "hold_slack": -0.2},
            {"pin": "d", "kind": "D", "setup_slack": -3.0, "hold_slack": 0.5}]

    def test_default_order_is_pin(self):
        t = model.EndpointTable(self.ROWS)
        self.assertEqual(pins(t.page(0)), ["C/D", "a", "b", "d"])

    def test_sort_none_last_and_pin_ties(self):
        t = model.EndpointTable(self.ROWS)
        t.sort("setup_slack")
        self.assertEqual(pins(t.page(0)), ["d", "a", "b", "C/D"])
        t.sort("setup_slack", descending=True)
        self.assertEqual(pins(t.page(0)), ["a", "b", "d", "C/D"])
        t.sort("hold_slack")
        self.assertEqual(pins(t.page(0)), ["C/D", "a", "d", "b"])
        t.sort("hold_slack", descending=True)
        self.assertEqual(pins(t.page(0)), ["a", "d", "C/D", "b"])
        t.sort("pin", descending=True)
        self.assertEqual(pins(t.page(0)), ["d", "b", "a", "C/D"])
        t.sort("kind")
        self.assertEqual(pins(t.page(0)), ["C/D", "b", "d", "a"])

    def test_filter(self):
        t = model.EndpointTable(self.ROWS)
        t.filter("c/")
        self.assertEqual(pins(t.page(0)), ["C/D"])
        t.filter("A")
        self.assertEqual(pins(t.page(0)), ["a"])
        t.filter("zz")
        self.assertEqual((t.page(0), t.pages()), ([], 1))
        t.filter("")
        self.assertEqual(len(t.page(0)), 4)

    def test_paging(self):
        t = model.EndpointTable([{"pin": "p%03d" % i, "kind": "D", "setup_slack": float(i),
                                  "hold_slack": None} for i in range(120)])
        self.assertEqual(t.pages(), 3)
        self.assertEqual(t.pages(size=10), 12)
        self.assertEqual(pins(t.page(0))[:2], ["p000", "p001"])
        self.assertEqual(pins(t.page(2)), ["p%03d" % i for i in range(100, 120)])
        self.assertEqual(t.page(3), [])
        self.assertEqual(pins(t.page(1, size=7)), ["p%03d" % i for i in range(7, 14)])
        t.sort("setup_slack", descending=True)
        self.assertEqual(pins(t.page(0))[0], "p119")
        t.filter("p11")
        self.assertEqual((len(t.page(0)), t.pages()), (10, 1))
        self.assertEqual(model.EndpointTable([]).pages(), 1)

    def test_from_bundle(self):
        self.assertEqual(model.EndpointTable.from_bundle(BUNDLE).rows,
                         [{"pin": "FF2/D", "kind": "D", "setup_slack": 5.7, "hold_slack": 2.9}])

    def test_from_graph_against_golden(self):
        from sta_toy import design
        for scenario in ("ff2_default", "ff2_setupviol"):
            g = design.timed(*design.load([LIB], FF2_V), sdc(scenario))
            rows = sorted(model.EndpointTable.from_graph(g).rows, key=lambda r: r["pin"])
            self.assertEqual([(r["pin"], fmt4(r["setup_slack"]), fmt4(r["hold_slack"])) for r in rows],
                             [(r["pin"], r["setup_slack"], r["hold_slack"])
                              for r in golden_endpoints(scenario)])
            self.assertEqual([r["kind"] for r in rows], ["D", "D", "PO"])


class TimelineTests(unittest.TestCase):
    """R28: timeline items and the time -> pixel mapping (viewer_p4.md)."""

    def items(self, path, width, margin):
        return {it["kind"]: (it["x0"], it["x1"], it["label"]) for it in model.timeline(path, width, margin)}

    def assertItems(self, got, expected):
        self.assertEqual(sorted(got), sorted(expected))
        for kind, (x0, x1, label) in expected.items():
            self.assertAlmostEqual(got[kind][0], x0, places=6, msg=kind)
            self.assertAlmostEqual(got[kind][1], x1, places=6, msg=kind)
            self.assertEqual(got[kind][2], label)

    def test_setup(self):
        # span [0, 10] onto [40, 460]: 42 px per ns.
        self.assertItems(self.items(SETUP_PATH, 500, 40), {
            "launch_edge": (40, 40, "launch edge 0.0000"),
            "capture_edge": (460, 460, "capture edge 10.0000"),
            "arrival": (208, 208, "arrival 4.0000"),
            "required": (447.4, 447.4, "required 9.7000"),
            "data": (61, 208, "data 0.5000 -> 4.0000"),
            "window": (447.4, 460, "setup window 9.7000 -> 10.0000")})

    def test_hold(self):
        # span [0, 3] (arrival) onto [20, 320]: 100 px per ns.
        self.assertItems(self.items(HOLD_PATH, 340, 20), {
            "launch_edge": (20, 20, "launch edge 0.0000"),
            "capture_edge": (20, 20, "capture edge 0.0000"),
            "arrival": (320, 320, "arrival 3.0000"),
            "required": (30, 30, "required 0.1000"),
            "data": (20, 320, "data 0.0000 -> 3.0000"),
            "window": (20, 30, "hold window 0.0000 -> 0.1000")})

    def test_po_has_no_window(self):
        # span [0, 10] (no capture latency) onto [20, 520]: 50 px per ns.
        self.assertItems(self.items(PO_PATH, 540, 20), {
            "launch_edge": (20, 20, "launch edge 0.0000"),
            "capture_edge": (520, 520, "capture edge 10.0000"),
            "arrival": (70, 70, "arrival 1.0000"),
            "required": (420, 420, "required 8.0000"),
            "data": (20, 70, "data 0.0000 -> 1.0000")})

    def test_negative_start(self):
        # A start AT of -2 moves the span to [-2, 10]: onto [20, 620] at 50 px per ns.
        path = copy.deepcopy(SETUP_PATH)
        path["points"][0]["at"] = -2.0
        got = self.items(path, 640, 20)
        self.assertAlmostEqual(got["launch_edge"][0], 120)
        self.assertAlmostEqual(got["data"][0], 20)
        self.assertAlmostEqual(got["capture_edge"][0], 620)

    def test_negative_required(self):
        # ff2_default y hold: required = 0 - 0.5. The span is [-0.5, 1.0] onto [20, 320],
        # 200 px per ns, so required sits on the left margin instead of off the canvas.
        path = copy.deepcopy(HOLD_PATH)
        path["capture"].update({"pin": None, "cell": None, "latency": None, "uncertainty": None,
                                "check": None, "output_delay": 0.5, "rat": -0.5})
        path.update({"required": -0.5, "arrival": 1.0})
        got = self.items(path, 340, 20)
        self.assertAlmostEqual(got["required"][0], 20)
        self.assertAlmostEqual(got["launch_edge"][0], 120)
        for x0, x1, _ in got.values():
            self.assertTrue(20 <= x0 <= 320 and 20 <= x1 <= 320)


class ConeLayoutTests(unittest.TestCase):
    """R28: columns by depth (0 on the right), rows by name, on_path edges."""

    def test_positions(self):
        layout = model.cone_layout(BUNDLE, 700, 400, margin=50)
        self.assertEqual(layout["nodes"], {
            "FF2/CK": (650, 50), "FF2/D": (650, 200), "U2/Y": (650, 350),
            "FF1/Q": (50, 50), "U1/Y": (50, 150), "U2/A": (50, 250), "U2/B": (50, 350)})

    def test_three_columns(self):
        b = copy.deepcopy(BUNDLE)
        b["nodes"].append(node("x", None, "PI", 2, (0.5,) * 4, (6.2,) * 4, (5.7, 0.5), 0.0015))
        layout = model.cone_layout(b, 500, 300, margin=50)
        self.assertEqual([layout["nodes"][p] for p in ("FF2/D", "U2/B", "x")],
                         [(450, 150), (250, 250), (50, 150)])

    def test_single_node(self):
        b = dict(BUNDLE, nodes=BUNDLE["nodes"][0:1], edges=[], paths=[])
        self.assertEqual(model.cone_layout(b, 300, 200)["nodes"], {"FF2/D": (260, 100)})

    def test_edges_on_path(self):
        layout = model.cone_layout(BUNDLE, 700, 400)
        self.assertEqual(layout["edges"], [
            ("FF2/CK", "FF2/D", "check", False), ("U2/Y", "FF2/D", "net", True),
            ("FF1/Q", "U2/A", "net", True), ("U1/Y", "U2/B", "net", True),
            ("U2/A", "U2/Y", "cell", True), ("U2/B", "U2/Y", "cell", True)])
        self.assertEqual(layout["path_pins"], {"x", "U1/A", "U1/Y", "U2/B", "U2/Y", "FF2/D",
                                               "FF1/CK", "FF1/Q", "U2/A"})
        setup_only = model.cone_layout(dict(BUNDLE, paths=[SETUP_PATH]), 700, 400)
        self.assertEqual([e[3] for e in setup_only["edges"]], [False, True, False, True, False, True])


class NodeDetailsTests(unittest.TestCase):
    """R28: node_details lines (values from pins.tsv of ff2_default)."""

    HEADER = "          late r    late f   early r   early f"

    def test_cell_output(self):
        self.assertEqual(model.node_details(BUNDLE, "U2/Y"), [
            "kind: other", "cell: NAND2", "depth: 0", "cap: 0.0020", self.HEADER,
            "AT        4.0000    4.0000    3.0000    3.0000",
            "RAT       9.7000    9.7000    0.1000    0.1000",
            "SLEW      0.0500    0.0500    0.0500    0.0500",
            "setup slack: 5.7000", "hold slack: 2.9000"])

    def test_clock_pin_with_na(self):
        self.assertEqual(model.node_details(BUNDLE, "FF2/CK"), [
            "kind: CK", "cell: DFF", "depth: 0", "cap: NA", self.HEADER,
            "AT        0.0000        NA    0.0000        NA",
            "RAT       7.0000        NA   -0.9000        NA",
            "SLEW      0.0500        NA    0.0500        NA",
            "setup slack: 7.0000", "hold slack: 0.9000"])

    def test_port(self):
        b = dict(BUNDLE, nodes=[node("x", None, "PI", 2, (0.5,) * 4, (6.2,) * 4, (5.7, None), 0.0015)])
        lines = model.node_details(b, "x")
        self.assertEqual(lines[:4], ["kind: PI", "cell: -", "depth: 2", "cap: 0.0015"])
        self.assertEqual(lines[-1], "hold slack: NA")


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            f.write(text)
        return path


class SourceTests(TempDirTest):
    """R28: BundleSource and EngineSource."""

    def test_bundle_source(self):
        s = BundleSource(self.write("b.json", json.dumps(BUNDLE, indent=2) + "\n"))
        self.assertEqual((s.mode, s.clock_name), ("bundle", "clk"))
        self.assertEqual(s.rows(), [{"pin": "FF2/D", "kind": "D", "setup_slack": 5.7, "hold_slack": 2.9}])
        self.assertEqual(s.bundle("FF2/D"), BUNDLE)

    def test_bundle_source_errors(self):
        cases = [(os.path.join(self.tmp, "missing.json"), "error: cannot read "),
                 (self.write("bad.json", "{not json"), "error: %s is not JSON"),
                 (self.write("list.json", "[]"), "error: %s is not a sta_toy.bundle/1 bundle"),
                 (self.write("report.json", '{"schema": "sta_toy.report/1"}'),
                  "error: %s is not a sta_toy.bundle/1 bundle")]
        for path, message in cases:
            with self.assertRaises(P2Error) as cm:
                BundleSource(path)
            self.assertIsNone(cm.exception.file)
            text = message % path if "%s" in message else message
            self.assertTrue(str(cm.exception).startswith(text), str(cm.exception))

    def test_engine_source(self):
        s = EngineSource([LIB], FF2_V, sdc("ff2_default"))
        self.assertEqual((s.mode, s.clock_name), ("engine", "clk"))
        rows = sorted(s.rows(), key=lambda r: r["pin"])
        self.assertEqual([(r["pin"], fmt4(r["setup_slack"]), fmt4(r["hold_slack"])) for r in rows],
                         [(r["pin"], r["setup_slack"], r["hold_slack"])
                          for r in golden_endpoints("ff2_default")])
        b = s.bundle("FF2/D", depth=1)
        self.assertEqual((b["endpoint"], b["depth"], b["max_nodes"]), ("FF2/D", 1, 300))
        self.assertEqual([n["pin"] for n in b["nodes"]], [n["pin"] for n in BUNDLE["nodes"]])

    def test_engine_source_errors(self):
        with self.assertRaises(StaError):
            EngineSource([os.path.join(self.tmp, "nope.lib")], FF2_V, sdc("ff2_default"))


def run_viewer(*args):
    return subprocess.run([sys.executable, "-m", "sta_toy.viewer"] + list(args), cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)


class ViewerCliTests(TempDirTest):
    """R29: start-up errors follow cli_p2.md (one stderr line, exit 1)."""

    def assertError(self, result, line):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr.decode(), line + "\n")

    def test_unknown_option(self):
        self.assertError(run_viewer("--lib", LIB, "--verilog", FF2_V, "--sdc", sdc("ff2_default"),
                                    "--depth", "2"), "error: unknown option --depth")

    def test_missing_sdc(self):
        self.assertError(run_viewer("--lib", LIB, "--verilog", FF2_V), "error: missing --sdc")

    def test_missing_value(self):
        self.assertError(run_viewer("--bundle"), "error: missing value for --bundle")

    def test_bundle_with_engine_options(self):
        self.assertError(run_viewer("--bundle", "b.json", "--lib", LIB),
                         "error: --bundle cannot be combined with --lib, --verilog or --sdc")

    def test_bad_bundle_file(self):
        path = self.write("bad.json", "{not json")
        self.assertError(run_viewer("--bundle", path), "error: %s is not JSON" % path)
        path = self.write("other.json", '{"schema": "x"}')
        self.assertError(run_viewer("--bundle", path),
                         "error: %s is not a sta_toy.bundle/1 bundle" % path)

    def test_engine_load_error(self):
        missing = os.path.join(self.tmp, "nope.lib")
        self.assertError(run_viewer("--lib", missing, "--verilog", FF2_V, "--sdc", sdc("ff2_default")),
                         "ERROR %s: cannot read file: No such file or directory" % missing)

    def test_no_tkinter(self):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("this Python has tkinter")
        path = self.write("b.json", json.dumps(BUNDLE))
        self.assertError(run_viewer("--bundle", path),
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


TK = tk_works()


@unittest.skipUnless(TK, "tkinter missing or Tk() cannot open a window")
class TkSmokeTests(TempDirTest):
    """R29: build the window on a withdrawn root and drive it without clicks."""

    def setUp(self):
        TempDirTest.setUp(self)
        import tkinter
        from sta_toy.viewer.app import App
        self.App = App
        self.root = tkinter.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()
        TempDirTest.tearDown(self)

    def text(self, widget):
        return widget.get("1.0", "end")

    def test_engine_mode(self):
        app = self.App(self.root, EngineSource([LIB], FF2_V, sdc("ff2_default")))
        self.root.update()
        # Sorted by setup slack (golden endpoints.tsv: 5.7, 7.0, 8.7); the worst is loaded.
        self.assertEqual(app.tree.get_children(), ("FF2/D", "y", "FF1/D"))
        self.assertEqual((app.endpoint, app.tree.selection()), ("FF2/D", ("FF2/D",)))
        app.select_endpoint("y")
        app.select_endpoint("FF2/D")
        self.root.update()
        self.assertEqual(app.tree.selection(), ("FF2/D",))
        self.assertIn("Path Type: max", self.text(app.path_text))
        self.assertIn("slack (MET)", self.text(app.path_text))
        self.assertTrue(app.timeline_canvas.find_all())
        self.assertEqual(len(app.cone.find_withtag("node")), 4 * len(app.data["nodes"]))
        app.show_check("hold")
        self.assertIn("Path Type: min", self.text(app.path_text))
        self.assertIn("FF1/CK (DFF)", self.text(app.path_text))
        app.select_node("U2/Y")
        self.assertIn("cell: NAND2", self.text(app.details))
        app.reload_cone(1)
        self.assertEqual([n["pin"] for n in app.data["nodes"]], [n["pin"] for n in BUNDLE["nodes"]])
        self.assertEqual((app.node, app.banner.cget("text")), ("U2/Y", ""))
        app.reload_cone(1, 3)
        self.assertIn("TRUNCATED", app.banner.cget("text"))
        self.assertIn("TRUNCATED", app.status.get())
        app.sort_by("pin")
        self.assertEqual(app.tree.get_children(), ("FF1/D", "FF2/D", "y"))
        app.sort_by("pin")
        self.assertEqual(app.tree.get_children(), ("y", "FF2/D", "FF1/D"))
        app.set_filter("ff")
        self.assertEqual(app.tree.get_children(), ("FF2/D", "FF1/D"))
        self.assertEqual(app.page_label.get(), "page 1 / 1")
        self.root.update()

    def test_negative_slack_red(self):
        app = self.App(self.root, EngineSource([LIB], FF2_V, sdc("ff2_setupviol")))
        self.root.update()
        # golden ff2_setupviol: FF2/D setup slack -0.3000.
        self.assertEqual(app.tree.item("FF2/D", "tags"), ("negative",))
        self.assertEqual(app.tree.item("y", "tags"), "")
        self.assertIn("slack (VIOLATED)", self.text(app.path_text))

    def test_bundle_mode(self):
        app = self.App(self.root, BundleSource(self.write("b.json", json.dumps(BUNDLE))))
        self.root.update()
        self.assertEqual(app.tree.get_children(), ("FF2/D",))
        self.assertEqual(str(app.reload_button.cget("state")), "disabled")
        self.assertIn("slack (MET)", self.text(app.path_text))
        app.select_node("FF2/CK")
        self.assertIn("kind: CK", self.text(app.details))


if __name__ == "__main__":
    unittest.main()
