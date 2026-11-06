#!/usr/bin/env python3
"""Rewrite an OpenSTA raw dump (ref/opensta/run.tcl) in the golden format.

    python3 ref/opensta/to_golden.py RESULTS_DIR OUT_DIR [--toy-pins TOY_DIR]

Writes endpoints.tsv, pins.tsv, paths.txt exactly as docs/contracts/golden_format.md
(fmt4, NA, sorted rows).  Required times come from slack: late RAT = AT + slack_max,
early RAT = AT - slack_min, per rf.  With --toy-pins, pins or endpoints only one
tool has become all-NA rows and are listed in RESULTS_DIR/../missing.txt.
See docs/contracts/reference.md.
"""
import argparse
import math
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

TIE = 1e-9
RAW_COLS = ["name", "kind", "at_max_r", "at_max_f", "at_min_r", "at_min_f",
            "slack_max_r", "slack_max_f", "slack_min_r", "slack_min_f",
            "slew_max_r", "slew_max_f", "slew_min_r", "slew_min_f"]
PINS_HEADER = ["pin", "at_late_r", "at_late_f", "at_early_r", "at_early_f",
               "rat_late_r", "rat_late_f", "rat_early_r", "rat_early_f",
               "slew_late_r", "slew_late_f", "slew_early_r", "slew_early_f"]
END_HEADER = ["pin", "setup_at", "setup_rat", "setup_slack", "hold_at", "hold_rat", "hold_slack"]
EDGE = {"^": "r", "rise": "r", "r": "r", "v": "f", "fall": "f", "f": "f"}


def fmt4(v):
    # p2_semantics.md §11, the one number format of the golden files.
    if v is None:
        return "NA"
    d = Decimal(repr(round(v, 9))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    s = str(d)
    return "0.0000" if s == "-0.0000" else s


def value(text):
    """OpenSTA's text for one number -> float, or None when undefined / infinite."""
    try:
        v = float(text)
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v) or abs(v) >= 1e10:
        return None
    return v


def read_raw_pins(path):
    pins = {}
    with open(path) as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    if lines[0].split("\t") != RAW_COLS:
        raise ValueError("%s: unexpected header %r" % (path, lines[0]))
    for ln in lines[1:]:
        cells = ln.split("\t")
        if len(cells) != len(RAW_COLS):
            raise ValueError("%s: bad row %r" % (path, ln))
        row = dict(zip(RAW_COLS[2:], (value(c) for c in cells[2:])))
        pins[cells[0]] = row
    return pins


def read_raw_paths(path):
    """[(endpoint, check, slack, [(pin, rf)])] in file order."""
    out = []
    with open(path) as f:
        for ln in f:
            parts = ln.split()
            if not parts:
                continue
            if parts[0] == "END":
                _tag, end, check, slack = parts
                if check not in ("setup", "hold"):
                    raise ValueError("%s: bad check %r" % (path, ln))
                out.append((end, check, value(slack), []))
            elif parts[0] == "PT":
                _tag, pin, edge = parts[:3]
                out[-1][3].append((pin, EDGE[edge]))
            else:
                raise ValueError("%s: bad line %r" % (path, ln))
    return out


def sub(a, b):
    return None if a is None or b is None else a - b


def add(a, b):
    return None if a is None or b is None else a + b


def pin_row(raw):
    at = [raw["at_max_r"], raw["at_max_f"], raw["at_min_r"], raw["at_min_f"]]
    rat = [add(at[0], raw["slack_max_r"]), add(at[1], raw["slack_max_f"]),
           sub(at[2], raw["slack_min_r"]), sub(at[3], raw["slack_min_f"])]
    slew = [raw["slew_max_r"], raw["slew_max_f"], raw["slew_min_r"], raw["slew_min_f"]]
    return at + rat + slew


def worst(row, check):
    """(at, rat, slack) of the worst transition, p2_semantics.md §9; ties go to r."""
    if check == "setup":
        cand = [(row[4] if row[4] is None else row[4] - row[0], 0),
                (row[5] if row[5] is None else row[5] - row[1], 1)]
        idx = {0: (0, 4), 1: (1, 5)}
    else:
        cand = [(None if row[2] is None or row[6] is None else row[2] - row[6], 0),
                (None if row[3] is None or row[7] is None else row[3] - row[7], 1)]
        idx = {0: (2, 6), 1: (3, 7)}
    defined = [(s, k) for s, k in cand if s is not None and row[idx[k][0]] is not None]
    if not defined:
        return [None, None, None]
    best = defined[0]
    for s, k in defined[1:]:
        if s < best[0] - TIE:
            best = (s, k)
    a, r = idx[best[1]]
    return [row[a], row[r], best[0]]


def read_names(path):
    with open(path) as f:
        return [ln.split("\t", 1)[0] for ln in list(f)[1:] if ln.strip()]


def convert(results_dir, out_dir, toy_dir=None):
    raw = read_raw_pins(os.path.join(results_dir, "pins.tsv"))
    paths = read_raw_paths(os.path.join(results_dir, "paths.txt"))
    rows = {name: pin_row(r) for name, r in raw.items()}
    ends = sorted(set(end for end, _c, _s, _p in paths))

    missing = []
    if toy_dir is not None:
        toy_pins = set(read_names(os.path.join(toy_dir, "pins.tsv")))
        toy_ends = set(read_names(os.path.join(toy_dir, "endpoints.tsv")))
        for p in sorted(set(rows) - toy_pins):
            missing.append("opensta-only pin %s" % p)
        for p in sorted(toy_pins - set(rows)):
            missing.append("toy-only pin %s" % p)
            rows[p] = [None] * 12
        for p in sorted(set(ends) - toy_ends):
            missing.append("opensta-only endpoint %s" % p)
        for p in sorted(toy_ends - set(ends)):
            missing.append("toy-only endpoint %s" % p)
        ends = sorted(set(ends) | toy_ends)
        with open(os.path.join(os.path.dirname(os.path.abspath(results_dir)), "missing.txt"), "w") as f:
            f.write("".join(m + "\n" for m in missing))

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "pins.tsv"), "w", newline="") as f:
        f.write("\t".join(PINS_HEADER) + "\n")
        for name in sorted(rows):
            f.write("\t".join([name] + [fmt4(v) for v in rows[name]]) + "\n")
    with open(os.path.join(out_dir, "endpoints.tsv"), "w", newline="") as f:
        f.write("\t".join(END_HEADER) + "\n")
        for name in ends:
            row = rows.get(name, [None] * 12)
            cells = worst(row, "setup") + worst(row, "hold")
            f.write("\t".join([name] + [fmt4(v) for v in cells]) + "\n")
    order = {"setup": 0, "hold": 1}
    with open(os.path.join(out_dir, "paths.txt"), "w", newline="") as f:
        for end, check, slack, pts in sorted(paths, key=lambda p: (p[0], order[p[1]])):
            if slack is None or not pts:
                continue
            seq = " -> ".join("%s(%s)" % p for p in pts)
            f.write("%s %s %s : %s\n" % (end, check, fmt4(slack), seq))
    return missing


def main(argv=None):
    ap = argparse.ArgumentParser(description="OpenSTA raw dump -> golden format")
    ap.add_argument("results_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--toy-pins", metavar="TOY_DIR")
    args = ap.parse_args(argv)
    try:
        missing = convert(args.results_dir, args.out_dir, args.toy_pins)
    except (OSError, ValueError, KeyError, IndexError) as e:
        sys.stderr.write("error: %s\n" % e)
        return 1
    if missing:
        sys.stderr.write("%d pins / endpoints on one side only (missing.txt)\n" % len(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
