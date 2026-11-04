import json
import os
import shutil
import tempfile
import unittest

from sta_toy import P2Error, jsonout
from sta_toy.tsv import fmt4
from test_paths import DESIGNS, ROOT, golden_rows, timed


def build(scenario, netlist):
    g = timed(scenario, netlist)
    info = {"name": g.netlist.name, "libs": ["data/toy2.lib"], "verilog": "data/%s.v" % netlist,
            "sdc": "data/sdc/%s.sdc" % scenario, "units": jsonout.units(g.lib)}
    return info, jsonout.report_json(g, info)


def golden_paths(scenario):
    """[((endpoint, check), slack, chain)] from the golden paths.txt, in file order."""
    with open(os.path.join(ROOT, "tests", "golden", scenario, "paths.txt")) as f:
        lines = f.read().splitlines()
    return [(tuple(l.split()[:2]), l.split()[2], l.split(" : ")[1]) for l in lines]


def golden_num(cell):
    return None if cell == "NA" else float(cell)


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


class SchemaTests(unittest.TestCase):
    """R25: top level, design and clocks of json_v1.md."""

    def test_top_level(self):
        info, obj = build("ff2_default", "ff2")
        self.assertEqual(list(obj), ["schema", "design", "clocks", "summary", "endpoints", "paths"])
        self.assertEqual(obj["schema"], "sta_toy.report/1")
        self.assertEqual(obj["design"], info)
        self.assertEqual(obj["design"]["name"], "ff2")
        self.assertEqual(obj["design"]["units"], {"time": "1ns", "cap": "1pf"})

    def test_clocks_s27(self):
        clocks = build("s27", "s27")[1]["clocks"]
        self.assertEqual(clocks, [{"name": "clk", "period": 10.0, "port": "clk", "latency": 0.2,
                                   "pin_latency": {}, "transition": 0.0,
                                   "uncertainty": {"setup": 0.1, "hold": 0.05}}])
        self.assertEqual(list(clocks[0]), ["name", "period", "port", "latency", "pin_latency",
                                           "transition", "uncertainty"])

    def test_clocks_pin_latency(self):
        clock = build("ff2_swap", "ff2")[1]["clocks"][0]
        self.assertEqual(clock["pin_latency"], {"FF1/CK": 1.5})
        self.assertEqual((clock["latency"], clock["transition"]), (0.3, 0.05))
        self.assertEqual(clock["uncertainty"], {"setup": 0.0, "hold": 0.0})


class GoldenTests(unittest.TestCase):
    """R25: summary, endpoints and paths against the golden files of every design."""

    def test_summary(self):
        for scenario, netlist in DESIGNS:
            summary = build(scenario, netlist)[1]["summary"]
            rows = golden_rows(scenario, "endpoints.tsv")
            self.assertEqual(list(summary), ["setup", "hold"])
            for check in ("setup", "hold"):
                slacks = [float(r[check + "_slack"]) for r in rows if r[check + "_slack"] != "NA"]
                self.assertEqual(summary[check],
                                 {"wns": float(fmt4(min(slacks))),
                                  "tns": float(fmt4(sum(min(s, 0.0) for s in slacks))),
                                  "nvp": sum(1 for s in slacks if s < 0)}, (scenario, check))

    def test_endpoints(self):
        for scenario, netlist in DESIGNS:
            endpoints = build(scenario, netlist)[1]["endpoints"]
            rows = golden_rows(scenario, "endpoints.tsv")
            rfs = {key: chain.split("(")[-1][0] for key, _, chain in golden_paths(scenario)}
            self.assertEqual([e["pin"] for e in endpoints], [r["pin"] for r in rows], scenario)
            for e, row in zip(endpoints, rows):
                self.assertEqual(list(e), ["pin", "kind", "clock", "setup", "hold", "worst_path"])
                self.assertEqual(e["kind"], "D" if "/" in e["pin"] else "PO")
                self.assertEqual(e["clock"], "clk")
                for check in ("setup", "hold"):
                    self.assertEqual(e[check], {"rf": rfs.get((e["pin"], check)),
                                                "at": golden_num(row[check + "_at"]),
                                                "rat": golden_num(row[check + "_rat"]),
                                                "slack": golden_num(row[check + "_slack"])},
                                     (scenario, e["pin"], check))

    def test_paths_and_ids(self):
        for scenario, netlist in DESIGNS:
            obj = build(scenario, netlist)[1]
            expected = golden_paths(scenario)
            self.assertEqual([p["id"] for p in obj["paths"]],
                             ["p%d" % i for i in range(1, len(expected) + 1)], scenario)
            for p, ((end, check), slack, chain) in zip(obj["paths"], expected):
                self.assertEqual((p["end"], p["check"], p["slack"]), (end, check, float(slack)))
                self.assertEqual(" -> ".join("%s(%s)" % (q["pin"], q["rf"]) for q in p["points"]),
                                 chain, (scenario, end, check))
            by_id = {p["id"]: p for p in obj["paths"]}
            for e in obj["endpoints"]:
                for check in ("setup", "hold"):
                    pid = e["worst_path"][check]
                    if e[check]["slack"] is None:
                        self.assertIsNone(pid)
                    else:
                        self.assertEqual((by_id[pid]["end"], by_id[pid]["check"]), (e["pin"], check))

    def test_s27_g17_hold_is_null(self):
        g17 = [e for e in build("s27", "s27")[1]["endpoints"] if e["pin"] == "G17"][0]
        self.assertEqual(g17["hold"], {"rf": None, "at": None, "rat": None, "slack": None})
        self.assertEqual(g17["worst_path"], {"setup": "p7", "hold": None})

    def test_numbers_are_fmt4_rounded(self):
        for scenario, netlist in DESIGNS:
            obj = build(scenario, netlist)[1]
            for x in floats(obj):
                self.assertEqual(x, float(fmt4(x)), scenario)
            self.assertNotIn("0000000", jsonout.dumps(obj), scenario)
        # ff2_swap FF2/D setup: t_su = (0.3 + 10.0 - 0.0) - 10.0, 0.3000000000000007 unrounded.
        p = [p for p in build("ff2_swap", "ff2")[1]["paths"]
             if (p["end"], p["check"]) == ("FF2/D", "setup")][0]
        self.assertEqual(p["capture"]["check"], 0.3)
        self.assertEqual(p["capture"]["latency"], 0.3)


class OutputTests(unittest.TestCase):
    """R25: dumps format and write errors."""

    def test_dumps(self):
        self.assertEqual(jsonout.dumps({"b": [1.0, None], "a": "x"}),
                         '{\n  "b": [\n    1.0,\n    null\n  ],\n  "a": "x"\n}\n')
        obj = build("inv2", "inv2")[1]
        self.assertEqual(json.loads(jsonout.dumps(obj)), obj)

    def test_write(self):
        tmp = tempfile.mkdtemp()
        try:
            obj = build("inv2", "inv2")[1]
            path = os.path.join(tmp, "r.json")
            jsonout.write(obj, path)
            with open(path, encoding="utf-8", newline="") as f:
                self.assertEqual(f.read(), jsonout.dumps(obj))
            bad = os.path.join(tmp, "missing", "r.json")
            with self.assertRaises(P2Error) as cm:
                jsonout.write(obj, bad)
            self.assertEqual(str(cm.exception), "error: cannot write %s: No such file or directory" % bad)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
