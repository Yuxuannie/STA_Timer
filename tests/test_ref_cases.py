"""R40: the classification of the OpenSTA differences (REPORT_P5.md §7, ref/cases/).

Skipped unless `ref/opensta/run.sh --probe` succeeds. Two kinds of test:
- each case still shows its difference (P5-1a is an adapter gap, the rest policy), with both tools' values as recorded in §7
  (so the classification is re-checked when either tool changes);
- with the P5-2 .. P5-4 policies neutralised (ref/cases/aligned/), every cell of s27,
  ff2_swap and ff2_unc other than the CK-pin / clock-port conventions (P5-1) agrees
  within 1 ps, i.e. no further class hides under them.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_SH = os.path.join(ROOT, "ref", "opensta", "run.sh")
CASES = os.path.join(ROOT, "ref", "cases")


def _probe():
    try:
        return subprocess.run([RUN_SH, "--probe"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE).returncode == 0
    except OSError:
        return False


HAVE_STA = _probe()


def _read(path):
    with open(path) as f:
        rows = [line.rstrip("\n").split("\t") for line in f]
    head = rows[0]
    return head, {r[0]: dict(zip(head, r)) for r in rows[1:]}


@unittest.skipUnless(HAVE_STA, "OpenSTA not available (ref/opensta/run.sh --probe)")
class CaseTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_case(self, verilog, sdc):
        """-> (opensta dir, toy dir) in golden format."""
        raw, toy, ref = (os.path.join(self.tmp, d) for d in ("raw", "toy", "opensta"))
        subprocess.run([RUN_SH, verilog, sdc, raw], check=True)
        subprocess.run([sys.executable, "-m", "sta_toy", "--lib", os.path.join(ROOT, "data", "toy2.lib"),
                        "--verilog", verilog, "--sdc", sdc, "--dump-tsv", toy], check=True, cwd=ROOT)
        subprocess.run([sys.executable, os.path.join(ROOT, "ref", "opensta", "to_golden.py"), raw, ref,
                        "--toy-pins", toy], check=True, stdout=subprocess.DEVNULL)
        return ref, toy

    def values(self, case, verilog, sdc, f, pin, col):
        ref, toy = self.run_case(os.path.join(CASES, case, verilog), os.path.join(CASES, case, sdc))
        return _read(os.path.join(ref, f))[1][pin][col], _read(os.path.join(toy, f))[1][pin][col]

    def test_p5_1_ck_pin_slew(self):
        self.assertEqual(self.values("ck_conventions", "reg1.v", "ck_slew.sdc", "pins.tsv", "FF1/CK",
                                     "slew_late_r"), ("0.0000", "0.0500"))

    def test_p5_2_input_delay_with_latency(self):
        self.assertEqual(self.values("io_latency", "reg1.v", "latency.sdc", "pins.tsv", "d", "at_late_r"),
                         ("0.8000", "0.5000"))

    def test_p5_3_output_port_uncertainty(self):
        self.assertEqual(self.values("po_uncertainty", "reg1.v", "po_unc.sdc", "endpoints.tsv", "q",
                                     "setup_rat"), ("7.5000", "8.0000"))

    def test_p5_4_max_only_input_delay(self):
        self.assertEqual(self.values("input_delay_facets", "reg1.v", "max_only.sdc", "endpoints.tsv",
                                     "FF1/D", "hold_slack"), ("NA", "-0.1000"))

    def test_p5_5_tie_break(self):
        ref, toy = self.run_case(os.path.join(CASES, "tie_break", "tie2.v"),
                                 os.path.join(CASES, "tie_break", "tie.sdc"))
        with open(os.path.join(ref, "paths.txt")) as f:
            ref_paths = f.read()
        with open(os.path.join(toy, "paths.txt")) as f:
            toy_paths = f.read()
        self.assertIn("FF1/D setup 7.2000 : b(f) -> U1/B(f)", ref_paths)
        self.assertIn("FF1/D setup 7.2000 : a(f) -> U1/A(f)", toy_paths)

    def test_aligned_designs_have_no_other_difference(self):
        for design, verilog in (("s27", "s27.v"), ("ff2_swap", "ff2.v"), ("ff2_unc", "ff2.v")):
            with self.subTest(design=design):
                ref, toy = self.run_case(os.path.join(ROOT, "data", verilog),
                                         os.path.join(CASES, "aligned", design + "_aligned.sdc"))
                for f in ("pins.tsv", "endpoints.tsv"):
                    head, a = _read(os.path.join(ref, f))
                    _, b = _read(os.path.join(toy, f))
                    self.assertEqual(set(a), set(b))
                    for pin in a:
                        if pin.endswith("/CK") or pin == "clk":
                            continue            # P5-1
                        for col in head[1:]:
                            x, y = a[pin][col], b[pin][col]
                            if "NA" in (x, y):
                                self.assertEqual(x, y, (f, pin, col))
                            else:
                                self.assertAlmostEqual(float(x), float(y), delta=0.001, msg=(f, pin, col))


if __name__ == "__main__":
    unittest.main()
