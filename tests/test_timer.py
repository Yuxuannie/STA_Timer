import os
import unittest

from sta_toy import graph, liberty, timer, verilog

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


if __name__ == "__main__":
    unittest.main()
