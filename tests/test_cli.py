import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOY2_LIB = os.path.join(ROOT, "data", "toy2.lib")
FF2_V = os.path.join(ROOT, "data", "ff2.v")
CLOCK = "create_clock -name clk -period 10.0 [get_ports clk]\n"

DESIGNS = [
    ("ff2_default", "ff2.v", "ff2_default.sdc"),
    ("ff2_swap", "ff2.v", "ff2_swap.sdc"),
    ("ff2_setupviol", "ff2.v", "ff2_setupviol.sdc"),
    ("ff2_holdviol", "ff2.v", "ff2_holdviol.sdc"),
    ("ff2_skew", "ff2.v", "ff2_skew.sdc"),
    ("ff2_unc", "ff2.v", "ff2_unc.sdc"),
    ("inv2", "inv2.v", "inv2.sdc"),
    ("s27", "s27.v", "s27.sdc"),
]


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "sta_toy"] + list(args),
                          cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def assertOneLineError(self, result, pattern=None):
        """Exit code 1, empty stdout, exactly one stderr line (matching `pattern`, a regex)."""
        stderr = result.stderr.decode()
        self.assertEqual(result.returncode, 1, stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(stderr.count("\n"), 1, stderr)
        self.assertTrue(stderr.endswith("\n"))
        if pattern:
            self.assertRegex(stderr, pattern)
        self.assertNotIn("usage", stderr.lower())
        return stderr

    def timing(self, verilog, sdc_text, lib=TOY2_LIB):
        return run_cli("--lib", lib, "--verilog", verilog,
                       "--sdc", self.write("c.sdc", sdc_text),
                       "--dump-tsv", os.path.join(self.tmp, "out"))


class GoldenTests(TempDirTest):
    """R19a: the eight designs against tests/golden/ with tools/diff_ref.py --tol 0."""

    def check(self, name, verilog, sdc_file, *extra_libs):
        out = os.path.join(self.tmp, name)
        libs = [a for lib in (TOY2_LIB,) + extra_libs for a in ("--lib", lib)]
        result = run_cli(*(libs + ["--verilog", os.path.join(ROOT, "data", verilog),
                                   "--sdc", os.path.join(ROOT, "data", "sdc", sdc_file),
                                   "--dump-tsv", out]))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""), name)
        diff = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "diff_ref.py"),
                               os.path.join(ROOT, "tests", "golden", name), out, "--tol", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(diff.returncode, 0, "%s:\n%s" % (name, diff.stdout.decode()))

    def test_designs(self):
        for name, verilog, sdc_file in DESIGNS:
            with self.subTest(design=name):
                self.check(name, verilog, sdc_file)

    def test_second_library(self):
        # Repeated --lib: cells come from every library, first one wins.
        self.check("ff2_default", "ff2.v", "ff2_default.sdc", os.path.join(ROOT, "data", "toy.lib"))


class SdcSemanticErrorTests(TempDirTest):
    """R13 / R19d: one test per semantic error class of sdc_subset.md, through the CLI."""

    def assertSdcError(self, sdc_text, line, message):
        result = self.timing(FF2_V, sdc_text)
        path = os.path.join(self.tmp, "c.sdc")
        self.assertOneLineError(result, "^%s:%d: .*%s" % (re.escape(path), line, re.escape(message)))

    def test_port_does_not_exist(self):
        self.assertSdcError(CLOCK + "set_input_delay 0.5 -clock clk [get_ports nope]\n", 2,
                            "port nope does not exist")

    def test_pin_does_not_exist(self):
        self.assertSdcError(CLOCK + "set_clock_latency 0.5 [get_pins FF9/CK]\n", 2,
                            "pin FF9/CK does not exist")

    def test_pin_is_not_a_clock_pin(self):
        self.assertSdcError(CLOCK + "set_clock_latency 0.5 [get_pins FF1/D]\n", 2,
                            "pin FF1/D is not a clock pin")

    def test_clock_does_not_exist(self):
        self.assertSdcError(CLOCK + "set_clock_transition 0.1 [get_clocks other]\n", 2,
                            "clock other does not exist")
        self.assertSdcError(CLOCK + "set_input_delay 0.5 -clock other [get_ports x]\n", 2,
                            "clock other does not exist")

    def test_create_clock_on_output_port(self):
        self.assertSdcError("create_clock -name clk -period 10 [get_ports y]\n", 1,
                            "create_clock on output port y")

    def test_input_constraint_on_clock_port(self):
        for command in ("set_input_delay 0.5 -clock clk", "set_input_transition 0.1", "set_load 0.1"):
            self.assertSdcError(CLOCK + command + " [get_ports clk]\n", 2, "on the clock port clk")

    def test_input_constraint_on_output_port(self):
        for command in ("set_input_delay 0.5 -clock clk", "set_input_transition 0.1"):
            self.assertSdcError(CLOCK + command + " [get_ports y]\n", 2, "on output port y")

    def test_output_constraint_on_input_port(self):
        for command in ("set_output_delay 0.5 -clock clk", "set_load 0.1"):
            self.assertSdcError(CLOCK + command + " [get_ports x]\n", 2, "on input port x")

    def test_no_create_clock(self):
        self.assertSdcError("set_load 0.1 [get_ports y]\n", 1, "no create_clock")


class ErrorContractTests(TempDirTest):
    """R19e: errors from the link and timing-graph stages, through the CLI."""

    def test_two_drivers_keeps_stage1_message(self):
        v = self.write("dd.v", "module dd (clk, a, z);\n"
                               "  input clk;\n"
                               "  input a;\n"
                               "  output z;\n"
                               "  BUF U1 (.A(a), .Y(z));\n"
                               "  BUF U2 (.A(a), .Y(z));\n"
                               "endmodule\n")
        stderr = self.assertOneLineError(self.timing(v, CLOCK))
        self.assertEqual(stderr, "ERROR %s:4: net z has 2 drivers: U1/Y, U2/Y\n" % v)

    def test_clock_port_drives_non_clock_pin(self):
        v = self.write("ck.v", "module ck (clk, a, z);\n"
                               "  input clk;\n"
                               "  input a;\n"
                               "  output z;\n"
                               "  wire n;\n"
                               "  BUF U1 (.A(clk), .Y(n));\n"
                               "  DFF FF1 (.CK(clk), .D(a), .Q(z));\n"
                               "endmodule\n")
        stderr = self.assertOneLineError(self.timing(v, CLOCK))
        self.assertEqual(stderr, "%s:6: clock port clk drives a non-clock pin U1/A\n" % v)

    def test_combinational_loop(self):
        v = self.write("loop.v", "module loop (clk, a, z);\n"
                                 "  input clk;\n"
                                 "  input a;\n"
                                 "  output z;\n"
                                 "  wire n1, n2;\n"
                                 "  NAND2 U1 (.A(a), .B(n2), .Y(n1));\n"
                                 "  INV U2 (.A(n1), .Y(n2));\n"
                                 "  DFF FF1 (.CK(clk), .D(n1), .Q(z));\n"
                                 "endmodule\n")
        self.assertOneLineError(self.timing(v, CLOCK), r"^error: combinational loop: .*U2/Y")

    def test_unsupported_timing_type(self):
        with open(TOY2_LIB) as f:
            text = f.read()
        self.assertEqual(text.count("timing_type : rising_edge;"), 1)
        lib = self.write("falling.lib", text.replace("timing_type : rising_edge;",
                                                     "timing_type : falling_edge;"))
        # R35 (cli_p5.md): no longer an error; the arc is ignored, counted and listed.
        result = self.timing(FF2_V, CLOCK, lib=lib)
        self.assertEqual((result.returncode, result.stdout), (0, b""))
        self.assertEqual(result.stderr, b"warning: 2 timing arcs ignored (run --check-timing)\n")
        result = run_cli("--lib", lib, "--verilog", FF2_V, "--sdc", os.path.join(self.tmp, "c.sdc"),
                         "--check-timing")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"\nignored timing arcs: 2\n  DFF Q CK falling_edge 2\nlookups outside",
                      result.stdout)


class ForwardTieTests(TempDirTest):
    """R19g: both inputs of U1 tie; the path goes through U1/A (pin name order), D transition r."""

    def test_tie(self):
        v = self.write("tie.v", "module tie (clk, p, q, y);\n"
                                "  input clk;\n"
                                "  input p;\n"
                                "  input q;\n"
                                "  output y;\n"
                                "  wire n;\n"
                                "  NAND2 U1 (.A(q), .B(p), .Y(n));\n"
                                "  DFF FF1 (.CK(clk), .D(n), .Q(y));\n"
                                "endmodule\n")
        result = self.timing(v, "create_clock -name clk -period 10 [get_ports clk]\n"
                                "set_clock_transition 0.05 [get_clocks clk]\n"
                                "set_input_delay 1.0 -clock clk [get_ports p]\n"
                                "set_input_delay 1.0 -clock clk [get_ports q]\n"
                                "set_input_transition 0.05 [get_ports p]\n"
                                "set_input_transition 0.05 [get_ports q]\n"
                                "set_output_delay 1.0 -clock clk [get_ports y]\n")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        with open(os.path.join(self.tmp, "out", "paths.txt")) as f:
            lines = f.read().splitlines()
        self.assertIn("FF1/D setup 6.7000 : q(f) -> U1/A(f) -> U1/Y(r) -> FF1/D(r)", lines)
        self.assertIn("FF1/D hold 2.9000 : q(f) -> U1/A(f) -> U1/Y(r) -> FF1/D(r)", lines)


class CliTests(TempDirTest):
    """R19h: options and the error contract of cli_p2.md. Stage 1 output without --sdc is
    checked byte for byte by test_graph.CliTests.test_golden (R19f)."""

    def test_unknown_option(self):
        # --report-timing was unknown in P2; P3 (cli_p3.md) made it an option.
        result = run_cli("--lib", "data/toy.lib", "--verilog", "data/c17.v", "--report-power")
        stderr = self.assertOneLineError(result)
        self.assertEqual(stderr, "error: unknown option --report-power\n")

    def test_sdc_without_dump_tsv(self):
        result = run_cli("--lib", TOY2_LIB, "--verilog", FF2_V,
                         "--sdc", os.path.join(ROOT, "data", "sdc", "ff2_default.sdc"))
        # cli_p3.md replaced "--sdc and --dump-tsv must be given together" by these two rules.
        self.assertOneLineError(result, r"^error: --sdc needs an output option \(--dump-tsv, ")

    def test_dump_tsv_without_sdc(self):
        result = run_cli("--lib", TOY2_LIB, "--verilog", FF2_V, "--dump-tsv", self.tmp)
        self.assertOneLineError(result, "^error: --dump-tsv needs --sdc\n$")
        self.assertEqual(os.listdir(self.tmp), [])

    def test_missing_verilog(self):
        self.assertOneLineError(run_cli("--lib", TOY2_LIB), "^error: missing --verilog\n$")


if __name__ == "__main__":
    unittest.main()
