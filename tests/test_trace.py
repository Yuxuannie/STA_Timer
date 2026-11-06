import os
import re
import unittest

from sta_toy import design, lookup, timer, trace, tsv
from test_cli import DESIGNS, ROOT, TempDirTest, run_cli
from test_check_timing import GoldenDiff

GOLDEN = os.path.join(ROOT, "tests", "golden")
TRACE_GOLDEN = os.path.join(GOLDEN, "trace", "ff2_default_FF2_D.txt")
ARGS = ["--lib", "data/toy2.lib", "--verilog", "data/ff2.v", "--sdc", "data/sdc/ff2_default.sdc"]


def timed(verilog, scenario, log=None):
    lib, netlist, linked = design.load([os.path.join(ROOT, "data", "toy2.lib")],
                                       os.path.join(ROOT, "data", verilog))
    return design.timed(lib, netlist, linked, os.path.join(ROOT, "data", "sdc", scenario),
                        log=log)


def read_golden(name):
    """pins.tsv as {pin: {column: text}}, endpoints.tsv rows, paths.txt as {(pin, kind): text}."""
    def table(path):
        with open(path) as f:
            rows = [line.rstrip("\n").split("\t") for line in f]
        return {r[0]: dict(zip(rows[0], r)) for r in rows[1:]}
    pins = table(os.path.join(GOLDEN, name, "pins.tsv"))
    ends = table(os.path.join(GOLDEN, name, "endpoints.tsv"))
    paths = {}
    with open(os.path.join(GOLDEN, name, "paths.txt")) as f:
        for line in f:
            head, path = line.rstrip("\n").split(" : ")
            pin, kind, _ = head.split(" ")
            paths[(pin, kind)] = path
    return pins, ends, paths


def traces():
    """(golden name, endpoint, trace text) for every endpoint of the eight designs."""
    for name, verilog, scenario in DESIGNS:
        names = [e.name for e in timed(verilog, scenario).endpoints]
        for e in names:
            log = []
            g = timed(verilog, scenario, log)
            yield name, e, trace.trace(g, e, log, scenario)


SECTION = re.compile(r"^(forward|check|backward|slack|path)$")
NUM = r"(-?[0-9]+\.[0-9]{4}|NA)"
FWD = re.compile(r"^(\S+) (late|early) ([rf]) at %s slew %s( source (input|clock))?$" % (NUM, NUM))
FWD_CAND = re.compile(r"^  [* ] (\S+)\(([rf])\) %s \+ %s = %s slew %s$" % (NUM, NUM, NUM, NUM))
CHECK_D = re.compile(r"^(\S+) (setup|hold) ([rf]) rat %s = ck_at %s \+ .*; t at d_slew %s "
                     r"ck_slew %s \((\S+)\)$" % (NUM, NUM, NUM, NUM))
CHECK_PO = re.compile(r"^(\S+) (setup|hold) ([rf]) rat %s = .*output_delay %s$" % (NUM, NUM))
BWD = re.compile(r"^(\S+) (late|early) ([rf]) rat %s$" % NUM)
BWD_CAND = re.compile(r"^  [* ] (\S+)\(([rf])\) %s - %s = %s$" % (NUM, NUM, NUM))
SLACK = re.compile(r"^(\S+) (setup|hold) ([rf]) at %s rat %s slack %s$" % (NUM, NUM, NUM))
PATH = re.compile(r"^(setup|hold) : (.*)$")
MODE = {"setup": "late", "hold": "early"}


class TraceGoldenTests(GoldenDiff):
    """R36: the ff2_default FF2/D trace, byte-exact (hand-reviewed against pins.tsv / paths.txt)."""

    def test_golden(self):
        result = run_cli(*(ARGS + ["--trace", "FF2/D"]))
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        with open(TRACE_GOLDEN, "rb") as f:
            self.assertEqual(result.stdout, f.read())

    def test_not_an_endpoint(self):
        out = os.path.join(self.tmp, "out")
        for pin in ("U2/Y", "nope"):
            result = run_cli(*(ARGS + ["--trace", pin, "--dump-tsv", out]))
            self.assertOneLineError(result, "^error: --trace %s is not an endpoint\n$" % re.escape(pin))
            self.assertFalse(os.path.exists(out))

    def test_needs_sdc(self):
        result = run_cli("--lib", "data/toy2.lib", "--verilog", "data/ff2.v", "--trace", "FF2/D")
        self.assertOneLineError(result, "^error: --trace needs --sdc\n$")

    def test_log_leaves_goldens_byte_exact(self):
        # The run that collects the log writes the same P2 files.
        out = os.path.join(self.tmp, "out")
        result = run_cli(*(ARGS + ["--trace", "FF2/D", "--dump-tsv", out]))
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertGolden(out, "ff2_default")
        for name, verilog, scenario in DESIGNS:
            with self.subTest(design=name):
                self.assertEqual(tsv.tables(timed(verilog, scenario, [])),
                                 tsv.tables(timed(verilog, scenario)))

    def test_stdout_order(self):
        both = run_cli(*(ARGS + ["--trace", "FF2/D", "--check-timing", "--report-summary"]))
        parts = [run_cli(*(ARGS + [o])).stdout for o in ("--report-summary", "--check-timing")]
        with open(TRACE_GOLDEN, "rb") as f:
            self.assertEqual(both.stdout, b"".join(parts) + f.read())


class TraceCrossCheckTests(unittest.TestCase):
    """R36 / section 6: every AT / RAT / slack / slew in a trace equals the P2 golden value at
    that pin, mode and rf; every path equals paths.txt; sources come before their users."""

    def cross_check(self, name, endpoint, text):
        pins, ends, paths = read_golden(name)

        def eq(value, pin, column):
            self.assertEqual(value, pins[pin][column], "%s %s %s" % (endpoint, pin, column))

        section, mode, header = None, None, None
        seen = set()
        for line in text.splitlines()[2:]:
            if SECTION.match(line):
                section = line
                continue
            if section == "forward":
                m = FWD.match(line)
                if m:
                    pin, mode, rf, at, slew = m.group(1, 2, 3, 4, 5)
                    eq(at, pin, "at_%s_%s" % (mode, rf))
                    eq(slew, pin, "slew_%s_%s" % (mode, rf))
                    seen.add(pin)
                    continue
                m = FWD_CAND.match(line)
                self.assertTrue(m, line)
                eq(m.group(3), m.group(1), "at_%s_%s" % (mode, m.group(2)))
                self.assertIn(m.group(1), seen, "%s: source after its user" % line)
            elif section == "check":
                m = CHECK_D.match(line)
                if m:
                    pin, kind, rf, rat, ck_at, d_slew, ck_slew, ck = m.groups()
                    mode = MODE[kind]
                    eq(rat, pin, "rat_%s_%s" % (mode, rf))
                    eq(ck_at, ck, "at_%s_r" % mode)
                    eq(d_slew, pin, "slew_%s_%s" % (mode, rf))
                    eq(ck_slew, ck, "slew_%s_r" % mode)
                else:
                    m = CHECK_PO.match(line)
                    self.assertTrue(m, line)
                    eq(m.group(4), m.group(1), "rat_%s_%s" % (MODE[m.group(2)], m.group(3)))
            elif section == "backward":
                m = BWD.match(line)
                if m:
                    pin, mode, rf, rat = m.groups()
                    eq(rat, pin, "rat_%s_%s" % (mode, rf))
                    continue
                m = BWD_CAND.match(line)
                self.assertTrue(m, line)
                eq(m.group(3), m.group(1), "rat_%s_%s" % (mode, m.group(2)))
            elif section == "slack":
                m = SLACK.match(line)
                self.assertTrue(m, line)
                pin, kind, rf, at, rat, slack = m.groups()
                mode = MODE[kind]
                eq(at, pin, "at_%s_%s" % (mode, rf))
                eq(rat, pin, "rat_%s_%s" % (mode, rf))
                row = ends[pin]
                if slack == "NA":
                    self.assertTrue("NA" in (at, rat))
                elif (row[kind + "_at"], row[kind + "_rat"]) == (at, rat):
                    self.assertEqual(slack, row[kind + "_slack"])
                else:
                    # The other transition: not in a golden file; within fmt4 rounding.
                    sign = 1 if kind == "setup" else -1
                    self.assertAlmostEqual(float(slack), sign * (float(rat) - float(at)), delta=1.5e-4)
            else:
                m = PATH.match(line)
                self.assertTrue(m, line)
                self.assertEqual(m.group(2), paths[(endpoint, m.group(1))])
        self.assertEqual(section, "path")

    def test_golden_file(self):
        with open(TRACE_GOLDEN) as f:
            self.cross_check("ff2_default", "FF2/D", f.read())

    def test_every_endpoint(self):
        count = 0
        for name, endpoint, text in traces():
            with self.subTest(design=name, endpoint=endpoint):
                self.cross_check(name, endpoint, text)
                count += 1
        self.assertGreater(count, 20)


class FormatterTests(unittest.TestCase):
    """R36: the formatter prints only the log; it never looks anything up."""

    def test_formatter_computes_nothing(self):
        log = []
        g = timed("ff2.v", "ff2_default.sdc", log)
        e = trace.collect(g, "FF2/D", log)
        cone = {n.name for n in trace.bundle._cone(e, float("inf"))}

        def fail(*args):
            raise AssertionError("called during formatting")
        saved = (lookup.lookup, lookup.lookup_detail, timer.arc_delay, timer.slack)
        lookup.lookup = lookup.lookup_detail = timer.arc_delay = timer.slack = fail
        try:
            text = trace.format_trace(log, "FF2/D", cone, "ff2", "ff2_default.sdc")
        finally:
            lookup.lookup, lookup.lookup_detail, timer.arc_delay, timer.slack = saved
        with open(TRACE_GOLDEN) as f:
            self.assertEqual(text, f.read())

    def test_log_entries_are_engine_values(self):
        log = []
        g = timed("s27.v", "s27.sdc", log)
        for x in log:
            n = g.by_name[x["pin"]]
            if x["phase"] == "forward":
                self.assertIs(x["at"], n.at[x["mode"]][x["rf"]])
                if x["candidates"]:
                    self.assertEqual(x["candidates"][x["winner"]]["value"], x["at"])
            elif x["phase"] == "backward":
                self.assertIs(x["rat"], n.rat[x["mode"]][x["rf"]])
                self.assertEqual(x["candidates"][x["winner"]]["value"], x["rat"])
            elif x["phase"] == "check":
                self.assertIs(x["rat"], n.rat[MODE[x["kind"]]][x["rf"]])
        phases = [x["phase"] for x in log]
        self.assertEqual(phases, sorted(phases, key=["forward", "check", "backward"].index))


if __name__ == "__main__":
    unittest.main()
