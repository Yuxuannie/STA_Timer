"""R38: tools/bench2v.py and the s1423 design."""
import itertools
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import bench2v  # noqa: E402

TOY2_LIB = os.path.join(ROOT, "data", "toy2.lib")

# s27 from the public ISCAS-89 description (4 inputs, 1 output, 3 DFFs, 10 gates).
S27_BENCH = """\
# s27
INPUT(G0)
INPUT(G1)
INPUT(G2)
INPUT(G3)
OUTPUT(G17)
G5 = DFF(G10)
G6 = DFF(G11)
G7 = DFF(G13)
G14 = NOT(G0)
G17 = NOT(G11)
G8 = AND(G14, G6)
G15 = OR(G12, G8)
G16 = OR(G3, G8)
G9 = NAND(G16, G15)
G10 = NOR(G14, G11)
G11 = NOR(G5, G9)
G12 = NOR(G1, G7)
G13 = NOR(G2, G12)
"""

FUNC = {"INV": lambda a: not a, "BUF": lambda a: a,
        "AND2": lambda a, b: a and b, "OR2": lambda a, b: a or b,
        "NAND2": lambda a, b: not (a and b), "NOR2": lambda a, b: not (a or b)}
BENCH = {"AND": all, "OR": any,
         "NAND": lambda v: not all(v), "NOR": lambda v: not any(v),
         "XOR": lambda v: v[0] != v[1], "XNOR": lambda v: v[0] == v[1],
         "NOT": lambda v: not v[0], "BUFF": lambda v: v[0]}

INST = re.compile(r"^\s+(\w+)\s+(\S+)\s*\((.*)\);$")


def run(args, **kw):
    return subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)


def instances(verilog):
    out = []
    for line in verilog.splitlines():
        m = INST.match(line)
        if m:
            pins = dict(re.findall(r"\.(\w+)\(([^)]*)\)", m.group(3)))
            out.append((m.group(1), m.group(2), pins))
    return out


def evaluate(verilog, values):
    """Evaluate a combinational netlist of toy2.lib cells; returns the net values."""
    nets = dict(values)
    pending = instances(verilog)
    while pending:
        rest = []
        for cell, name, pins in pending:
            ins = [pins[p] for p in ("A", "B") if p in pins]
            if all(n in nets for n in ins):
                nets[pins["Y"]] = FUNC[cell](*[nets[n] for n in ins])
            else:
                rest.append((cell, name, pins))
        assert len(rest) < len(pending), "netlist does not settle"
        pending = rest
    return nets


class Bench2vTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_s27_matches_golden(self):
        # Instance names come out as in data/s27.v (U14, FF5, ...), so all three
        # files are compared, not only endpoints.tsv.
        bench = os.path.join(self.tmp, "s27.bench")
        with open(bench, "w") as f:
            f.write(S27_BENCH)
        v = os.path.join(self.tmp, "s27.v")
        r = run([sys.executable, os.path.join("tools", "bench2v.py"), bench, v, "--top", "s27"])
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(r.stdout.decode(),
                         "AND2   1\nDFF    3\nINV    2\nNAND2  1\nNOR2   4\nOR2    2\ntotal  13\n")
        with open(v) as f:
            names = sorted(name for _c, name, _p in instances(f.read()))
        with open(os.path.join(ROOT, "data", "s27.v")) as f:
            self.assertEqual(names, sorted(name for _c, name, _p in instances(f.read())))
        out = os.path.join(self.tmp, "out")
        r = run([sys.executable, "-m", "sta_toy", "--lib", TOY2_LIB, "--verilog", v,
                 "--sdc", os.path.join(ROOT, "data", "sdc", "s27.sdc"), "--dump-tsv", out])
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))
        d = run([sys.executable, os.path.join("tools", "diff_ref.py"),
                 os.path.join(ROOT, "tests", "golden", "s27"), out, "--tol", "0"])
        self.assertEqual(d.returncode, 0, d.stdout.decode())

    def test_decompositions_are_equivalent(self):
        for kind, n in [("AND", 3), ("OR", 4), ("NAND", 3), ("NAND", 4), ("NOR", 4),
                        ("NOR", 5), ("AND", 1), ("NAND", 1), ("XOR", 2), ("XNOR", 2),
                        ("NOT", 1), ("BUFF", 1), ("AND", 2), ("NOR", 2)]:
            ins = ["I%d" % i for i in range(n)]
            text = "".join("INPUT(%s)\n" % i for i in ins)
            text += "OUTPUT(Z)\nZ = %s(%s)\n" % (kind, ", ".join(ins))
            verilog, _counts = bench2v.convert(text, "t")
            for bits in itertools.product([False, True], repeat=n):
                with self.subTest(kind=kind, n=n, bits=bits):
                    nets = evaluate(verilog, zip(ins, bits))
                    self.assertEqual(nets["Z"], BENCH[kind](list(bits)))

    def test_names(self):
        text = "INPUT(a)\nINPUT(b)\nINPUT(c)\nOUTPUT(G9)\nG9 = NAND(a, b, c)\nq = DFF(G9)\n"
        verilog, counts = bench2v.convert(text, "t")
        self.assertEqual(counts, {"AND2": 1, "NAND2": 1, "DFF": 1})
        self.assertEqual([(c, n) for c, n, _p in instances(verilog)],
                         [("AND2", "U9_t0"), ("NAND2", "U9"), ("DFF", "FFq")])
        self.assertIn("  wire G9_t0;\n", verilog)
        self.assertIn("  input clk;\n", verilog)
        self.assertIn("  DFF FFq (.CK(clk), .D(G9), .Q(q));\n", verilog)

    def test_errors(self):
        for text, msg in [("INPUT(a)\nOUTPUT(z)\nz = MUX(a, a)\n", "unsupported gate kind MUX"),
                          ("INPUT(a)\nOUTPUT(z)\nz = AND(a, w)\n", "net w is never driven"),
                          ("INPUT(a)\nOUTPUT(z)\nz = NOT(a)\nz = NOT(a)\n", "two drivers"),
                          ("INPUT(clk)\nOUTPUT(z)\nz = NOT(clk)\n", "reserved for the clock"),
                          ("INPUT(a)\nOUTPUT(a)\n", "is an INPUT"),
                          ("INPUT(a)\nz == NOT(a)\n", "cannot parse line")]:
            with self.subTest(msg=msg):
                with self.assertRaisesRegex(bench2v.BenchError, msg):
                    bench2v.convert(text, "t")


class S1423Tests(unittest.TestCase):
    """R38: s1423 is checked in as converted; the engine runs on it and writes three
    well-formed files (no value test: values are R39's job)."""

    def test_checked_in_netlist_is_the_conversion(self):
        with open(os.path.join(ROOT, "data", "bench", "s1423.bench")) as f:
            verilog, counts = bench2v.convert(f.read(), "s1423", "data/bench/s1423.bench")
        with open(os.path.join(ROOT, "data", "s1423.v")) as f:
            self.assertEqual(f.read(), verilog)
        self.assertEqual(counts, {"AND2": 206, "DFF": 74, "INV": 167, "NAND2": 64,
                                  "NOR2": 92, "OR2": 145})

    def test_engine_writes_three_well_formed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run([sys.executable, "-m", "sta_toy", "--lib", TOY2_LIB,
                     "--verilog", os.path.join(ROOT, "data", "s1423.v"),
                     "--sdc", os.path.join(ROOT, "data", "sdc", "s1423.sdc"), "--dump-tsv", tmp])
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))
            check_golden_dir(self, tmp)


NUM = re.compile(r"^(NA|-?\d+\.\d{4})$")
HEADERS = {
    "endpoints.tsv": "pin\tsetup_at\tsetup_rat\tsetup_slack\thold_at\thold_rat\thold_slack",
    "pins.tsv": "pin\tat_late_r\tat_late_f\tat_early_r\tat_early_f\trat_late_r\trat_late_f"
                "\trat_early_r\trat_early_f\tslew_late_r\tslew_late_f\tslew_early_r\tslew_early_f",
}
PATH = re.compile(r"^(\S+) (setup|hold) (-?\d+\.\d{4}) : (\S+\([rf]\))( -> \S+\([rf]\))*$")


def check_golden_dir(test, d):
    """Assert that d holds the three files of golden_format.md, well formed."""
    names = {}
    for fname, header in HEADERS.items():
        with open(os.path.join(d, fname), newline="") as f:
            text = f.read()
        test.assertTrue(text.endswith("\n") and "\r" not in text, fname)
        lines = text[:-1].split("\n")
        test.assertEqual(lines[0], header, fname)
        ncol = header.count("\t") + 1
        pins = []
        for ln in lines[1:]:
            cells = ln.split("\t")
            test.assertEqual(len(cells), ncol, ln)
            for c in cells[1:]:
                test.assertRegex(c, NUM, ln)
            pins.append(cells[0])
        test.assertEqual(pins, sorted(pins), fname)
        test.assertEqual(len(pins), len(set(pins)), fname)
        names[fname] = pins
    with open(os.path.join(d, "paths.txt"), newline="") as f:
        text = f.read()
    keys = []
    for ln in text.splitlines():
        m = PATH.match(ln)
        test.assertTrue(m, ln)
        test.assertIn(m.group(1), names["endpoints.tsv"])
        test.assertTrue(ln.endswith("-> %s(r)" % m.group(1)) or ln.endswith("-> %s(f)" % m.group(1)), ln)
        keys.append((m.group(1), m.group(2) == "hold"))
    test.assertEqual(keys, sorted(keys))
    return names


if __name__ == "__main__":
    unittest.main()
