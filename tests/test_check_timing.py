import os
import subprocess
import sys
import unittest

from test_cli import FF2_V, ROOT, TOY2_LIB, TempDirTest, run_cli

GOLDEN = os.path.join(ROOT, "tests", "golden", "check_timing")
WARNING = b"warning: 2 timing arcs ignored (run --check-timing)\n"
# A recovery arc on the DFF's D pin, as real flops carry on their reset pins.
RECOVERY = ("      timing () {\n        related_pin : \"CK\";\n        timing_type : recovery_rising;\n"
            "        rise_constraint (cons_3x3) {\n          values ( \"1, 1, 1\", \"1, 1, 1\", \"1, 1, 1\" );\n"
            "        }\n      }\n")


def golden(name):
    with open(os.path.join(GOLDEN, name), "rb") as f:
        return f.read()


class GoldenDiff(TempDirTest):
    def assertGolden(self, out, name):
        diff = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "diff_ref.py"),
                               os.path.join(ROOT, "tests", "golden", name), out, "--tol", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(diff.returncode, 0, diff.stdout.decode())


class CheckTimingGoldenTests(GoldenDiff):
    """R35: --check-timing against the hand-reviewed golden files (check_timing.md)."""

    def test_goldens(self):
        for design, scenario in (("s27", "s27"), ("ff2", "ff2_default")):
            with self.subTest(scenario=scenario):
                result = run_cli("--lib", "data/toy2.lib", "--verilog", "data/%s.v" % design,
                                 "--sdc", "data/sdc/%s.sdc" % scenario, "--check-timing")
                self.assertEqual((result.returncode, result.stderr), (0, b""))
                self.assertEqual(result.stdout, golden(scenario + ".txt"))

    def test_stdout_order_and_other_outputs(self):
        # Summary first, then check_timing; --dump-tsv still writes the P2 golden files.
        out = os.path.join(self.tmp, "out")
        result = run_cli("--lib", "data/toy2.lib", "--verilog", "data/ff2.v",
                         "--sdc", "data/sdc/ff2_default.sdc", "--report-summary",
                         "--check-timing", "--dump-tsv", out)
        summary = run_cli("--lib", "data/toy2.lib", "--verilog", "data/ff2.v",
                          "--sdc", "data/sdc/ff2_default.sdc", "--report-summary")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, summary.stdout + golden("ff2_default.txt"))
        self.assertGolden(out, "ff2_default")

    def test_needs_sdc(self):
        result = run_cli("--lib", TOY2_LIB, "--verilog", FF2_V, "--check-timing")
        self.assertOneLineError(result, "^error: --check-timing needs --sdc\n$")


class IgnoredArcTests(GoldenDiff):
    """R35: unsupported timing() groups are ignored, counted, warned about and listed."""

    def library(self, old, new):
        with open(TOY2_LIB) as f:
            text = f.read()
        # The first occurrence: toy2.lib starts with BUF.
        self.assertLess(text.index(old), text.index("cell (INV)"))
        return self.write("lib.lib", text.replace(old, new, 1))

    def run_ff2(self, lib, *extra):
        out = os.path.join(self.tmp, "out")
        return out, run_cli("--lib", lib, "--verilog", FF2_V,
                            "--sdc", os.path.join(ROOT, "data", "sdc", "ff2_default.sdc"),
                            "--dump-tsv", out, *extra)

    def test_recovery_arc(self):
        anchor = "        timing_type : hold_rising;\n"
        with open(TOY2_LIB) as f:
            text = f.read()
        # Put the recovery group right before the hold group of DFF/D.
        start = text.index(anchor)
        start = text.rindex("      timing () {\n", 0, start)
        lib = self.write("rec.lib", text[:start] + RECOVERY + text[start:])
        out, result = self.run_ff2(lib, "--check-timing")
        self.assertEqual((result.returncode, result.stderr), (0, WARNING), result.stderr.decode())
        lines = result.stdout.decode().splitlines()
        i = lines.index("ignored timing arcs: 2")
        self.assertEqual(lines[i + 1], "  DFF D CK recovery_rising 2")
        self.assertTrue(lines[i + 2].startswith("lookups outside"))
        # Ignoring the arc changes no value.
        self.assertGolden(out, "ff2_default")

    def test_warning_without_check_timing(self):
        lib = self.library("timing_sense : positive_unate;\n", "")
        out, result = self.run_ff2(lib)
        self.assertEqual((result.returncode, result.stdout), (0, b""))
        self.assertEqual(result.stderr, b"warning: 1 timing arcs ignored (run --check-timing)\n")
        _, result = self.run_ff2(lib, "--check-timing")
        self.assertIn(b"ignored timing arcs: 1\n  BUF Y A combinational:none 1\n", result.stdout)


class ConstraintSectionTests(TempDirTest):
    """R35: sections 1-5 and 7 on a netlist and SDC written by the test."""

    def test_sections(self):
        v = self.write("u.v", "module u (clk, ck2, a, b, z, w);\n"
                              "  input clk;\n  input ck2;\n  input a;\n  input b;\n"
                              "  output z;\n  output w;\n"
                              "  DFF FF1 (.CK(clk), .D(a), .Q(z));\n"
                              "  DFF FF2 (.CK(ck2), .D(b), .Q(w));\n"
                              "endmodule\n")
        sdc = self.write("u.sdc", "create_clock -name clk -period 10 [get_ports clk]\n"
                                  "set_clock_transition 0.05 [get_clocks clk]\n"
                                  "set_input_delay 1.0 -clock clk [get_ports a]\n"
                                  "set_input_transition 0.5 [get_ports a]\n"
                                  "set_input_transition 0.05 [get_ports ck2]\n"
                                  "set_output_delay 1.0 -clock clk [get_ports z]\n"
                                  "set_load 0.002 [get_ports w]\n")
        result = run_cli("--lib", TOY2_LIB, "--verilog", v, "--sdc", sdc, "--check-timing")
        self.assertEqual((result.returncode, result.stderr), (0, b""), result.stderr.decode())
        # FF2/CK hangs on port ck2, not on the clock net (it is still timed with the ideal
        # clock); a's slew 0.5 is above the grid, b's 0 below; z has no load (FF1's CK->Q
        # lookups, forward 8 and backward 4, are below the load grid); FF2/Q drives the
        # unconstrained w, so FF2 has no backward lookup: 12 + 8 + 8 checks = 28.
        self.assertEqual(result.stdout.decode(), (
            "unconstrained endpoints: 2\n  FF2/D\n  w\n"
            "unclocked registers: 1\n  FF2\n"
            "input ports without set_input_delay: 2\n  b\n  ck2\n"
            "input ports without set_input_transition: 1\n  b\n"
            "output ports without set_load: 1\n  z\n"
            "ignored timing arcs: 0\n"
            "lookups outside the table grid: 20 of 28\n"
            "  cell_fall total_output_net_capacitance below 4 above 0 query 0.0000..0.0000 grid 0.0010..0.0160\n"
            "  cell_rise total_output_net_capacitance below 4 above 0 query 0.0000..0.0000 grid 0.0010..0.0160\n"
            "  fall_constraint constrained_pin_transition below 2 above 2 query 0.0000..0.5000 grid 0.0100..0.2000\n"
            "  fall_transition total_output_net_capacitance below 2 above 0 query 0.0000..0.0000 grid 0.0010..0.0160\n"
            "  rise_constraint constrained_pin_transition below 2 above 2 query 0.0000..0.5000 grid 0.0100..0.2000\n"
            "  rise_transition total_output_net_capacitance below 2 above 0 query 0.0000..0.0000 grid 0.0010..0.0160\n"))


if __name__ == "__main__":
    unittest.main()
