"""R28, R29: the viewer v2 (viewer_p4.md) — endpoint list, pin-to-pin stages, capture rows,
path schematic, sources, themes, the viewer CLI and a Tk smoke test. Expected values come
from the contract by hand and from the P2 golden files."""

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

from sta_toy import P2Error, bundle
from sta_toy.tsv import fmt4
from sta_toy.viewer import model, sizing, theme
from sta_toy.viewer.source import BundleSource, EngineSource

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "data", "toy2.lib")
FF2_V = os.path.join(ROOT, "data", "ff2.v")
S1423 = (os.path.join(ROOT, "data", "s1423.v"), os.path.join(ROOT, "data", "sdc", "s1423.sdc"))   # W3, R38
DESIGNS = [("ff2_default", "ff2"), ("ff2_swap", "ff2"), ("ff2_setupviol", "ff2"),
           ("ff2_holdviol", "ff2"), ("ff2_skew", "ff2"), ("ff2_unc", "ff2"),
           ("inv2", "inv2"), ("s27", "s27")]
MODE = {"setup": "late", "hold": "early"}
THIN = "\u2009"
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
                         [("U2/A", "expand", "FF1/Q", "1.0000 r"), ("FF2/CK", "clock", None, "0.0000")])
        self.assertEqual([b["text"] for b in sch["badges"]], ["0.5000 f", "2.0000 f", "4.0000 r"])
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
        self.assertEqual(src.instance("FF1"), {"cell": "DFF", "sequential": True, "pins": [
            {"name": "CK", "direction": "input", "clock": True, "function": None},
            {"name": "D", "direction": "input", "clock": False, "function": None},
            {"name": "Q", "direction": "output", "clock": False, "function": "IQ"}]})
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
            self.assertEqual(b.pin(pin)["fanout"], src.pin(pin)["fanout"], pin)   # R34
            if "/" in pin:
                self.assertEqual(b.instance(pin.split("/")[0]), src.instance(pin.split("/")[0]))
            if b.driver(pin) is not None:
                self.assertEqual(b.driver(pin), src.driver(pin))
        # The path reaches past depth 2; its cells are still in "instances".
        for q in b.paths("FF5/D")["setup"]["points"]:
            if q["cell"]:
                b.instance(q["pin"].split("/")[0])
        self.assertIsNone(b.summary("setup"))

    def test_bundle_without_instances(self):
        # R33: the P4 compatibility path is gone; such a bundle is an error again.
        b = bundle.debug_bundle(engine("s27", "s27").g, "FF5/D", depth=1)
        del b["instances"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.json")
            with open(path, "w") as f:
                json.dump(b, f)
            with self.assertRaises(P2Error) as cm:
                BundleSource(path)
            self.assertEqual(str(cm.exception), "error: bundle has no instances: write it again with --bundle")

    def test_merges(self):
        src = engine("s27", "s27")
        # U9/Y falls: B and A rise at 4.44; A's slew 0.054 vs B's 0.056 -> 2.0 x 0.002 = 0.004.
        fanin = src.fanin("U9/Y", "setup", "f")
        self.assertEqual([(c["from"], c["rf"], fmt4(c["value"]), fmt4(c["margin"])) for c in fanin],
                         [("U9/B", "r", "6.4520", "0.0000"), ("U9/A", "r", "6.4480", "0.0040")])
        # U14/Y drives U8/A (RAT 2.5706) and U10/A (RAT 9.0222): the smaller one binds (golden pins.tsv).
        fanout = src.fanout("U14/Y", "setup", "r")
        self.assertEqual([(c["to"], fmt4(c["value"])) for c in fanout], [("U8/A", "2.5706"), ("U10/A", "9.0222")])
        self.assertEqual(fmt4(fanout[1]["margin"]), "6.4516")
        hold = src.fanin("U9/Y", "hold", "f")
        self.assertEqual(hold[0]["value"], min(c["value"] for c in hold))

    def test_bundle_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = {"x.json": "{not json", "y.json": '{"schema": "x"}'}
            for name, text in cases.items():
                with open(os.path.join(tmp, name), "w") as f:
                    f.write(text)
            for name, message in (("x.json", "is not JSON"), ("y.json", "is not a sta_toy.bundle/1 bundle"),
                                  ("missing.json", "cannot read")):
                with self.assertRaises(P2Error) as cm:
                    BundleSource(os.path.join(tmp, name))
                self.assertIn(message, cm.exception.message)


class ViewModelTests(unittest.TestCase):
    """R28: the v3 views — symbols, summary, formula, histogram, profile, path table, waveform."""

    def test_symbols(self):
        src = engine("s27", "s27")
        self.assertEqual([model.symbol(src.instance(i)) for i in ("U14", "U8", "U15", "U9", "U10", "FF5")],
                         ["inv", "and", "or", "nand", "nor", "flop"])
        pin = lambda f: {"sequential": False, "pins": [{"direction": "output", "function": f}]}
        self.assertEqual([model.symbol(pin(f)) for f in ("A", "!(A&B&C)", "A^B", "!(A^B)", "(A&B)|C", None)],
                         ["buf", "nand", "xor", "xnor", "box", "box"])

    def test_summary_and_formula(self):
        # ff2_skew FF2/D hold: L_launch 0, ck->q 1.0, NAND 2.0, L_capture 0.5, t_hold 0.1 (DFF table).
        src = engine("ff2_skew", "ff2")
        hold = src.paths("FF2/D")["hold"]
        s = model.summary(hold)
        self.assertEqual((s["ckq"], s["data_path"], s["skew"], s["levels"]), (1.0, 2.0, 0.5, 1))
        f = model.formula(hold)
        self.assertEqual([(n, fmt4(v)) for n, v in f["arrival"]],
                         [("L_launch", "0.0000"), ("ck→q", "1.0000"), ("data path", "2.0000")])
        self.assertEqual([(n, fmt4(v)) for n, v in f["required"]],
                         [("edge", "0.0000"), ("L_capture", "0.5000"), ("t_hold", "0.1000"), ("unc_hold", "0.0000")])
        self.assertEqual(fmt4(sum(v for _, v in f["required"])), fmt4(hold["required"]))
        setup = model.formula(engine("s27", "s27").paths("FF5/D")["setup"])
        self.assertEqual([n for n, _ in setup["arrival"]], ["input delay", "data path"])
        self.assertEqual(fmt4(sum(v for _, v in setup["arrival"])), "8.6849")
        self.assertEqual(fmt4(sum(v for _, v in setup["required"])), "9.8222")

    def test_histogram(self):
        bins = model.histogram([-0.3, 2.7, 1.0, None], bins=3)
        self.assertEqual([(fmt4(b["lo"]), fmt4(b["hi"]), b["count"]) for b in bins],
                         [("-0.3000", "0.7000", 1), ("0.7000", "1.7000", 1), ("1.7000", "2.7000", 1)])
        self.assertEqual(model.histogram([None]), [])

    def test_path_table(self):
        src = engine("s27", "s27")
        pins = golden("s27", "pins.tsv")
        sections = model.path_table(src.paths("FF5/D")["setup"], src)
        self.assertEqual([s["title"] for s in sections], ["Input", "Data path", "Destination clock path"])
        for r in sections[1]["rows"]:
            rf = r["rf"][-1]
            self.assertEqual(fmt4(r["rat"]), pins[r["label"]]["rat_late_" + rf])
            self.assertEqual(fmt4(r["slack"]), fmt4(r["rat"] - r["value"]))
        self.assertEqual(fmt4(sections[1]["rows"][0]["slack"]), "0.3706")   # G0: worse path to G17
        self.assertEqual([r["label"] for r in sections[2]["rows"]],
                         ["clock clk (rise edge)", "clock latency", "FF5/CK", "clock uncertainty",
                          "library setup time"])
        flop = model.path_table(engine("ff2_default", "ff2").paths("FF2/D")["hold"], engine("ff2_default", "ff2"))
        self.assertEqual([r["label"] for r in flop[0]["rows"]], ["clock clk (rise edge)", "clock latency (ideal)", "FF1/CK"])

    def test_path_table_largest(self):
        # R33: the largest cell incr of the data path is marked (U10 NOR2 B->Y, 2.0120 in s27
        # FF5/D setup); ties mark all (ff2_holdviol FF2/D hold: CK->Q 1.0 vs NAND 2.0 -> one).
        rows = model.path_table(engine("s27", "s27").paths("FF5/D")["setup"], engine("s27", "s27"))[1]["rows"]
        self.assertEqual([(r["label"], fmt4(r["incr"])) for r in rows if r["largest"]], [("U9/Y", "2.0120")])
        path = copy.deepcopy(engine("s27", "s27").paths("FF5/D")["setup"])
        for q in path["points"]:
            if q["pin"] == "U14/Y":
                q["incr"] = 2.0120 + 1e-10                 # a tie within 1e-9
        rows = model.path_table(path, engine("s27", "s27"))[1]["rows"]
        self.assertEqual([r["label"] for r in rows if r["largest"]], ["U14/Y", "U9/Y"])

    def test_waveform(self):
        src = engine("ff2_skew", "ff2")
        p = src.paths("FF2/D")
        wave = model.waveform(p["setup"], p["hold"], src.period, "hold")
        rows = dict((r["name"], r) for r in wave["rows"])
        self.assertEqual((rows["launch clock"]["pin"], rows["capture clock"]["edges"]), ("FF1/CK", [0.5, 10.5]))
        data = [r for r in wave["rows"] if r["kind"] == "data"][0]
        self.assertEqual((data["early"], data["late"]), (3.0, 4.0))
        marks = dict((m["kind"], m) for m in wave["marks"])
        self.assertEqual(tuple(fmt4(v) for v in marks["hold"]["window"]), ("0.5000", "0.6000"))
        self.assertEqual(tuple(fmt4(v) for v in marks["setup"]["window"]), ("10.2000", "10.5000"))
        self.assertEqual((marks["setup"]["slack"], marks["hold"]["slack"]), (6.2, 2.4))
        self.assertLessEqual(wave["span"][0], 0.0)
        setup_view = model.waveform(p["setup"], p["hold"], src.period, "setup")
        self.assertEqual(setup_view["rows"][0]["pin"], "x")

    def test_waveform_edge_labels(self):
        # R33: every rising edge in the span is labelled with its time; ff2_holdviol FF2/D:
        # capture edges 3.5 and 13.5 (latency 3.5), never the falling edge 8.5.
        src = engine("ff2_holdviol", "ff2")
        p = src.paths("FF2/D")
        for check in ("setup", "hold"):
            rows = model.waveform(p["setup"], p["hold"], src.period, check)["rows"]
            self.assertEqual([text for _, text, _ in rows[1]["labels"]], ["3.5000", "13.5000"])
            self.assertEqual([text for _, text, _ in rows[0]["labels"]], ["0.0000", "10.0000"])
        # With real widths (span 14.58 over 600 px, labels 48 px = 1.166 time units): 3.5 would
        # cover the hold mark line at 3.6, so it goes left of its edge; 13.5 stays right of it
        # (the setup line at 13.2 lies left of the edge).
        wave = model.waveform(p["setup"], p["hold"], src.period, "hold", lambda text: 48, 600)
        self.assertEqual(wave["rows"][1]["labels"], [(3.5, "3.5000", "e"), (13.5, "13.5000", "w")])
        # Labels so wide that both sides of 3.5 hit a line or the span start: dropped.
        wave = model.waveform(p["setup"], p["hold"], src.period, "hold", lambda text: 240, 600)
        self.assertEqual([text for _, text, _ in wave["rows"][1]["labels"]], ["13.5000"])
        self.assertEqual([text for _, text, _ in wave["rows"][0]["labels"]], ["0.0000", "10.0000"])

    def blocks(self, scenario, netlist, endpoint, check, pin):
        src = engine(scenario, netlist)
        path = src.paths(endpoint)[check]
        k = [q["pin"] for q in path["points"]].index(pin)
        return path["points"][k], model.lookups(path, src, k)

    def test_lookup_blocks(self):
        # R34: the grid behind each lookup, at the arguments the engine used (the block's value
        # is the path's number). Slew axis below the grid where the source slew is 0: the CK pin
        # (s27 has no set_clock_transition) and G2 (no set_input_transition).
        slew = lambda d: d["extrapolated"][d["axes"].index("input_net_transition")]
        for endpoint, check, pin in (("FF7/D", "setup", "FF7/Q"), ("FF7/D", "hold", "U13/Y")):
            point, blocks = self.blocks("s27", "s27", endpoint, check, pin)
            self.assertEqual([label for label, _ in blocks], ["delay", "output slew"])
            self.assertEqual([slew(d) for _, d in blocks], ["below", "below"])
            self.assertEqual(fmt4(blocks[0][1]["value"]), fmt4(point["incr"]))
        # U14 is driven by G0 (slew 0.05): inside the grid; FF2/D's setup lookup has its CK
        # slew 0.05 inside too, s27 FF5/D's CK slew 0 is below.
        point, blocks = self.blocks("s27", "s27", "FF5/D", "setup", "U14/Y")
        self.assertEqual([d["extrapolated"] for _, d in blocks], [[None, None], [None, None]])
        self.assertEqual((fmt4(blocks[0][1]["value"]), fmt4(blocks[1][1]["value"])), (fmt4(point["incr"]), fmt4(point["slew"])))
        point, blocks = self.blocks("s27", "s27", "FF5/D", "setup", "FF5/D")
        self.assertEqual([(label, d["extrapolated"]) for label, d in blocks], [("t_setup", [None, "below"])])
        # ff2_default U2/Y: no extrapolation on either axis; the four corners bracket the query.
        point, blocks = self.blocks("ff2_default", "ff2", "FF2/D", "setup", "U2/Y")
        for label, d in blocks:
            self.assertEqual(d["extrapolated"], [None, None], label)
            for (lo, hi), q in zip(d["bracket"], d["query"]):
                self.assertTrue(lo <= q <= hi)
        point, blocks = self.blocks("ff2_default", "ff2", "FF2/D", "hold", "FF2/D")
        self.assertEqual(fmt4(blocks[0][1]["value"]), fmt4(engine("ff2_default", "ff2").paths("FF2/D")["hold"]["capture"]["check"]))
        self.assertEqual(self.blocks("ff2_default", "ff2", "FF2/D", "setup", "U2/B")[1], [])     # a net hop

    def test_lookup_blocks_bundle(self):
        # R34: a bundle has no tables, so no grid in bundle mode.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.json")
            with open(path, "w") as f:
                json.dump(bundle.debug_bundle(engine("ff2_default", "ff2").g, "FF2/D", depth=2), f)
            b = BundleSource(path)
        p = b.paths("FF2/D")["setup"]
        self.assertEqual([model.lookups(p, b, k) for k in range(len(p["points"]))], [[]] * len(p["points"]))

    def test_fanout(self):
        # R34: net arcs leaving the pin; None for pins that drive no net (inputs, the capture pin).
        src = engine("inv2", "inv2")
        nets = [a for a in src.g.by_name["FF1/Q"].fanout if a.kind == "net"]
        self.assertEqual(src.pin("FF1/Q")["fanout"], len(nets))
        self.assertEqual((src.pin("U3/A")["fanout"], src.pin("y")["fanout"]), (None, None))
        rows = model.path_table(src.paths("y")["setup"], src)[1]["rows"]
        self.assertEqual([(r["label"], r["fanout"]) for r in rows],
                         [("FF1/Q", len(nets)), ("U3/A", None), ("U3/Y", 1), ("y", None)])
        s27 = engine("s27", "s27")
        self.assertEqual((s27.pin("U14/Y")["fanout"], s27.pin("G0")["fanout"]), (2, 1))   # U8/A, U10/A

    def test_near_critical(self):
        # R33: 1 % of the clock period (was the constant 0.05).
        self.assertEqual(fmt4(model.near_critical(engine("s27", "s27").period)), "0.1000")
        # The inspector colours a margin by is_near: under 0.1 at period 10, not at it.
        self.assertEqual([model.is_near(m, 10.0) for m in (0.0999, 0.1, 0.05, 0.2)],
                         [True, False, True, False])


class TraceReplayTests(unittest.TestCase):
    """R41: the Trace tab's replay of the R36 log, without Tk."""

    def golden_sequence(self):
        """(phase, pin) per entry, read from the structure of the golden trace text: section
        header lines, then one header line per entry (candidate lines start with spaces);
        a path line names the endpoint last."""
        with open(os.path.join(ROOT, "tests", "golden", "trace", "ff2_default_FF2_D.txt")) as f:
            lines = f.read().splitlines()[2:]
        seq, phase = [], None
        for line in lines:
            if line in ("forward", "check", "backward", "slack", "path"):
                phase = line
            elif not line.startswith(" "):
                pin = line.split(" -> ")[-1].split("(")[0] if phase == "path" else line.split(" ")[0]
                seq.append((phase, pin))
        return seq

    def test_steps_follow_the_trace_text(self):
        replay = model.Replay(engine("ff2_default", "ff2").trace("FF2/D"))
        seq = [(replay.current["phase"], replay.current["pin"])]
        while not replay.at_end:
            replay.step(1)
            seq.append((replay.current["phase"], replay.current["pin"]))
        expected = self.golden_sequence()
        self.assertEqual(seq, expected)
        self.assertEqual(len(expected), 78)
        self.assertEqual(replay.label, "path · 78 of 78")

    def test_reached_values(self):
        src = engine("ff2_default", "ff2")
        replay = model.Replay(src.trace("FF2/D"))
        self.assertEqual(replay.label, "forward · 1 of 78")
        self.assertIsNone(replay.forward("U2/Y", "late", "r"))     # not reached yet
        self.assertIsNotNone(replay.forward("x", "late", "r"))
        replay.step(-5)
        self.assertEqual(replay.k, 0)                               # clamped
        while replay.current["pin"] != "U2/Y":
            replay.step(1)
        # U2/Y late r: AT 4.0 from U2/B(f) (delay 2.0); U2/A(f) lost (golden trace text).
        self.assertEqual(replay.forward("U2/Y", "late", "r"), {"at": 4.0, "slew": 0.05, "delay": 2.0})
        self.assertEqual([c["src"] for c in model.Replay.ordered(replay.current)], ["U2/B", "U2/A"])
        self.assertIsNone(replay.rat("FF2/D", "late", "r"))
        self.assertIsNone(replay.slack("FF2/D", "setup", "r"))
        path = src.paths("FF2/D")["setup"]
        sections, slack = model.trace_table(model.path_table(path, src), path, replay)
        data = dict((r["label"], r) for r in sections[1]["rows"])
        self.assertEqual((data["U2/Y"]["value"], data["U2/Y"]["incr"], data["FF2/D"]["value"]), (4.0, 2.0, None))
        self.assertEqual([r["value"] for r in sections[2]["rows"]], [None] * len(sections[2]["rows"]))
        self.assertIsNone(slack)
        replay.run_to_end()
        self.assertTrue(replay.at_end)
        self.assertEqual((replay.rat("FF2/D", "late", "r"), replay.rat("U1/A", "early", "f")), (9.7, -3.4))
        self.assertEqual(fmt4(replay.slack("FF2/D", "setup", "r")), "5.7000")
        sections, slack = model.trace_table(model.path_table(path, src), path, replay)
        full = model.path_table(path, src)
        self.assertEqual(fmt4(slack), fmt4(path["slack"]))
        for got, want in zip(sections[1]["rows"], full[1]["rows"]):     # the log gives the path's numbers
            self.assertEqual((fmt4(got["value"]), fmt4(got["rat"])), (fmt4(want["value"]), fmt4(want["rat"])))
        self.assertEqual([r["value"] for r in sections[2]["rows"]], [r["value"] for r in full[2]["rows"]])

    def test_auto_expand(self):
        src = engine("s27", "s27")
        path = src.paths("FF5/D")["setup"]
        lay, truncated = model.auto_expand(path, src)
        self.assertFalse(truncated)
        self.assertEqual([s for s in lay["stubs"] if s["state"] == "expand"], [])
        lay, truncated = model.auto_expand(path, src, limit=10)
        self.assertTrue(truncated)
        self.assertTrue(any(s["state"] == "expand" for s in lay["stubs"]))

    def test_bundle_has_no_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.json")
            with open(path, "w") as f:
                json.dump(bundle.debug_bundle(engine("ff2_default", "ff2").g, "FF2/D", depth=1), f)
            self.assertIsNone(BundleSource(path).trace("FF2/D"))


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


class SizingTests(unittest.TestCase):
    """R32: the --scale value, the default scale and the window size, without Tk."""

    def test_parse_scale(self):
        self.assertEqual([sizing.parse_scale(t) for t in ("0.6", "1", "1.25", "2.0")], [0.6, 1.0, 1.25, 2.0])
        for text in ("0.59", "2.01", "abc", "", "nan", "inf", "-1"):
            with self.assertRaises(P2Error) as cm:
                sizing.parse_scale(text)
            self.assertEqual(str(cm.exception), "error: --scale needs a number from 0.6 to 2.0")

    def test_default_scale(self):
        self.assertEqual(sizing.default_scale("aqua", 1.3318), 1.0)
        self.assertEqual(sizing.default_scale("x11", 96 / 72.0), 1.0)          # 96 dpi
        self.assertEqual(sizing.default_scale("x11", 144 / 72.0), 1.5)
        self.assertEqual((sizing.default_scale("x11", 4.0), sizing.default_scale("win32", 0.5)), (2.0, 0.6))

    def test_geometry(self):
        # The minimum is the three pane minimums and two dividers wide; header, status bar and
        # the taller centre column (summary 90 + views 160 + table 80 + two dividers) high.
        self.assertEqual(sizing.minimum(1.0), (280 + 460 + 320 + 6, 52 + 26 + 336))
        # 1280x800 at scale 1: 92 % x 90 % of the screen, centred, and above the minimum.
        self.assertEqual(sizing.geometry(1.0, 1280, 800), (1177, 720, 51, 40, 1066, 414))
        self.assertEqual(sizing.geometry(1.0, 2560, 1440)[:2], (1520, 940))
        self.assertEqual(sizing.geometry(1.0, 1440, 900)[:2], (1324, 810))
        # A large scale on a small screen opens at the minimum, at the screen's left edge.
        self.assertEqual(sizing.geometry(1.25, 1280, 800), (1333, 720, 0, 40, 1333, 517))
        self.assertEqual(sizing.minimum(0.8), (852, 331))


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

    def test_scale(self):
        # R32: out of range or not a number, checked before the design is loaded.
        for value in ("0.5", "2.1", "big"):
            self.assertError(run_viewer("--lib", LIB, "--verilog", FF2_V, "--sdc", sdc("ff2_default"), "--scale", value),
                             "error: --scale needs a number from 0.6 to 2.0")
        self.assertError(run_viewer("--bundle", "missing.json", "--scale", "3"),
                         "error: --scale needs a number from 0.6 to 2.0")

    def test_load_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w") as f:
                f.write("{not json")
            self.assertError(run_viewer("--bundle", bad), "error: %s is not JSON" % bad)
            old = os.path.join(tmp, "old.json")         # R33: written before instances existed
            b = bundle.debug_bundle(engine("ff2_default", "ff2").g, "FF2/D", depth=1)
            del b["instances"]
            with open(old, "w") as f:
                json.dump(b, f)
            self.assertError(run_viewer("--bundle", old), "error: bundle has no instances: write it again with --bundle")
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

    def texts(self, canvas):
        return [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]

    def test_engine_mode_in_every_theme(self):
        for name in theme.NAMES:
            app = self.App(self.root, engine("s27", "s27"), name)
            self.assertEqual(app.endpoint, "G17")                       # worst setup first
            app.select_endpoint("FF5/D")
            self.assertIn("1.1373", self.texts(app.summary_cv))
            self.assertIn("9.8222", self.texts(app.summary_cv))       # required in the formula
            for tab in ("schematic", "waveform"):
                app.set_tab(tab)
                self.assertTrue(app.view.find_all(), tab)
            self.assertTrue(app.root.bind("<Key-3>"))                  # R41: 3 opens the Trace tab
            app.select_endpoint("FF5/D")
            app.set_tab("trace")                                        # R41: three steps
            for _ in range(3):
                app.trace_step(1)
            self.assertEqual(app.replay.k, 3)
            current = app.replay.current
            self.assertIn(current["pin"], self.texts(app.insp))
            self.assertIn(app.replay.label, self.texts(app.tabs))
            ring = app.view.find_withtag("ring")
            self.assertEqual([app.view.gettags(i)[1] for i in ring], [current["pin"]])   # ringed
            self.assertNotIn("8.6849", self.texts(app.table))           # FF5/D's AT: not reached yet
            app.trace_end()
            self.assertIn("8.6849", self.texts(app.table))
            app.trace_step(-1)
            self.assertFalse(app.replay.at_end)
            app.set_tab("schematic")
            app.expand("U9/A")
            app.set_check("hold")
            app.set_check("setup")
            self.assertEqual(app.expansions[("FF5/D", "setup")], ["U9/A"])   # kept per check
            app.step(-1)
            self.assertEqual(app.selected, "U10/Y")              # FF5/D <- U10/Y over the net
            app.select_pin("U9/Y")
            insp = self.texts(app.insp)
            self.assertIn("U9/Y", insp)
            self.assertTrue(any("U9/A" in t for t in insp))     # the losing input of the merge
            self.assertIn("near-critical: margin < 0.1000", insp)  # R33: 1 % of the period
            app.select_cell("U9")
            self.assertTrue(any("NAND2" in t for t in self.texts(app.insp)))
            app.select_endpoint("FF7/D")                          # R34: CK slew 0, below the grid
            app.select_stage(1)
            insp = self.texts(app.insp)
            self.assertIn("extrapolated below", insp)
            self.assertIn("input_net_transition", insp)
            app.select_pin("FF7/Q")
            self.assertIn("fanout", self.texts(app.insp))
            self.assertIn("FANOUT", [t.replace(THIN, "") for t in self.texts(app.table)])
            app.filter_bin(0)
            app.filter_bin(0)
            app.set_zoom(1.5)
            app.fit()
            app.select_endpoint("G17")
            app.set_check("hold")                                        # no hold path
            self.assertIsNone(app.layout)
            self.assertTrue(app.view.find_all())
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
        app.set_tab("trace")                                    # R41: engine mode only
        self.assertEqual((app.tab, app.replay), ("schematic", None))
        app.expand("U2/A")
        self.assertTrue(any(e["name"] == "FF1" for e in app.layout["elements"]))
        self.assertEqual(app.errors, [])

    @unittest.skipUnless(all(os.path.exists(p) for p in S1423), "data/s1423.v or data/sdc/s1423.sdc not here")
    def test_s1423_in_10_seconds(self):
        """PROMPT_P5 section 6: open s1423 (about 1000 instances), the worst setup endpoint, both
        views, three left / right steps, Hold, [ and ], within 10 s of wall clock."""
        start = time.time()
        src = EngineSource([LIB], S1423[0], S1423[1])
        app = self.App(self.root, src, "light")
        self.assertEqual(app.endpoint, model.EndpointList(src.rows()).view()[0]["pin"])
        for tab in ("schematic", "waveform"):
            app.set_tab(tab)
        for delta in (-1, -1, 1):
            app.step(delta)
        app.set_check("hold")
        app.toggle_panel("left")
        app.toggle_panel("right")
        self.root.update()
        self.assertEqual(app.errors, [])
        self.assertLess(time.time() - start, 10.0)

    def test_scale(self):
        # R32: pixels times s, fonts times s on aqua (s / default elsewhere), minimum from the panes.
        app = self.App(self.root, engine("ff2_default", "ff2"), "light", 1.25)
        self.assertEqual((app.px(10), app.ipx(3)), (12.5, 4))
        aqua = self.root.tk.call("tk", "windowingsystem") == "aqua"
        if aqua:
            self.assertEqual(app.font("ui", 12).actual("size"), 15)
        self.assertEqual(self.root.wm_minsize(), sizing.minimum(1.25))
        self.assertEqual(int(app.body.panecget(app.insp, "minsize")), 400)
        self.assertEqual(app.errors, [])

    def test_no_label_overlaps(self):
        """R32: every design, endpoint, check, view and path stage, with every side input
        expanded once, at UI scales 0.8 / 1.0 / 1.25 and window widths 1100 / 1280 / 1520: no
        two texts on one canvas overlap (1 px tolerance across, 2 px down) and none is cut off
        (each lies inside its canvas, or inside the scroll region of a scrolling one)."""
        for scale in (0.8, 1.0, 1.25):
            for width in (1100, 1280, 1520):
                for scenario, netlist in DESIGNS:
                    self.check_texts(engine(scenario, netlist), scale, width, scenario)

    def check_texts(self, src, scale, width, scenario):
        app = self.App(self.root, src, "light", scale)
        self.root.geometry("%dx940" % width)
        self.root.deiconify()               # mapped, so every canvas has its real size
        self.root.update()
        self.assertEqual(self.root.winfo_width(), max(width, sizing.minimum(scale)[0]))
        canvases = (app.header, app.hist, app.list_head, app.plist, app.summary_cv, app.tabs, app.view, app.table,
                    app.insp, app.status)
        for row in app.endpoints.rows:
            for check in ("setup", "hold"):
                app.select_endpoint(row["pin"])
                app.set_check(check)
                for stub in [s["pin"] for s in app.layout["stubs"] if s["state"] == "expand"] if app.layout else []:
                    app.expand(stub)
                for tab in ("waveform", "schematic"):
                    app.set_tab(tab)
                    if tab == "waveform":
                        self.root.update_idletasks()    # pane sizes settle (the summary grows to fit)
                    for cv in canvases:
                        self.check_canvas(cv, (scenario, scale, width, row["pin"], check, tab))
                # A stage changes only the schematic, the table and the inspector (the same in
                # both views), so the stages are stepped in the schematic.
                for k in range(len(app.path()["points"])) if app.path() else []:
                    app.select_stage(k)
                    for cv in (app.view, app.table, app.insp):
                        self.check_canvas(cv, (scenario, scale, width, row["pin"], check, k))
                # R41: the Trace tab at the first entry of every phase and at the end.
                app.set_tab("trace")
                self.root.update_idletasks()
                entries = app.replay.entries
                for i in [i for i in range(len(entries)) if i == 0 or entries[i]["phase"] != entries[i - 1]["phase"]] + \
                        [len(entries) - 1]:
                    app.trace_step(i - app.replay.k)
                    for cv in canvases:
                        self.check_canvas(cv, (scenario, scale, width, row["pin"], check, "trace", i))
        if app._static_job is not None:
            self.root.after_cancel(app._static_job)
        self.assertEqual(app.errors, [])

    def check_canvas(self, cv, where):
        boxes = [(cv.itemcget(i, "text"), cv.bbox(i)) for i in cv.find_all()
                 if cv.type(i) == "text" and cv.itemcget(i, "text").strip()]
        for n, (ta, a) in enumerate(boxes):
            for tb, b in boxes[n + 1:]:
                self.assertFalse(a[0] + 1 < b[2] - 1 and b[0] + 1 < a[2] - 1 and
                                 a[1] + 2 < b[3] - 2 and b[1] + 2 < a[3] - 2, where + (ta, tb))
        region = cv.cget("scrollregion")
        if region:
            x0, y0, x1, y1 = [float(v) for v in region.split()]
        else:
            x0, y0, x1, y1 = 0, 0, cv.winfo_width(), cv.winfo_height()
        for text, (a0, b0, a1, b1) in boxes:
            self.assertTrue(x0 - 1 <= a0 and a1 <= x1 + 1 and y0 - 1 <= b0 and b1 <= y1 + 1,
                            where + (str(cv), text, (a0, b0, a1, b1), (x0, y0, x1, y1)))


if __name__ == "__main__":
    unittest.main()
