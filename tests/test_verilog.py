import os
import unittest

from sta_toy import verilog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C17 = os.path.join(ROOT, "data", "c17.v")


class VerilogTests(unittest.TestCase):

    def test_c17(self):
        net = verilog.load(C17)
        self.assertEqual(net.name, "c17")
        self.assertEqual(net.ports, ["N1", "N2", "N3", "N6", "N7", "N22", "N23"])
        self.assertEqual(net.inputs, ["N1", "N2", "N3", "N6", "N7"])
        self.assertEqual(net.outputs, ["N22", "N23"])
        self.assertEqual(net.wires, ["N10", "N11", "N16", "N19"])
        self.assertEqual([(i.cell, i.name) for i in net.instances],
                         [("ND2D1", "U%d" % n) for n in range(1, 7)])
        u6 = net.instances[5]
        self.assertEqual(u6.line, 13)
        self.assertEqual([(c.pin, c.net, c.line) for c in u6.conns],
                         [("A1", "N16", 13), ("A2", "N19", 13), ("ZN", "N23", 14)])

    def test_positional_connection_error(self):
        text = (
            "module m ( a, z );\n"     # 1
            "  input a;\n"             # 2
            "  output z;\n"            # 3
            "  X U1 ( a, z );\n"       # 4
            "endmodule\n"
        )
        with self.assertRaises(verilog.StaError) as cm:
            verilog.parse(text, "p.v")
        self.assertEqual((cm.exception.file, cm.exception.line), ("p.v", 4))
        self.assertIn("p.v:4:", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
