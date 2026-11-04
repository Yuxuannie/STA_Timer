import os
import unittest

from sta_toy import design, paths
from sta_toy.tsv import fmt4

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGNS = [("ff2_default", "ff2"), ("ff2_swap", "ff2"), ("ff2_setupviol", "ff2"),
           ("ff2_holdviol", "ff2"), ("ff2_skew", "ff2"), ("ff2_unc", "ff2"),
           ("inv2", "inv2"), ("s27", "s27")]


def timed(scenario, netlist):
    lib, nl, linked = design.load([os.path.join(ROOT, "data", "toy2.lib")],
                                  os.path.join(ROOT, "data", netlist + ".v"))
    return design.timed(lib, nl, linked, os.path.join(ROOT, "data", "sdc", scenario + ".sdc"))


def golden_rows(scenario, name):
    with open(os.path.join(ROOT, "tests", "golden", scenario, name)) as f:
        lines = f.read().splitlines()
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"))) for line in lines[1:]]


class WorstPathTests(unittest.TestCase):
    """R21 + R22: the PRED path, the enumeration and the golden paths.txt agree."""

    def test_against_golden_paths(self):
        for scenario, netlist in DESIGNS:
            g = timed(scenario, netlist)
            with open(os.path.join(ROOT, "tests", "golden", scenario, "paths.txt")) as f:
                golden = f.read().splitlines()
            lines = []
            for e in sorted(g.endpoints, key=lambda n: n.name):
                for check in ("setup", "hold"):
                    worst = paths.worst_path(e, check)
                    found = paths.enumerate_paths(e, check, 3)
                    if worst is None:
                        self.assertEqual(found, [])
                        continue
                    lines.append("%s %s %s : %s" % (e.name, check, fmt4(worst.slack), worst.text()))
                    self.assertEqual(found[0].text(), worst.text(), (scenario, e.name, check))
                    slacks = [round(p.slack, 9) for p in found]
                    self.assertEqual(slacks, sorted(slacks))
            self.assertEqual(lines, golden, scenario)

    def test_points(self):
        p = paths.worst_path(timed("ff2_default", "ff2").by_name["FF2/D"], "setup")
        self.assertEqual([(q.node.name, q.rf, q.arc) for q in p.points],
                         [("x", "f", "start"), ("U1/A", "f", "net"), ("U1/Y", "f", "cell"),
                          ("U2/B", "f", "net"), ("U2/Y", "r", "cell"), ("FF2/D", "r", "net")])
        self.assertEqual([fmt4(q.incr) for q in p.points],
                         ["0.0000", "0.0000", "1.5000", "0.0000", "2.0000", "0.0000"])
        self.assertEqual([fmt4(q.at) for q in p.points],
                         ["0.5000", "0.5000", "2.0000", "2.0000", "4.0000", "4.0000"])
        self.assertEqual((fmt4(p.arrival), fmt4(p.required), fmt4(p.slack)), ("4.0000", "9.7000", "5.7000"))


class EnumerationTests(unittest.TestCase):
    """R22: K worst paths, endpoint selection and the from / to / through filters."""

    @classmethod
    def setUpClass(cls):
        cls.g = timed("s27", "s27")

    def test_second_worst_path(self):
        # Through U16 instead of U15: U9/A sees slew 0.054 instead of 0.056 -> 2.0 * 0.002 later.
        first, second = paths.enumerate_paths(self.g.by_name["FF5/D"], "setup", 2)
        self.assertEqual(fmt4(first.slack), "1.1373")
        self.assertEqual(fmt4(second.slack), "1.1413")
        self.assertIn("U16/Y(r)", second.text())

    def test_select(self):
        found = paths.select(self.g, "setup", max_paths=2, nworst=1)
        self.assertEqual([p.endpoint.name for p in found], ["G17", "FF5/D"])
        found = paths.select(self.g, "setup", through="U16/Y")
        self.assertEqual((found[0].endpoint.name, fmt4(found[0].slack)), ("G17", "0.3746"))
        found = paths.select(self.g, "hold", to="FF7/D", frm="FF7/CK")
        self.assertEqual(found[0].start.name, "FF7/CK")
        self.assertEqual(paths.select(self.g, "hold", to="G17"), [])

    def test_select_errors(self):
        for kwargs, text in (({"frm": "U9/Y"}, "--from U9/Y is not a startpoint"),
                             ({"to": "U9/Y"}, "--to U9/Y is not an endpoint"),
                             ({"through": "nope"}, "--through nope is not a node")):
            with self.assertRaises(paths.P2Error) as cm:
                paths.select(self.g, "setup", **kwargs)
            self.assertEqual(cm.exception.message, text)


class SummaryTests(unittest.TestCase):
    """R24: wns / tns / nvp from the golden endpoint slacks."""

    def test_against_golden_endpoints(self):
        for scenario, netlist in DESIGNS:
            got = paths.summary(timed(scenario, netlist))
            rows = golden_rows(scenario, "endpoints.tsv")
            for check in ("setup", "hold"):
                slacks = [float(r[check + "_slack"]) for r in rows if r[check + "_slack"] != "NA"]
                self.assertEqual(fmt4(got[check]["wns"]), fmt4(min(slacks)), (scenario, check))
                self.assertEqual(fmt4(got[check]["tns"]), fmt4(sum(min(s, 0.0) for s in slacks)))
                self.assertEqual(got[check]["nvp"], sum(1 for s in slacks if s < 0))


class PathObjectTests(unittest.TestCase):
    """R21: the json_v1.md path object."""

    def test_flop_capture(self):
        g = timed("ff2_default", "ff2")
        p = paths.path_json(paths.worst_path(g.by_name["FF2/D"], "setup"), g.sdc, "p1")
        self.assertEqual(p["capture"], {"clock_edge": 10.0, "latency": 0.0, "uncertainty": 0.0,
                                        "check": 0.3, "output_delay": None, "rat": 9.7,
                                        "pin": "FF2/CK", "cell": "DFF"})
        self.assertEqual(p["launch"], {"clock_edge": 0.0, "latency": None, "input_delay": 0.5})
        self.assertEqual((p["type"], p["start"], p["end"], p["slack"]), ("max", "x", "FF2/D", 5.7))

    def test_port_capture_and_caps(self):
        g = timed("inv2", "inv2")
        p = paths.path_json(paths.worst_path(g.by_name["y"], "hold"), g.sdc, "p2")
        self.assertEqual(p["capture"]["output_delay"], 1.0)
        self.assertEqual(p["capture"]["rat"], -1.0)
        self.assertIsNone(p["capture"]["check"])
        caps = {q["pin"]: q["cap"] for q in p["points"]}
        self.assertEqual(caps, {"FF1/CK": None, "FF1/Q": 0.0015, "U3/A": None, "U3/Y": 0.003, "y": None})


if __name__ == "__main__":
    unittest.main()
