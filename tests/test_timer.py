import os
import unittest

from sta_toy import graph, liberty, sdc, timer, verilog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOY2_LIB = os.path.join(ROOT, "data", "toy2.lib")


def build(design, clock_port="clk", port_loads=None):
    lib = liberty.load(TOY2_LIB)
    netlist = verilog.load(os.path.join(ROOT, "data", design + ".v"))
    return timer.build(graph.link(netlist, lib), netlist, lib, clock_port, port_loads or {})


def arcs(node):
    return [(a.src.name, a.dst.name, a.pairs, a.tables is None) for a in node.fanin]


class GraphTests(unittest.TestCase):
    """R12: nodes, classes, net edges and timing() arcs only, check arcs on D pins."""

    @classmethod
    def setUpClass(cls):
        cls.g = build("ff2", port_loads={"y": 0.002})

    def node(self, name):
        return self.g.by_name[name]

    def test_node_classes(self):
        kinds = {n.name: n.kind for n in self.g.nodes}
        self.assertEqual(kinds, {
            "clk": "clock_port", "x": "PI", "y": "PO",
            "U1/A": "other", "U1/Y": "other", "U2/A": "other", "U2/B": "other", "U2/Y": "other",
            "FF1/CK": "CK", "FF1/D": "D", "FF1/Q": "other",
            "FF2/CK": "CK", "FF2/D": "D", "FF2/Q": "other"})
        for n in self.g.nodes:
            for values in (n.at, n.slew, n.rat, n.pred):
                self.assertEqual(sorted(values), ["early", "late"])
                self.assertEqual(sorted(values["late"]), ["f", "r"])

    def test_clock_net_not_in_graph(self):
        self.assertEqual(self.node("clk").fanout, [])
        self.assertEqual(self.node("FF1/CK").fanin, [])
        self.assertEqual(self.node("FF2/CK").fanin, [])

    def test_no_d_to_q_edge(self):
        self.assertEqual(self.node("FF1/D").fanout, [])
        self.assertEqual(arcs(self.node("FF1/Q")), [("FF1/CK", "FF1/Q", (("r", "r"), ("r", "f")), False)])

    def test_cell_and_net_arcs(self):
        self.assertEqual(arcs(self.node("U2/Y")),
                         [("U2/A", "U2/Y", (("r", "f"), ("f", "r")), False),
                          ("U2/B", "U2/Y", (("r", "f"), ("f", "r")), False)])
        self.assertEqual(arcs(self.node("U1/Y")), [("U1/A", "U1/Y", (("r", "r"), ("f", "f")), False)])
        self.assertEqual(arcs(self.node("U2/B")), [("U1/Y", "U2/B", (("r", "r"), ("f", "f")), True)])
        self.assertEqual(arcs(self.node("y")), [("FF2/Q", "y", (("r", "r"), ("f", "f")), True)])
        self.assertEqual(sorted(self.node("U2/Y").fanin[0].tables), ["f", "r"])

    def test_check_arcs(self):
        checks = self.node("FF2/D").checks
        self.assertEqual([(c.kind, c.ck.name) for c in checks], [("setup", "FF2/CK"), ("hold", "FF2/CK")])
        self.assertEqual(checks[1].tables["r"].template, "cons_3x3")

    def test_loads(self):
        # LOAD = pin capacitances of the loads + set_load of an output port on the net.
        self.assertAlmostEqual(self.node("FF2/Q").load, 0.002 + 0.002, delta=1e-12)
        self.assertAlmostEqual(self.node("U2/Y").load, 0.002, delta=1e-12)
        self.assertAlmostEqual(self.node("x").load, 0.0015, delta=1e-12)


def run(design, scenario=None, netlist_text=None, sdc_text=None):
    """Time a design: files from data/, or netlist / SDC text written by the test."""
    lib = liberty.load(TOY2_LIB)
    if netlist_text is None:
        netlist = verilog.load(os.path.join(ROOT, "data", design + ".v"))
    else:
        netlist = verilog.parse(netlist_text, design + ".v")
    if sdc_text is None:
        constraints = sdc.load(os.path.join(ROOT, "data", "sdc", (scenario or design) + ".sdc"))
    else:
        constraints = sdc.parse(sdc_text, design + ".sdc")
    return timer.run(graph.link(netlist, lib), netlist, lib, constraints).by_name


class ForwardTests(unittest.TestCase):
    """R14 + R15: sources from the clock model and the SDC, then forward propagation."""

    def assertValues(self, values, expected):
        for mode in expected:
            for rf in ("r", "f"):
                if expected[mode][rf] is None:
                    self.assertIsNone(values[mode][rf], (mode, rf))
                else:
                    self.assertAlmostEqual(values[mode][rf], expected[mode][rf], delta=1e-9, msg=(mode, rf))

    def test_two_routes_late_max_early_min(self):
        n = run("ff2", "ff2_default")
        self.assertValues(n["U2/Y"].at, {"late": {"r": 4.0, "f": 4.0}, "early": {"r": 3.0, "f": 3.0}})

    def test_pin_latency_beats_later_clock_latency(self):
        n = run("ff2", "ff2_swap")
        self.assertValues(n["FF1/CK"].at, {"late": {"r": 1.5, "f": None}, "early": {"r": 1.5, "f": None}})
        self.assertValues(n["FF2/CK"].at, {"late": {"r": 0.3, "f": None}, "early": {"r": 0.3, "f": None}})
        self.assertValues(n["FF2/CK"].slew, {"late": {"r": 0.05, "f": None}, "early": {"r": 0.05, "f": None}})
        self.assertValues(n["clk"].at, {"late": {"r": None, "f": None}, "early": {"r": None, "f": None}})

    def test_rise_fall_split(self):
        n = run("inv2")
        self.assertValues(n["U1/Y"].at, {"late": {"r": 1.2, "f": 0.8}})
        self.assertValues(n["U2/Y"].at, {"late": {"r": 2.0, "f": 2.0}})
        self.assertValues(n["y"].at, {"late": {"r": 2.55, "f": 2.55}})

    def test_unset_facets_and_worst_slew(self):
        n = run("s27")
        self.assertValues(n["G1"].at, {"late": {"r": 0.0, "f": 0.0}, "early": {"r": 0.0, "f": 0.0}})
        self.assertValues(n["G2"].slew, {"late": {"r": 0.0, "f": 0.0}, "early": {"r": 0.0, "f": 0.0}})
        self.assertValues(n["G3"].at, {"late": {"r": 2.0, "f": 2.0}, "early": {"r": 0.0, "f": 0.0}})
        # U15/Y late rise: slew from a different arc than the one that sets the AT.
        self.assertAlmostEqual(n["U15/Y"].slew["late"]["r"], 0.056, delta=1e-9)

    def test_combinational_loop(self):
        netlist = (
            "module loop (clk, a, z);\n"
            "  input clk;\n"
            "  input a;\n"
            "  output z;\n"
            "  wire n1, n2;\n"
            "  NAND2 U1 (.A(a), .B(n2), .Y(n1));\n"
            "  INV U2 (.A(n1), .Y(n2));\n"
            "  DFF FF1 (.CK(clk), .D(n1), .Q(z));\n"
            "endmodule\n")
        with self.assertRaises(timer.P2Error) as cm:
            run("loop", netlist_text=netlist,
                sdc_text="create_clock -name clk -period 10 [get_ports clk]\n")
        self.assertIsNone(cm.exception.file)
        self.assertTrue(str(cm.exception).startswith("error: combinational loop: "))
        for pin in ("U1/Y", "U2/A", "U2/Y", "U1/B"):
            self.assertIn(pin, cm.exception.message)


if __name__ == "__main__":
    unittest.main()
