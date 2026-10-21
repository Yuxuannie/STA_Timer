import os
import subprocess
import sys
import tempfile
import unittest

from sta_toy import graph, liberty, verilog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "tests", "golden", "c17_graph.txt")

# Cell X: inputs A, B, C and output Z. Two A->Z groups merge; "B C" splits.
MERGE_LIB = """library (m) {
  capacitive_load_unit (1, pf);
  cell (X) {
    pin (A) { direction : input; capacitance : 0.001; }
    pin (B) { direction : input; capacitance : 0.002; }
    pin (C) { direction : input; capacitance : 0.003; }
    pin (Z) {
      direction : output;
      timing () { related_pin : "A"; when : "B"; timing_sense : positive_unate; }
      timing () { related_pin : "A"; when : "!B"; timing_sense : negative_unate; }
      timing () { related_pin : "B C"; timing_sense : positive_unate; }
    }
  }
}
"""

UNKNOWN_CELL_V = (
    "module m ( a, z );\n"                  # 1
    "  input a;\n"                          # 2
    "  output z;\n"                         # 3
    "  NOPE U1 ( .A(a), .Z(z) );\n"         # 4
    "endmodule\n"
)


def run_cli(lib, v):
    return subprocess.run(
        [sys.executable, "-m", "sta_toy", "--lib", lib, "--verilog", v],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class GraphStructureTests(unittest.TestCase):
    """R4: the graph data structure on its own."""

    def test_graph_structure(self):
        g = graph.Graph("d", "l", (1.0, "pf"))
        g.add_node("a", "PI")
        g.add_node("U1/A", "input", cell="X", cap=0.001)
        g.add_node("U1/Z", "output", cell="X")
        g.add_node("z", "PO")
        g.add_net_edge("a", "U1/A")
        g.add_cell_edge("U1/A", "U1/Z", "positive_unate")
        g.add_cell_edge("U1/A", "U1/Z", "negative_unate")
        g.add_cell_edge("U1/A", "U1/Z", "positive_unate")
        g.add_net_edge("U1/Z", "z")
        self.assertEqual([n.name for n in g.nodes], ["a", "U1/A", "U1/Z", "z"])
        self.assertEqual([(e.kind, e.dst) for e in g.node("a").edges], [("net", "U1/A")])
        self.assertEqual([(e.kind, e.dst, e.senses) for e in g.node("U1/A").edges],
                         [("cell", "U1/Z", ["positive_unate", "negative_unate"])])
        self.assertEqual(g.node("U1/A").cap, 0.001)


class LinkTests(unittest.TestCase):
    """R5: netlist + library -> graph."""

    def setUp(self):
        self.lib = liberty.loads(MERGE_LIB, "m.lib")

    def link(self, text):
        return graph.link(verilog.parse(text, "x.v"), self.lib)

    def test_merge_and_split(self):
        g = self.link(
            "module m ( a, b, c, z );\n"
            "  input a, b, c;\n"
            "  output z;\n"
            "  X U1 ( .A(a), .B(b), .C(c), .Z(z) );\n"
            "endmodule\n")
        cell_edges = [(n.name, e.dst, ",".join(e.senses))
                      for n in g.nodes for e in n.edges if e.kind == "cell"]
        self.assertEqual(cell_edges, [("U1/A", "U1/Z", "positive_unate,negative_unate"),
                                      ("U1/B", "U1/Z", "positive_unate"),
                                      ("U1/C", "U1/Z", "positive_unate")])

    def assertLinkError(self, text, line, name):
        with self.assertRaises(graph.StaError) as cm:
            self.link(text)
        self.assertEqual((cm.exception.file, cm.exception.line), ("x.v", line))
        self.assertIn(name, cm.exception.message)

    def test_unknown_cell(self):
        self.assertLinkError(UNKNOWN_CELL_V, 4, "NOPE")

    def test_unknown_pin(self):
        self.assertLinkError(
            "module m ( a, z );\n"                      # 1
            "  input a;\n"                              # 2
            "  output z;\n"                             # 3
            "  X U1 ( .A(a), .B(a), .C(a),\n"           # 4
            "         .QQ(z) );\n"                      # 5
            "endmodule\n", 5, "QQ")

    def test_net_without_driver(self):
        self.assertLinkError(
            "module m ( a, z );\n"                      # 1
            "  input a;\n"                              # 2
            "  output z;\n"                             # 3
            "  wire nodrv;\n"                           # 4
            "  X U1 ( .A(a), .B(nodrv), .C(a), .Z(z) );\n"
            "endmodule\n", 4, "nodrv")

    def test_net_with_two_drivers(self):
        self.assertLinkError(
            "module m ( a, zz );\n"                     # 1
            "  input a;\n"                              # 2
            "  output zz;\n"                            # 3
            "  X U1 ( .A(a), .B(a), .C(a), .Z(zz) );\n"
            "  X U2 ( .A(a), .B(a), .C(a), .Z(zz) );\n"
            "endmodule\n", 3, "zz")


class CliTests(unittest.TestCase):
    """R6: writer and CLI."""

    def test_golden(self):
        result = run_cli("data/toy.lib", "data/c17.v")
        with open(GOLDEN, "rb") as f:
            golden = f.read()
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, golden)

    def test_unknown_cell_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.v")
            with open(path, "w") as f:
                f.write(UNKNOWN_CELL_V)
            result = run_cli("data/toy.lib", path)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        stderr = result.stderr.decode()
        self.assertTrue(stderr.startswith("ERROR %s:4:" % path), stderr)
        self.assertIn("NOPE", stderr)
        self.assertEqual(stderr.count("\n"), 1)
        self.assertTrue(stderr.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
