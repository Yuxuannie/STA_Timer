"""R39: the OpenSTA adapter (ref/opensta/to_golden.py), tools/correlate.py, and the
OpenSTA run itself (skipped unless ref/opensta/run.sh --probe succeeds)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ref", "opensta"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import to_golden  # noqa: E402
from test_bench2v import check_golden_dir  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "golden")
DESIGNS = ["ff2_default", "ff2_swap", "ff2_setupviol", "ff2_holdviol", "ff2_skew", "ff2_unc",
           "inv2", "s27"]
RUN_SH = os.path.join(ROOT, "ref", "opensta", "run.sh")


def run(args):
    return subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def tsv(path):
    with open(path) as f:
        lines = [ln.rstrip("\n").split("\t") for ln in f if ln.strip()]
    return lines[0], lines[1:]


def raw_from_golden(golden_dir, raw_dir):
    """Write what run.tcl would write if OpenSTA agreed with golden_dir exactly:
    arrivals, slews and slacks (from RAT - AT), INF for undefined."""
    _h, rows = tsv(os.path.join(golden_dir, "pins.tsv"))
    out = ["\t".join(to_golden.RAW_COLS)]
    for r in rows:
        v = [None if c == "NA" else float(c) for c in r[1:]]
        at, rat, slew = v[0:4], v[4:8], v[8:12]
        slack = [None if rat[0] is None else rat[0] - at[0],
                 None if rat[1] is None else rat[1] - at[1],
                 None if rat[2] is None else at[2] - rat[2],
                 None if rat[3] is None else at[3] - rat[3]]
        cells = (["-INF" if x is None else repr(x) for x in at]
                 + ["INF" if x is None else repr(x) for x in slack]
                 + ["NA" if x is None else repr(x) for x in slew])
        out.append("\t".join([r[0], "port" if "/" not in r[0] else "pin"] + cells))
    with open(os.path.join(raw_dir, "pins.tsv"), "w") as f:
        f.write("\n".join(out) + "\n")
    lines = []
    with open(os.path.join(golden_dir, "paths.txt")) as f:
        for ln in f:
            head, _, seq = ln.rstrip("\n").partition(" : ")
            end, check, slack = head.split()
            lines.append("END %s %s %s" % (end, check, slack))
            for node in seq.split(" -> "):
                name, rf = node[:-3], node[-2]
                lines.append("PT %s %s 0.0" % (name, {"r": "^", "f": "v"}[rf]))
    with open(os.path.join(raw_dir, "paths.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


class ToGoldenTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip_of_the_eight_goldens(self):
        # RAT from slack and the worst-transition rule reproduce the golden files exactly.
        for name in DESIGNS:
            with self.subTest(design=name):
                raw = os.path.join(self.tmp, name, "raw")
                out = os.path.join(self.tmp, name, "opensta")
                os.makedirs(raw)
                raw_from_golden(os.path.join(GOLDEN, name), raw)
                to_golden.convert(raw, out)
                for fname in ("pins.tsv", "endpoints.tsv", "paths.txt"):
                    with open(os.path.join(GOLDEN, name, fname)) as f1, \
                            open(os.path.join(out, fname)) as f2:
                        self.assertEqual(f2.read(), f1.read(), fname)

    def test_hand_made_sample(self):
        # A sample in OpenSTA's own text: INF slacks, ^/v edges, 6 digits.
        raw = os.path.join(self.tmp, "raw")
        os.makedirs(raw)
        with open(os.path.join(raw, "pins.tsv"), "w") as f:
            f.write("\t".join(to_golden.RAW_COLS) + "\n")
            f.write("a\tport\t0.000000\t0.000000\t0.000000\t0.000000\t2.500000\t2.400000"
                    "\t0.300000\t0.300000\t0.050000\t0.050000\t0.050000\t0.050000\n")
            f.write("U1/A\tpin\t0.000000\t0.000000\t0.000000\t0.000000\tINF\t2.400000"
                    "\t0.300000\tINF\t0.050000\t0.050000\t0.050000\t0.050000\n")
            f.write("U1/Y\tpin\t1.200000\t0.800000\t1.200000\t0.800000\t2.400000\t2.400000"
                    "\t1.500000\t1.500000\t0.071234\t0.060000\t0.071234\t0.060000\n")
            f.write("clk\tport\t-INF\t-INF\tINF\tINF\tINF\tINF\tINF\tINF\t0.0\t0.0\t0.0\t0.0\n")
        with open(os.path.join(raw, "paths.txt"), "w") as f:
            f.write("END U1/Y hold 1.500000\nPT a ^ 0.0\nPT U1/A ^ 0.0\nPT U1/Y v 0.8\n"
                    "END U1/Y setup 2.400000\nPT a v 0\nPT U1/A v 0\nPT U1/Y ^ 1.2\n")
        out = os.path.join(self.tmp, "out")
        r = run([sys.executable, os.path.join("ref", "opensta", "to_golden.py"), raw, out])
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        check_golden_dir(self, out)
        _h, pins = tsv(os.path.join(out, "pins.tsv"))
        self.assertEqual([p[0] for p in pins], ["U1/A", "U1/Y", "a", "clk"])
        self.assertEqual(pins[0][1:9], ["0.0000"] * 4 + ["NA", "2.4000", "-0.3000", "NA"])
        self.assertEqual(pins[1][5:13], ["3.6000", "3.2000", "-0.3000", "-0.7000",
                                         "0.0712", "0.0600", "0.0712", "0.0600"])
        self.assertEqual(pins[3][1:], ["NA"] * 8 + ["0.0000"] * 4)
        _h, ends = tsv(os.path.join(out, "endpoints.tsv"))
        # setup slacks tie (2.4 / 2.4) -> r; hold slacks tie -> r.
        self.assertEqual(ends, [["U1/Y", "1.2000", "3.6000", "2.4000", "1.2000", "-0.3000", "1.5000"]])
        with open(os.path.join(out, "paths.txt")) as f:
            self.assertEqual(f.read(),
                             "U1/Y setup 2.4000 : a(f) -> U1/A(f) -> U1/Y(r)\n"
                             "U1/Y hold 1.5000 : a(r) -> U1/A(r) -> U1/Y(f)\n")

    def test_missing_pins(self):
        raw = os.path.join(self.tmp, "d", "raw")
        os.makedirs(raw)
        raw_from_golden(os.path.join(GOLDEN, "ff2_default"), raw)
        toy = os.path.join(self.tmp, "toy")
        shutil.copytree(os.path.join(GOLDEN, "ff2_default"), toy)
        with open(os.path.join(raw, "pins.tsv")) as f:
            lines = [ln for ln in f if not ln.startswith("U1/A\t")]
        lines.append("extra\tport" + "\tINF" * 12 + "\n")
        with open(os.path.join(raw, "pins.tsv"), "w") as f:
            f.writelines(lines)
        out = os.path.join(self.tmp, "d", "opensta")
        to_golden.convert(raw, out, toy)
        with open(os.path.join(self.tmp, "d", "missing.txt")) as f:
            self.assertEqual(f.read(), "opensta-only pin extra\ntoy-only pin U1/A\n")
        _h, pins = tsv(os.path.join(out, "pins.tsv"))
        self.assertIn(["U1/A"] + ["NA"] * 12, pins)


class CorrelateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.a = os.path.join(self.tmp, "a")
        self.b = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(GOLDEN, "s27"), self.a)
        shutil.copytree(os.path.join(GOLDEN, "s27"), self.b)

    def tearDown(self):
        self._tmp.cleanup()

    def edit(self, fname, pin, col, new):
        path = os.path.join(self.b, fname)
        header, rows = tsv(path)
        k = header.index(col)
        for r in rows:
            if r[0] == pin:
                r[k] = new
        with open(path, "w") as f:
            f.write("\n".join("\t".join(r) for r in [header] + rows) + "\n")

    def correlate(self, *extra):
        r = run([sys.executable, os.path.join("tools", "correlate.py"), self.a, self.b] + list(extra))
        return r.returncode, r.stdout.decode()

    def test_identical(self):
        code, text = self.correlate("--design", os.path.join("data", "s27.v"),
                                    "--lib", os.path.join("data", "toy2.lib"))
        self.assertEqual(code, 0, text)
        self.assertTrue(text.startswith("PASS"))
        self.assertIn("same 7  mismatch 0", text)
        self.assertIn("by cell", text)
        self.assertIn("by level", text)

    def test_within_and_over_tolerance(self):
        self.edit("pins.tsv", "U15/Y", "at_late_r", "4.4405")
        code, text = self.correlate()
        self.assertEqual(code, 0, text)
        self.edit("pins.tsv", "U9/Y", "slew_late_f", "0.9999")
        self.edit("endpoints.tsv", "G17", "setup_slack", "NA")
        code, text = self.correlate()
        self.assertEqual(code, 1, text)
        self.assertTrue(text.startswith("FAIL"))
        top = text.split("largest |d|")[1]
        first = top.splitlines()[1].split()
        self.assertEqual(first[:3], ["pins.tsv", "U9/Y", "slew_late_f"])
        stats = [ln.split() for ln in text.splitlines() if ln.strip().startswith("slew_late_f")]
        self.assertEqual(stats[0][4], "1")            # over tolerance
        setup = [ln.split() for ln in text.splitlines() if ln.strip().startswith("setup_slack")]
        self.assertEqual(setup[0][5], "1")            # one-sided NA

    def test_rows_and_paths(self):
        path = os.path.join(self.b, "paths.txt")
        with open(path) as f:
            lines = f.readlines()
        lines[0] = lines[0].replace("U14/Y(r)", "U14/Y(f)", 1)
        del lines[-1]
        with open(path, "w") as f:
            f.writelines(lines)
        header, rows = tsv(os.path.join(self.b, "pins.tsv"))
        with open(os.path.join(self.b, "pins.tsv"), "w") as f:
            f.write("\n".join("\t".join(r) for r in [header] + rows[1:]) + "\n")
        code, text = self.correlate("--tol", "0.01")
        self.assertEqual(code, 1)
        self.assertIn("path-mismatch FF5/D setup", text)
        self.assertIn("golden-only %s" % rows[0][0], text)
        self.assertIn("same 5  mismatch 1  golden-only 1  actual-only 0", text)


def probe():
    if not os.path.exists(RUN_SH):
        return False
    r = run(["/bin/sh", RUN_SH, "--probe"])
    return r.returncode == 0


@unittest.skipUnless(probe(), "OpenSTA not available (ref/opensta/run.sh --probe failed)")
class OpenStaTests(unittest.TestCase):
    def test_ff2_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "raw")
            r = run(["/bin/sh", RUN_SH, os.path.join(ROOT, "data", "ff2.v"),
                     os.path.join(ROOT, "data", "sdc", "ff2_default.sdc"), raw])
            self.assertEqual(r.returncode, 0, r.stdout.decode())
            toy = os.path.join(tmp, "toy")
            r = run([sys.executable, "-m", "sta_toy", "--lib", os.path.join(ROOT, "data", "toy2.lib"),
                     "--verilog", os.path.join(ROOT, "data", "ff2.v"),
                     "--sdc", os.path.join(ROOT, "data", "sdc", "ff2_default.sdc"), "--dump-tsv", toy])
            self.assertEqual(r.returncode, 0, r.stdout.decode())
            out = os.path.join(tmp, "opensta")
            to_golden.convert(raw, out)
            names = check_golden_dir(self, out)
            toy_names = check_golden_dir(self, toy)
            self.assertEqual(names["pins.tsv"], toy_names["pins.tsv"])
            self.assertEqual(names["endpoints.tsv"], toy_names["endpoints.tsv"])


if __name__ == "__main__":
    unittest.main()
