import os
import unittest

from sta_toy import paths, report
from test_paths import DESIGNS, ROOT, golden_rows, timed

GOLDEN = os.path.join(ROOT, "tests", "golden", "reports")


def golden(name):
    with open(os.path.join(GOLDEN, name), encoding="utf-8", newline="") as f:
        return f.read()


def path_obj(g, endpoint, check, pid="p1"):
    return paths.path_json(paths.worst_path(g.by_name[endpoint], check), g.sdc, pid)


class GoldenReportTests(unittest.TestCase):
    """R23: byte-exact against the hand-written blocks of tests/golden/reports/."""

    def test_ff2_default_setup_and_hold(self):
        g = timed("ff2_default", "ff2")
        self.assertEqual(report.format_path(path_obj(g, "FF2/D", "setup")),
                         golden("ff2_default_FF2_D_max.txt"))
        self.assertEqual(report.format_path(path_obj(g, "FF2/D", "hold")),
                         golden("ff2_default_FF2_D_min.txt"))

    def test_inv2_port_endpoint(self):
        p = path_obj(timed("inv2", "inv2"), "y", "setup")
        self.assertEqual(report.format_path(p), golden("inv2_y_max.txt"))
        self.assertEqual(report.format_path(p, transition=True, capacitance=True),
                         golden("inv2_y_max_cap_trans.txt"))

    def test_report_timing_joins_blocks(self):
        g = timed("ff2_default", "ff2")
        objs = [path_obj(g, "FF2/D", "setup", "p1"), path_obj(g, "FF2/D", "hold", "p2")]
        self.assertEqual(report.report_timing(objs),
                         golden("ff2_default_FF2_D_max.txt") + "\n" + golden("ff2_default_FF2_D_min.txt"))
        self.assertEqual(report.report_timing([]), "No paths.\n")

    def test_violated_label(self):
        for scenario, check in (("ff2_setupviol", "setup"), ("ff2_holdviol", "hold")):
            text = report.format_path(path_obj(timed(scenario, "ff2"), "FF2/D", check))
            last = text.splitlines()[-1]
            self.assertEqual(last.split()[:2], ["slack", "(VIOLATED)"], scenario)
            self.assertEqual(last.split()[-1], "-0.3000" if check == "setup" else "-0.6000")


class GoldenCrossCheckTests(unittest.TestCase):
    """R23: every data row's Path against pins.tsv, required time and slack against
    endpoints.tsv, for every endpoint and check of the eight designs."""

    def test_against_golden_tsv(self):
        for scenario, netlist in DESIGNS:
            g = timed(scenario, netlist)
            pins = {r["pin"]: r for r in golden_rows(scenario, "pins.tsv")}
            with open(os.path.join(ROOT, "tests", "golden", scenario, "paths.txt")) as f:
                chains = {tuple(l.split()[:2]): l.split(" : ")[1] for l in f.read().splitlines()}
            for row in golden_rows(scenario, "endpoints.tsv"):
                for check, mode in (("setup", "late"), ("hold", "early")):
                    where = (scenario, row["pin"], check)
                    worst = paths.worst_path(g.by_name[row["pin"]], check)
                    if row[check + "_slack"] == "NA":
                        self.assertIsNone(worst, where)
                        continue
                    lines = report.format_path(paths.path_json(worst, g.sdc, "p1")).splitlines()
                    end = lines.index([l for l in lines if l.startswith("data arrival time")][0])
                    chain = []
                    for line in lines[9:end]:  # header block (7 lines) and the two launch rows
                        pin = line[:40].split(" (")[0]
                        _, path, rf = line[40:].split()
                        self.assertEqual(path, pins[pin]["at_%s_%s" % (mode, rf)], where + (pin,))
                        chain.append("%s(%s)" % (pin, rf))
                    self.assertEqual(" -> ".join(chain), chains[(row["pin"], check)], where)
                    self.assertEqual(lines[end].split()[-1], row[check + "_at"], where)
                    required = [l for l in lines if l.startswith("data required time")][0]
                    self.assertEqual(required.split()[-1], row[check + "_rat"], where)
                    label = "(VIOLATED)" if row[check + "_slack"].startswith("-") else "(MET)"
                    self.assertEqual(lines[-1].split()[1:], [label, row[check + "_slack"]], where)


class SummaryTextTests(unittest.TestCase):
    """R24: the --report-summary layout of report_p3.md §5."""

    def test_s27(self):
        # golden endpoints.tsv: setup min 0.3706 (G17), no negative slack; hold min 0.9600
        # (FF7/D), G17 hold NA.
        self.assertEqual(report.format_summary(paths.summary(timed("s27", "s27"))),
                         "check          wns       tns   nvp\n"
                         "setup       0.3706    0.0000     0\n"
                         "hold        0.9600    0.0000     0\n")

    def test_violations_and_na(self):
        # ff2_setupviol golden: setup slacks 2.7, -0.3, 1.0; hold 0.9, 2.9, 1.5.
        self.assertEqual(report.format_summary(paths.summary(timed("ff2_setupviol", "ff2"))),
                         "check          wns       tns   nvp\n"
                         "setup      -0.3000   -0.3000     1\n"
                         "hold        0.9000    0.0000     0\n")
        none = {"wns": None, "tns": 0.0, "nvp": 0}
        self.assertEqual(report.format_summary({"setup": none, "hold": none}).splitlines()[1],
                         "setup           NA    0.0000     0")


if __name__ == "__main__":
    unittest.main()
