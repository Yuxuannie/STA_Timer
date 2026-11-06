import json
import os
import unittest

from sta_toy import P2Error, bundle, design, paths
from sta_toy.tsv import fmt4

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def timed(scenario, netlist):
    lib, nl, linked = design.load([os.path.join(ROOT, "data", "toy2.lib")],
                                  os.path.join(ROOT, "data", netlist + ".v"))
    return design.timed(lib, nl, linked, os.path.join(ROOT, "data", "sdc", scenario + ".sdc"))


def golden_pins(scenario):
    with open(os.path.join(ROOT, "tests", "golden", scenario, "pins.tsv")) as f:
        lines = f.read().splitlines()
    header = lines[0].split("\t")
    return {r["pin"]: r for r in (dict(zip(header, line.split("\t"))) for line in lines[1:])}


def floats(obj):
    if isinstance(obj, float):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            for x in floats(v):
                yield x
    elif isinstance(obj, list):
        for v in obj:
            for x in floats(v):
                yield x


# ff2, backwards from FF2/D: net U2/Y (0); cell U2/A, U2/B (1); nets FF1/Q, U1/Y (1);
# ckq FF1/CK and cell U1/A (2); net x (2). FF2/CK is the capture pin (0). The endpoint
# comes first, then (depth, name).
FF2D_DEPTH = [("FF2/D", 0), ("FF2/CK", 0), ("U2/Y", 0),
              ("FF1/Q", 1), ("U1/Y", 1), ("U2/A", 1), ("U2/B", 1),
              ("FF1/CK", 2), ("U1/A", 2), ("x", 2)]


class ConeTests(unittest.TestCase):
    """R27: the cone, its order, truncation and the edges between kept nodes."""

    @classmethod
    def setUpClass(cls):
        cls.g = timed("ff2_default", "ff2")

    def test_depths(self):
        for k in (0, 1, 2, 3):
            b = bundle.debug_bundle(self.g, "FF2/D", depth=k)
            self.assertEqual([(n["pin"], n["depth"]) for n in b["nodes"]],
                             [t for t in FF2D_DEPTH if t[1] <= k], k)
            self.assertFalse(b["truncated"])
            self.assertEqual((b["schema"], b["endpoint"], b["depth"], b["max_nodes"], b["clock"]),
                             ("sta_toy.bundle/1", "FF2/D", k, 300, {"name": "clk", "period": 10.0}))

    def test_edges(self):
        b = bundle.debug_bundle(self.g, "FF2/D")
        self.assertEqual([(x["u"], x["v"], x["kind"]) for x in b["edges"]],
                         [("FF1/CK", "FF1/Q", "ckq"),
                          ("FF2/CK", "FF2/D", "check"),
                          ("U2/Y", "FF2/D", "net"),
                          ("x", "U1/A", "net"), ("U1/A", "U1/Y", "cell"),
                          ("FF1/Q", "U2/A", "net"), ("U1/Y", "U2/B", "net"),
                          ("U2/A", "U2/Y", "cell"), ("U2/B", "U2/Y", "cell")])

    def test_truncation(self):
        b = bundle.debug_bundle(self.g, "FF2/D", max_nodes=5)
        self.assertTrue(b["truncated"])
        self.assertEqual([n["pin"] for n in b["nodes"]], ["FF2/D", "FF2/CK", "U2/Y", "FF1/Q", "U1/Y"])
        self.assertEqual([(x["u"], x["v"], x["kind"]) for x in b["edges"]],
                         [("FF2/CK", "FF2/D", "check"), ("U2/Y", "FF2/D", "net")])
        # The endpoint is kept even when only one node fits ('FF2/CK' < 'FF2/D').
        b = bundle.debug_bundle(self.g, "FF2/D", max_nodes=1)
        self.assertEqual(([n["pin"] for n in b["nodes"]], b["edges"], b["truncated"]),
                         (["FF2/D"], [], True))
        b = bundle.debug_bundle(self.g, "FF2/D", depth=2, max_nodes=10)
        self.assertFalse(b["truncated"])

    def test_po_endpoint(self):
        # inv2, backwards from y: net U3/Y (0); cell U3/A (1); net FF1/Q (1); ckq FF1/CK (2).
        g = timed("inv2", "inv2")
        b = bundle.debug_bundle(g, "y", depth=1)
        self.assertEqual([(n["pin"], n["depth"]) for n in b["nodes"]],
                         [("y", 0), ("U3/Y", 0), ("FF1/Q", 1), ("U3/A", 1)])
        b = bundle.debug_bundle(g, "y")
        self.assertEqual([(n["pin"], n["depth"]) for n in b["nodes"]],
                         [("y", 0), ("U3/Y", 0), ("FF1/Q", 1), ("U3/A", 1), ("FF1/CK", 2)])
        self.assertEqual([x["kind"] for x in b["edges"]], ["ckq", "net", "cell", "net"])
        self.assertEqual([p["id"] for p in b["paths"]], ["setup", "hold"])

    def test_not_an_endpoint(self):
        for name in ("U2/Y", "nope"):
            with self.assertRaises(P2Error) as cm:
                bundle.debug_bundle(self.g, name)
            self.assertEqual(str(cm.exception), "error: --bundle %s is not an endpoint" % name)


class ValueTests(unittest.TestCase):
    """R27: node values against the P2 golden, edge delays, check values, paths, JSON."""

    @classmethod
    def setUpClass(cls):
        cls.g = timed("ff2_default", "ff2")
        cls.b = bundle.debug_bundle(cls.g, "FF2/D")

    def edge(self, u, v):
        return [x for x in self.b["edges"] if (x["u"], x["v"]) == (u, v)]

    def test_nodes_against_golden(self):
        rows = golden_pins("ff2_default")
        for n in self.b["nodes"]:
            row = rows[n["pin"]]
            for kind in ("at", "rat", "slew"):
                for m in ("late", "early"):
                    for rf in ("r", "f"):
                        self.assertEqual(fmt4(n[kind][m][rf]), row["%s_%s_%s" % (kind, m, rf)])

            def golden_slack(a, b):
                s = [float(row[a + rf]) - float(row[b + rf]) for rf in ("r", "f")
                     if row[a + rf] != "NA" and row[b + rf] != "NA"]
                return fmt4(min(s)) if s else "NA"
            self.assertEqual(fmt4(n["slack"]["setup"]), golden_slack("rat_late_", "at_late_"), n["pin"])
            self.assertEqual(fmt4(n["slack"]["hold"]), golden_slack("at_early_", "rat_early_"), n["pin"])

    def test_node_fields(self):
        nodes = {n["pin"]: n for n in self.b["nodes"]}
        self.assertEqual((nodes["FF2/D"]["kind"], nodes["FF2/D"]["cell"], nodes["FF2/D"]["cap"]),
                         ("D", "DFF", None))
        self.assertEqual((nodes["x"]["kind"], nodes["x"]["cell"], nodes["x"]["cap"]), ("PI", None, 0.0015))
        self.assertEqual(nodes["U2/Y"]["cap"], 0.002)
        # P5 / R34: fanout counts the pin's net arcs; null where the pin drives no net.
        self.assertEqual((nodes["U2/Y"]["fanout"], nodes["x"]["fanout"], nodes["FF2/D"]["fanout"]), (1, 1, None))
        # The clock port is never in a cone (its net is not in the graph); as a node it would be null.
        self.assertEqual(bundle._node(self.g.by_name["clk"], 0)["fanout"], None)
        # golden FF2/CK: setup 7.0 - 0.0, hold 0.0 - (-0.9); no falling values.
        self.assertEqual(nodes["FF2/CK"]["slack"], {"setup": 7.0, "hold": 0.9})

    def test_check_edges(self):
        # DFF setup = 0.25 + 0.5*0.05 + 0.5*0.05 = 0.3, hold = -0.05 + 0.05 + 2*0.05 = 0.1.
        # One check edge per capture CK pin, carrying both the setup and the hold values.
        (check,) = self.edge("FF2/CK", "FF2/D")
        self.assertEqual(check["check"], {"setup": {"r": 0.3, "f": 0.3}, "hold": {"r": 0.1, "f": 0.1}})
        self.assertIsNone(check["delay"])

    def test_edge_delays(self):
        # NAND2 delay = 1.8 + 2.0*0.05 + 50*0.002 = 2.0 (negative unate: only rf / fr).
        (e,) = self.edge("U2/A", "U2/Y")
        for m in ("late", "early"):
            self.assertEqual(e["delay"][m], {"rr": None, "rf": 2.0, "fr": 2.0, "ff": None})
        self.assertIsNone(e["check"])
        # BUF delay = 1.3 + 2.0*0.05 + 50*0.002 = 1.5.
        (e,) = self.edge("U1/A", "U1/Y")
        self.assertEqual(e["delay"]["late"], {"rr": 1.5, "rf": None, "fr": None, "ff": 1.5})
        # CK -> Q is 1.0 for rr / rf; the CK pin has no falling slew.
        (e,) = self.edge("FF1/CK", "FF1/Q")
        self.assertEqual(e["delay"]["early"], {"rr": 1.0, "rf": 1.0, "fr": None, "ff": None})
        (e,) = self.edge("U2/Y", "FF2/D")
        self.assertEqual(e["delay"]["late"], {"rr": 0.0, "rf": None, "fr": None, "ff": 0.0})

    def test_paths(self):
        expected = [paths.path_json(paths.worst_path(self.g.by_name["FF2/D"], c), self.g.sdc, c)
                    for c in ("setup", "hold")]
        self.assertEqual(self.b["paths"], expected)
        self.assertEqual([(p["start"], p["slack"]) for p in self.b["paths"]], [("x", 5.7), ("FF1/CK", 2.9)])

    def test_instances(self):
        # Every instance in the cone or on a path, with its library pins in library order.
        b = bundle.debug_bundle(timed("s27", "s27"), "FF5/D", depth=1)
        self.assertEqual(sorted(b["instances"]), ["FF5", "U10", "U11", "U14", "U15", "U8", "U9"])
        self.assertEqual(b["instances"]["FF5"], {"cell": "DFF", "sequential": True, "pins": [
            {"name": "CK", "direction": "input", "clock": True, "function": None},
            {"name": "D", "direction": "input", "clock": False, "function": None},
            {"name": "Q", "direction": "output", "clock": False, "function": "IQ"}]})
        self.assertEqual(b["instances"]["U9"]["pins"][2]["function"], "!(A&B)")
        self.assertEqual([p["name"] for p in b["instances"]["U9"]["pins"]], ["A", "B", "Y"])

    def test_json(self):
        for b in (self.b, bundle.debug_bundle(timed("s27", "s27"), "FF5/D")):
            self.assertEqual(json.loads(json.dumps(b)), b)
            for v in floats(b):
                self.assertEqual(v, float(fmt4(v)))


if __name__ == "__main__":
    unittest.main()
