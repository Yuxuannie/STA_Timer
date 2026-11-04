#!/usr/bin/env python3
"""Compare two golden-format directories (endpoints.tsv, pins.tsv, paths.txt).

    python3 tools/diff_ref.py tests/golden/ff2_default build/ff2_default [--tol 0]

Exit 0 when every cell matches, 1 otherwise.  With --tol 0 (the default,
used in stage P2) numeric cells must be byte-identical.  With --tol T
(stage 2 reference-tool comparisons) numeric cells may differ by at most T;
NA cells, pin names, row sets and path strings must always match exactly.
The same tool is used against hand/oracle golden now and against OpenSTA /
PrimeTime adapters later, so its input format never changes.
"""
import argparse
import os
import sys


def read_tsv(path):
    with open(path) as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    header = lines[0].split("\t")
    rows = {}
    for ln in lines[1:]:
        cells = ln.split("\t")
        rows[cells[0]] = dict(zip(header, cells))
    return header, rows


def read_paths(path):
    out = {}
    with open(path) as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip():
                continue
            key = " ".join(ln.split()[:2])  # "<endpoint> <setup|hold>"
            out[key] = ln
    return out


def cmp_num(a, b, tol):
    if a == b:
        return True
    if a == "NA" or b == "NA":
        return False
    try:
        return abs(float(a) - float(b)) <= tol + 1e-12
    except ValueError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("golden")
    ap.add_argument("actual")
    ap.add_argument("--tol", type=float, default=0.0)
    a = ap.parse_args()
    bad, total, maxd = [], 0, (0.0, "")

    for fname in ("endpoints.tsv", "pins.tsv"):
        gp, apth = os.path.join(a.golden, fname), os.path.join(a.actual, fname)
        if not os.path.exists(apth):
            bad.append("%s: missing" % fname)
            continue
        gh, gr = read_tsv(gp)
        ah, ar = read_tsv(apth)
        if gh != ah:
            bad.append("%s: header differs" % fname)
            continue
        if set(gr) != set(ar):
            bad.append("%s: row set differs: missing %s, extra %s" % (
                fname, sorted(set(gr) - set(ar)), sorted(set(ar) - set(gr))))
        for key in sorted(set(gr) & set(ar)):
            for col in gh[1:]:
                total += 1
                g, x = gr[key][col], ar[key][col]
                if not cmp_num(g, x, a.tol):
                    bad.append("%s: %s %s: golden %s actual %s" % (fname, key, col, g, x))
                try:
                    d = abs(float(g) - float(x))
                    if d > maxd[0]:
                        maxd = (d, "%s %s" % (key, col))
                except ValueError:
                    pass

    gp, apth = os.path.join(a.golden, "paths.txt"), os.path.join(a.actual, "paths.txt")
    if not os.path.exists(apth):
        bad.append("paths.txt: missing")
    else:
        g, x = read_paths(gp), read_paths(apth)
        if set(g) != set(x):
            bad.append("paths.txt: key set differs: missing %s, extra %s" % (
                sorted(set(g) - set(x)), sorted(set(x) - set(g))))
        for key in sorted(set(g) & set(x)):
            total += 1
            gl, xl = g[key], x[key]
            if a.tol > 0:
                # compare the path string exactly, the slack number within tolerance
                gs, xs = gl.split(" : ", 1), xl.split(" : ", 1)
                ok = gs[1] == xs[1] and cmp_num(gs[0].split()[2], xs[0].split()[2], a.tol)
            else:
                ok = gl == xl
            if not ok:
                bad.append("paths.txt: %s:\n    golden %s\n    actual %s" % (key, gl, xl))

    print("compared %d cells; max |delta| %.6f at %s" % (total, maxd[0], maxd[1] or "-"))
    if bad:
        print("%d mismatch(es):" % len(bad))
        for b in bad[:200]:
            print("  " + b)
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
