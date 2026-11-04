import unittest

from sta_toy import sdc

CLOCK = "create_clock -name clk -period 10.0 [get_ports clk]\n"


class ParseTests(unittest.TestCase):
    """R13 / R19d: the SDC parser module on its own."""

    def test_every_command_form(self):
        text = (
            "# every command form of sdc_subset.md\n"
            + CLOCK +
            "set_clock_transition 0.05 [get_clocks clk]\n"
            "set_clock_latency 1.5 [get_pins FF1/CK]\n"
            "set_clock_latency 0.3 [get_clocks clk]\n"
            "set_clock_latency 0.4 [get_clocks clk]   # later clock-level line wins\n"
            "set_clock_uncertainty -hold 0.1 [get_clocks clk]\n"
            "set_clock_uncertainty 0.3 [get_clocks clk]\n"
            "set_clock_uncertainty -setup 0.5 [get_clocks clk]\n"
            "set_input_delay 0.5 -clock clk [get_ports x]\n"
            "set_input_delay -clock clk -max 0.7 [get_ports x]\n"
            "set_input_delay -min -0.2 -clock clk [get_ports z]\n"
            "set_output_delay 2.0 -clock clk [get_ports y]\n"
            "set_output_delay -max 2.5 -clock clk [get_ports y]\n"
            "set_output_delay -min 0.5 -clock clk [get_ports w]\n"
            "\n"
            "set_input_transition 0.05 [get_ports x]\n"
            "set_load 0.002 [get_ports y]\n"
        )
        c = sdc.parse(text, "all.sdc")
        self.assertEqual((c.clock_name, c.clock_port, c.period), ("clk", "clk", 10.0))
        self.assertEqual(c.clock_transition, 0.05)
        self.assertEqual(c.clock_latency, 0.4)
        self.assertEqual(c.pin_latency, {"FF1/CK": 1.5})
        self.assertEqual(c.uncertainty, {"setup": 0.5, "hold": 0.3})
        self.assertEqual(c.input_delay, {"x": {"min": 0.5, "max": 0.7}, "z": {"min": -0.2}})
        self.assertEqual(c.output_delay, {"y": {"min": 2.0, "max": 2.5}, "w": {"min": 0.5}})
        self.assertEqual(c.input_transition, {"x": 0.05})
        self.assertEqual(c.load, {"y": 0.002})
        self.assertEqual(c.objects[:3], [(2, "create_clock", "get_ports", "clk"),
                                         (3, "set_clock_transition", "get_clocks", "clk"),
                                         (4, "set_clock_latency", "get_pins", "FF1/CK")])
        self.assertIn((10, "set_input_delay", "get_clocks", "clk"), c.objects)

    def test_defaults(self):
        c = sdc.parse(CLOCK, "d.sdc")
        self.assertEqual((c.clock_transition, c.clock_latency), (0.0, 0.0))
        self.assertEqual(c.uncertainty, {"setup": 0.0, "hold": 0.0})
        self.assertEqual((c.input_delay, c.output_delay, c.pin_latency), ({}, {}, {}))

    def assertSyntaxError(self, bad_line, expected_text):
        text = CLOCK + "set_load 0.1 [get_ports y]\n" + bad_line + "\n"
        with self.assertRaises(sdc.P2Error) as cm:
            sdc.parse(text, "s.sdc")
        self.assertEqual((cm.exception.file, cm.exception.line), ("s.sdc", 3))
        self.assertTrue(str(cm.exception).startswith("s.sdc:3: "), str(cm.exception))
        self.assertIn(expected_text, cm.exception.message)

    def test_unknown_command(self):
        self.assertSyntaxError("set_driving_cell -lib_cell BUF [get_ports x]", "unknown command")

    def test_unknown_option(self):
        self.assertSyntaxError("set_input_delay 0.5 -clock clk -add_delay [get_ports x]",
                               "unknown option -add_delay")

    def test_min_and_max(self):
        self.assertSyntaxError("set_input_delay -min -max 0.5 -clock clk [get_ports x]",
                               "-min and -max")
        self.assertSyntaxError("set_clock_uncertainty -setup -hold 0.1 [get_clocks clk]",
                               "-setup and -hold")

    def test_missing_value(self):
        self.assertSyntaxError("set_load [get_ports y]", "missing value")

    def test_missing_object_list(self):
        self.assertSyntaxError("set_load 0.1 y", "unexpected token y")
        self.assertSyntaxError("set_load 0.1", "missing object list")

    def test_malformed_object_list(self):
        self.assertSyntaxError("set_load 0.1 [get_ports y", "malformed object list")
        self.assertSyntaxError("set_load 0.1 [get_nets y]", "malformed object list")

    def test_wildcard_or_several_names(self):
        self.assertSyntaxError("set_load 0.1 [get_ports y*]", "wildcards")
        self.assertSyntaxError("set_load 0.1 [get_ports y z]", "exactly one object")

    def test_clock_option_missing(self):
        self.assertSyntaxError("set_output_delay 1.0 [get_ports y]", "-clock missing")

    def test_second_create_clock(self):
        self.assertSyntaxError("create_clock -name clk2 -period 5 [get_ports clk2]",
                               "second create_clock")

    def test_clock_named_before_it_is_created(self):
        text = ("set_input_delay 0.5 -clock clk [get_ports x]\n"
                + CLOCK)
        with self.assertRaises(sdc.P2Error) as cm:
            sdc.parse(text, "o.sdc")
        self.assertEqual((cm.exception.file, cm.exception.line), ("o.sdc", 1))
        self.assertIn("clock clk is not defined", cm.exception.message)


if __name__ == "__main__":
    unittest.main()
