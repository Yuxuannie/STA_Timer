import os
import unittest

from sta_toy import liberty

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOY_LIB = os.path.join(ROOT, "data", "toy.lib")


def find_group(group, header, name):
    for g in group.find_groups(header):
        if g.names == [name]:
            return g
    raise AssertionError("no %s (%s)" % (header, name))


class TreeTests(unittest.TestCase):
    """R1: the generic tree."""

    @classmethod
    def setUpClass(cls):
        cls.root = liberty.parse_file(TOY_LIB)

    def test_define_kept_twice(self):
        self.assertEqual(len(self.root.find_attrs("define")), 2)

    def test_leakage_power_groups_kept(self):
        cell = find_group(self.root, "cell", "ND2D1")
        self.assertGreaterEqual(len(cell.find_groups("leakage_power")), 2)

    def test_tree_keeps_ocv_sigma(self):
        zn = find_group(find_group(self.root, "cell", "ND2D1"), "pin", "ZN")
        timing = zn.find_groups("timing")[0]
        self.assertEqual(len(timing.find_groups("ocv_sigma_cell_rise")), 1)

    def test_grammar_constructs(self):
        text = (
            '/* multi-line\n'                         # 1
            '   comment */ library ("q lib") {\n'     # 2
            '  define (a, cell, string);\n'           # 3
            '  define (b, cell, string);\n'           # 4
            '  num : 1.25e-03;\n'                     # 5
            '  str : "x, y" ;\n'                      # 6
            '  pair (k1, k2) { }\n'                   # 7
            '  timing () {\n'                         # 8
            '    values ("1, 2", \\\n'                # 9
            '            "3, 4");\n'                  # 10
            '    cont : "a, \\\n'                     # 11
            'b";\n'                                   # 12
            '  }\n'                                   # 13
            '  timing () { unknown_thing : 7; }\n'    # 14
            '}\n'                                     # 15
        )
        root = liberty.parse(text, "g.lib")
        self.assertEqual((root.header, root.names, root.line), ("library", ["q lib"], 2))
        self.assertEqual([a.values for a in root.find_attrs("define")],
                         [["a", "cell", "string"], ["b", "cell", "string"]])
        self.assertEqual(float(root.find_attrs("num")[0].values[0]), 1.25e-03)
        self.assertEqual(root.find_attrs("str")[0].values, ["x, y"])
        self.assertEqual(root.find_groups("pair")[0].names, ["k1", "k2"])
        timings = root.find_groups("timing")
        self.assertEqual([(t.names, t.line) for t in timings], [([], 8), ([], 14)])
        values = timings[0].find_attrs("values")[0]
        self.assertEqual((values.values, values.line), (["1, 2", "3, 4"], 9))
        cont = timings[0].find_attrs("cont")[0]
        self.assertEqual((cont.values, cont.line), (["a, b"], 11))
        self.assertEqual(timings[1].find_attrs("unknown_thing")[0].values, ["7"])

    def test_unclosed_group_reports_header_line(self):
        text = (
            "library (u) {\n"          # 1
            "  cell (C) {\n"           # 2
            "    pin (A) {\n"          # 3
            "      direction : input;\n"
        )
        with self.assertRaises(liberty.StaError) as cm:
            liberty.parse(text, "u.lib")
        self.assertEqual((cm.exception.file, cm.exception.line), ("u.lib", 3))
        self.assertIn("pin (A)", cm.exception.message)


class AccessorTests(unittest.TestCase):
    """R2: the accessors over the tree."""

    @classmethod
    def setUpClass(cls):
        cls.lib = liberty.load(TOY_LIB)

    def test_name_and_cap_unit(self):
        self.assertEqual(self.lib.name, "toy_lib")
        self.assertEqual(self.lib.cap_unit, (1.0, "pf"))

    def test_cell_count(self):
        self.assertEqual(len(self.lib.cells), 2)

    def test_nd2d1_signal_pins(self):
        cell = self.lib.cells["ND2D1"]
        self.assertEqual([p.name for p in cell.pins], ["A1", "A2", "ZN"])

    def test_input_capacitances(self):
        cell = self.lib.cells["ND2D1"]
        a1, a2 = cell.pin("A1"), cell.pin("A2")
        self.assertEqual((a1.direction, a1.capacitance, a1.rise_capacitance, a1.fall_capacitance),
                         ("input", 0.00071, 0.00070, 0.00072))
        self.assertEqual((a2.direction, a2.capacitance, a2.rise_capacitance, a2.fall_capacitance),
                         ("input", 0.00064, 0.00063, 0.00065))

    def test_zn_timing_groups(self):
        zn = self.lib.cells["ND2D1"].pin("ZN")
        self.assertEqual(zn.direction, "output")
        self.assertEqual([(t.related_pins, t.timing_sense, t.timing_type) for t in zn.timings],
                         [(["A1"], "negative_unate", "combinational"),
                          (["A2"], "negative_unate", "combinational")])

    def test_cell_rise_table(self):
        table = self.lib.cells["ND2D1"].pin("ZN").timings[0].tables["cell_rise"]
        self.assertEqual(table.template, "delay_template_3x3")
        self.assertEqual(table.index_1, [0.005, 0.02, 0.08])
        self.assertEqual(table.values[2][1], 0.0280)

    def test_ocv_sigma_not_nldm(self):
        timing = self.lib.cells["ND2D1"].pin("ZN").timings[0]
        self.assertEqual(sorted(timing.tables),
                         ["cell_fall", "cell_rise", "fall_transition", "rise_transition"])

    def test_invd1_indices_from_template(self):
        # The INVD1 tables carry no index_1/index_2 of their own ...
        root = liberty.parse_file(TOY_LIB)
        zn = find_group(find_group(root, "cell", "INVD1"), "pin", "ZN")
        for g in zn.find_groups("timing")[0].groups:
            self.assertEqual(g.find_attrs("index_1") + g.find_attrs("index_2"), [])
        # ... so the accessor fills them in from delay_template_3x3.
        timing = self.lib.cells["INVD1"].pin("ZN").timings[0]
        self.assertEqual(timing.related_pins, ["I"])
        self.assertEqual(len(timing.tables), 4)
        for table in timing.tables.values():
            self.assertEqual(table.index_1, [0.005, 0.02, 0.08])
            self.assertEqual(table.index_2, [0.0005, 0.002, 0.008])
            self.assertEqual(len(table.values), 3)

    def assertLoadError(self, text, line, names):
        with self.assertRaises(liberty.StaError) as cm:
            liberty.loads(text, "e.lib")
        self.assertEqual((cm.exception.file, cm.exception.line), ("e.lib", line))
        for name in names:
            self.assertIn(name, cm.exception.message)

    def test_error_bad_direction(self):
        text = (
            "library (e) {\n"                     # 1
            "  capacitive_load_unit (1, pf);\n"   # 2
            "  cell (MYCELL) {\n"                 # 3
            "    pin (MYIN) {\n"                  # 4
            "      direction : inout;\n"          # 5
            "      capacitance : 0.001;\n"        # 6
            "    }\n"
            "  }\n"
            "}\n"
        )
        self.assertLoadError(text, 5, ["MYCELL", "MYIN"])

    def test_error_input_without_capacitance(self):
        text = (
            "library (e) {\n"                     # 1
            "  capacitive_load_unit (1, pf);\n"   # 2
            "  cell (MYCELL) {\n"                 # 3
            "    pin (MYIN) {\n"                  # 4
            "      direction : input;\n"          # 5
            "    }\n"
            "  }\n"
            "}\n"
        )
        self.assertLoadError(text, 4, ["MYCELL", "MYIN"])

    def test_error_table_shape(self):
        text = (
            "library (e) {\n"                                     # 1
            "  capacitive_load_unit (1, pf);\n"                   # 2
            "  lu_table_template (t3) {\n"                        # 3
            "    variable_1 : input_net_transition;\n"            # 4
            "    variable_2 : total_output_net_capacitance;\n"    # 5
            '    index_1 ("0.1, 0.2, 0.3");\n'                    # 6
            '    index_2 ("0.01, 0.02");\n'                       # 7
            "  }\n"                                               # 8
            "  cell (MYCELL) {\n"                                 # 9
            "    pin (MYIN) {\n"                                  # 10
            "      direction : input;\n"                          # 11
            "      capacitance : 0.001;\n"                        # 12
            "    }\n"                                             # 13
            "    pin (MYOUT) {\n"                                 # 14
            "      direction : output;\n"                         # 15
            "      timing () {\n"                                 # 16
            '        related_pin : "MYIN";\n'                     # 17
            "        cell_rise (t3) {\n"                          # 18
            '          values ("1, 2", \\\n'                      # 19
            '                  "3, 4");\n'                        # 20
            "        }\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        self.assertLoadError(text, 19, ["MYCELL", "MYOUT"])


if __name__ == "__main__":
    unittest.main()
