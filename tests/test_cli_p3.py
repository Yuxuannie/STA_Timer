import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(ROOT, "tests", "golden", "reports")


def cli(design, scenario, *extra):
    return subprocess.run([sys.executable, "-m", "sta_toy", "--lib", "data/toy2.lib",
                           "--verilog", "data/%s.v" % design, "--sdc", "data/sdc/%s.sdc" % scenario]
                          + list(extra), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def golden(name):
    with open(os.path.join(REPORTS, name), "rb") as f:
        return f.read()


class ReportCliTests(unittest.TestCase):
    """R26: report_timing / summary through the CLI, against the hand-written golden."""

    def assertOutput(self, result, expected):
        self.assertEqual((result.returncode, result.stderr), (0, b""), result.stderr.decode())
        self.assertEqual(result.stdout, expected)

    def test_report_timing(self):
        # The worst setup endpoint of ff2_default is FF2/D (5.7 against 8.7 and 7.0).
        self.assertOutput(cli("ff2", "ff2_default", "--report-timing"),
                          golden("ff2_default_FF2_D_max.txt"))
        self.assertOutput(cli("ff2", "ff2_default", "--report-timing", "--path-delay", "min",
                              "--to", "FF2/D"), golden("ff2_default_FF2_D_min.txt"))
        self.assertOutput(cli("inv2", "inv2", "--report-timing", "--to", "y",
                              "--capacitance", "--transition-time"),
                          golden("inv2_y_max_cap_trans.txt"))

    def test_several_paths(self):
        result = cli("ff2", "ff2_default", "--report-timing", "--max-paths", "3")
        blocks = result.stdout.decode().split("\n\nStartpoint: ")
        self.assertEqual(len(blocks), 3)
        self.assertEqual(result.stdout.decode().split("\n\nStartpoint: ")[0] + "\n",
                         golden("ff2_default_FF2_D_max.txt").decode())
        ends = [line for line in result.stdout.decode().splitlines() if line.startswith("Endpoint: ")]
        self.assertEqual([e.split()[1] for e in ends], ["FF2/D", "y", "FF1/D"])

    def test_no_paths(self):
        # s27 G17 has no -min output delay, so no hold path.
        self.assertOutput(cli("s27", "s27", "--report-timing", "--path-delay", "min", "--to", "G17"),
                          b"No paths.\n")

    def test_summary(self):
        # ff2_setupviol endpoints.tsv: setup slacks -0.3 (FF2/D), 2.7 (FF1/D), 1.0 (y).
        result = cli("ff2", "ff2_setupviol", "--report-summary")
        lines = result.stdout.decode().splitlines()
        self.assertEqual(lines[0].split(), ["check", "wns", "tns", "nvp"])
        self.assertEqual(lines[1].split(), ["setup", "-0.3000", "-0.3000", "1"])


class FileOutputTests(unittest.TestCase):
    """R26: --json and --bundle write files; stdout stays empty without report options."""

    def test_json_and_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_json, out_bundle = os.path.join(tmp, "r.json"), os.path.join(tmp, "b.json")
            result = cli("ff2", "ff2_default", "--json", out_json, "--bundle", "FF2/D",
                         "--bundle-out", out_bundle, "--depth", "1")
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
            with open(out_json) as f:
                report = json.load(f)
            with open(out_bundle) as f:
                bundle = json.load(f)
        self.assertEqual(report["schema"], "sta_toy.report/1")
        self.assertEqual(report["design"]["libs"], ["data/toy2.lib"])
        self.assertEqual([e["pin"] for e in report["endpoints"]], ["FF1/D", "FF2/D", "y"])
        self.assertEqual((bundle["schema"], bundle["endpoint"], bundle["depth"]),
                         ("sta_toy.bundle/1", "FF2/D", 1))

    def test_error_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            result = cli("ff2", "ff2_default", "--dump-tsv", out, "--bundle", "U2/Y",
                         "--bundle-out", os.path.join(tmp, "b.json"))
            self.assertEqual(os.listdir(tmp), [])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, b"error: --bundle U2/Y is not an endpoint\n")


class OptionErrorTests(unittest.TestCase):
    """R26: the option rules of cli_p3.md, one stderr line and exit 1 each."""

    def assertError(self, args, message, with_sdc=True):
        base = ["--lib", "data/toy2.lib", "--verilog", "data/ff2.v"]
        if with_sdc:
            base += ["--sdc", "data/sdc/ff2_default.sdc"]
        result = subprocess.run([sys.executable, "-m", "sta_toy"] + base + args, cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual((result.returncode, result.stdout), (1, b""))
        self.assertEqual(result.stderr.decode(), "error: %s\n" % message)

    def test_rules(self):
        cases = [
            (["--report-summary"], "--report-summary needs --sdc", False),
            (["--report-timing", "--nworst", "0"], "--nworst needs an integer >= 1", True),
            (["--report-timing", "--max-paths", "two"], "--max-paths needs an integer >= 1", True),
            (["--report-timing", "--path-delay", "typ"], "--path-delay needs max or min", True),
            (["--report-summary", "--to", "FF2/D"], "--to needs --report-timing", True),
            (["--bundle", "FF2/D"], "--bundle needs --bundle-out", True),
            (["--report-summary", "--depth", "2"], "--depth needs --bundle", True),
            (["--report-summary", "--report-summary"], "--report-summary given twice", True),
            (["--report-timing", "--to", "U2/Y"], "--to U2/Y is not an endpoint", True),
            (["--report-timing", "--from", "U2/Y"], "--from U2/Y is not a startpoint", True),
            (["--report-timing", "--through", "nope"], "--through nope is not a node", True),
        ]
        for args, message, with_sdc in cases:
            with self.subTest(args=args):
                self.assertError(args, message, with_sdc)


if __name__ == "__main__":
    unittest.main()
