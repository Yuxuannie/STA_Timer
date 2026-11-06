import os
import unittest

from sta_toy import liberty, lookup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOY2_LIB = os.path.join(ROOT, "data", "toy2.lib")


class InterpolationTests(unittest.TestCase):
    """R11 / R19b: bilinear interpolation and linear extrapolation on v = x1 * x2 / 10."""

    INDEX_1 = [1, 2, 4]
    INDEX_2 = [10, 20, 40]
    VALUES = [[1, 2, 4], [2, 4, 8], [4, 8, 16]]

    def test_points(self):
        cases = [
            ((1, 10), 1.0),     # grid point
            ((1.5, 10), 1.5),   # along one axis
            ((1.5, 15), 2.25),  # interior bilinear; a plane fit would differ
            ((3, 30), 9.0),     # second cell
            ((2, 40), 8.0),     # grid point on the far edge
            ((0.5, 10), 0.5),   # extrapolation below axis 1
            ((4, 5), 2.0),      # extrapolation below axis 2
            ((5, 50), 25.0),    # beyond both axes; clamping would give 16.0
        ]
        for (x1, x2), expected in cases:
            got = lookup.bilinear(self.INDEX_1, self.INDEX_2, self.VALUES, x1, x2)
            self.assertAlmostEqual(got, expected, delta=1e-9, msg="(%s, %s)" % (x1, x2))


class LookupDetailTests(unittest.TestCase):
    """P5 interface: lookup_detail reports the grid cell lookup() used, on the R19b table."""

    class _Table:
        variables = ["a", "b"]
        index_1 = InterpolationTests.INDEX_1
        index_2 = InterpolationTests.INDEX_2
        values = InterpolationTests.VALUES

    def detail(self, a, b):
        return lookup.lookup_detail(self._Table, {"a": a, "b": b})

    def test_interior(self):
        d = self.detail(1.5, 15)
        self.assertEqual(d["corners"], [[1, 2], [2, 4]])
        self.assertEqual(d["segment"], [0, 0])
        self.assertEqual(d["bracket"], [[1, 2], [10, 20]])
        self.assertEqual(d["extrapolated"], [None, None])
        self.assertEqual(d["axes"], ["a", "b"])
        self.assertEqual(d["query"], [1.5, 15])

    def test_above_both(self):
        d = self.detail(5, 50)
        self.assertEqual(d["segment"], [1, 1])
        self.assertEqual(d["extrapolated"], ["above", "above"])

    def test_below_axis_1(self):
        self.assertEqual(self.detail(0.5, 10)["extrapolated"], ["below", None])

    def test_value_equals_lookup(self):
        for a, b in [(1, 10), (1.5, 15), (3, 30), (0.5, 10), (4, 5), (5, 50), (2, 40)]:
            self.assertEqual(self.detail(a, b)["value"], lookup.lookup(self._Table, {"a": a, "b": b}))


class TemplateOrderTests(unittest.TestCase):
    """R10 + R11 / R19c: axes come from the template's variable names."""

    @classmethod
    def setUpClass(cls):
        cls.lib = liberty.load(TOY2_LIB)

    def test_buf_cell_rise(self):
        # del_3x3 has load on axis 1 and slew on axis 2; swapped axes would give 1.832.
        table = self.lib.cells["BUF"].pin("Y").timings[0].tables["cell_rise"]
        got = lookup.lookup(table, {"input_net_transition": 0.01,
                                    "total_output_net_capacitance": 0.016})
        self.assertAlmostEqual(got, 2.12, delta=1e-9)

    def test_dff_hold_rise_constraint(self):
        # cons_3x3 has D slew on axis 1 and CK slew on axis 2; swapped axes would give 0.36.
        hold = [t for t in self.lib.cells["DFF"].pin("D").timings if t.timing_type == "hold_rising"]
        got = lookup.lookup(hold[0].tables["rise_constraint"],
                            {"constrained_pin_transition": 0.2, "related_pin_transition": 0.01})
        self.assertAlmostEqual(got, 0.17, delta=1e-9)


if __name__ == "__main__":
    unittest.main()
