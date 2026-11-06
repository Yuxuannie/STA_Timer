#!/usr/bin/env python3
"""Correlate two golden-format directories (endpoints.tsv, pins.tsv, paths.txt).

    python3 tools/correlate.py GOLDEN_DIR ACTUAL_DIR [--tol 0.001] [--design V --lib L]

GOLDEN_DIR is the reference.  Beyond pass / fail (exit 0 / 1) it prints, per
column, count / max|d| / mean|d| / over-tolerance / one-sided NA; the 20
largest |d|; pins only on one side; path sequence mismatches; and with
--design / --lib the mean |d| of pins.tsv grouped by cell type and by logic
level.  See docs/contracts/reference.md.  Does not import sta_toy.
"""
import argparse
import os
import re
import sys

TOP = 20


def read_tsv(path):
    with open(path) as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    header = lines[0].split("\t")
    rows = {}
    for ln in lines[1:]:
        cells = ln.split("\t")
        rows[cells[0]] = cells[1:]
    return header, rows


def num(cell):
    if cell == "NA":
        return None
    return float(cell)


def read_paths(path):
    """{(endpoint, check): (slack, [node(rf), ...])}"""
    out = {}
    with open(path) as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip():
                continue
            head, _, seq = ln.partition(" : ")
            end, check, slack = head.split()
            out[(end, check)] = (float(slack), seq.split(" -> "))
    return out


class Stats:
    def __init__(self):
        self.count = 0
        self.max = 0.0
        self.sum = 0.0
        self.over = 0
        self.na = 0


def compare_tsv(fname, gold, act, tol, deltas, pin_deltas):
    header, grows = gold
    _h2, arows = act
    cols = header[1:]
    stats = [Stats() for _ in cols]
    fails = 0
    for pin in sorted(set(grows) & set(arows)):
        for k, col in enumerate(cols):
            g, a = num(grows[pin][k]), num(arows[pin][k])
            st = stats[k]
            if g is None and a is None:
                continue
            if g is None or a is None:
                st.na += 1
                fails += 1
                continue
            d = a - g
            ad = abs(d)
            st.count += 1
            st.sum += ad
            st.max = max(st.max, ad)
            if ad > tol + 1e-9:
                st.over += 1
                fails += 1
            deltas.append((ad, fname, pin, col, grows[pin][k], arows[pin][k], d))
            if pin_deltas is not None:
                pin_deltas.setdefault(pin, []).append(ad)
    return cols, stats, fails


def print_stats(fname, cols, stats):
    print("\n%s" % fname)
    print("  %-14s %7s %10s %10s %6s %6s" % ("column", "count", "max|d|", "mean|d|", "over", "na"))
    for col, st in zip(cols, stats):
        mean = st.sum / st.count if st.count else 0.0
        print("  %-14s %7d %10.4f %10.4f %6d %6d" % (col, st.count, st.max, mean, st.over, st.na))


# ---------- sources: Verilog and Liberty, just enough for cell types and levels

def read_verilog(path):
    """Returns (inputs, outputs, instances); instances: {name: (cell, {pin: net})}."""
    with open(path) as f:
        text = re.sub(r"//[^\n]*", "", f.read())
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    inputs, outputs, insts = [], [], {}
    for stmt in text.split(";"):
        stmt = stmt.strip()
        m = re.match(r"^(input|output)\s+(.*)$", stmt, re.S)
        if m:
            names = [n.strip() for n in m.group(2).split(",") if n.strip()]
            (inputs if m.group(1) == "input" else outputs).extend(names)
            continue
        m = re.match(r"^(\w+)\s+(\S+)\s*\((.*)\)$", stmt, re.S)
        if m and m.group(1) not in ("module", "wire"):
            insts[m.group(2)] = (m.group(1),
                                 dict(re.findall(r"\.(\w+)\s*\(\s*([^)\s]*)\s*\)", m.group(3))))
    return inputs, outputs, insts


def liberty_groups(text):
    """Tiny Liberty reader: [(kind, name, body, start, end)] for the top-level groups of text."""
    out = []
    pos = 0
    pat = re.compile(r"(\w+)\s*\(([^)]*)\)\s*\{")
    while True:
        m = pat.search(text, pos)
        if not m:
            return out
        depth, i = 1, m.end()
        while depth and i < len(text):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        out.append((m.group(1), m.group(2).strip().strip('"'), text[m.end():i - 1], m.start(), i))
        pos = i


def read_liberty(path):
    """{cell: {"clock": set(pins), "out": {pin: set(related_pins)}}}"""
    with open(path) as f:
        text = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
    lib = liberty_groups(text)
    cells = {}
    for _k, _n, body, _s, _e in lib:
        for kind, cname, cbody, _s, _e in liberty_groups(body):
            if kind != "cell":
                continue
            info = {"clock": set(), "out": {}}
            for pkind, pnames, pbody, _s, _e in liberty_groups(cbody):
                if pkind != "pin":
                    continue
                inner = liberty_groups(pbody)
                own, pos = [], 0
                for _gk, _gn, _gb, start, end in inner:
                    own.append(pbody[pos:start])
                    pos = end
                own = "".join(own) + pbody[pos:]
                for pname in [n.strip().strip('"') for n in pnames.split(",")]:
                    if re.search(r"\bclock\s*:\s*true\b", own):
                        info["clock"].add(pname)
                    if re.search(r"\bdirection\s*:\s*output\b", own):
                        rel = set()
                        for tkind, _t, tbody, _s2, _e2 in inner:
                            if tkind == "timing":
                                m = re.search(r'related_pin\s*:\s*"?([^";\s]+)', tbody)
                                if m:
                                    rel.add(m.group(1))
                        info["out"][pname] = rel
            cells[cname] = info
    return cells


def classify(verilog_path, lib_path):
    """Returns ({node: cell type}, {node: level or '?'})."""
    inputs, outputs, insts = read_verilog(verilog_path)
    cells = read_liberty(lib_path)
    ctype, driver, level = {}, {}, {}
    for p in inputs + outputs:
        ctype[p] = "port"
    for p in inputs:
        driver[p] = p
        level[p] = 0
    for name, (cell, conns) in insts.items():
        info = cells.get(cell, {"clock": set(), "out": {}})
        for pin, net in conns.items():
            node = "%s/%s" % (name, pin)
            ctype[node] = cell
            if pin in info["out"]:
                driver[net] = node
            elif pin in info["clock"]:
                level[node] = 0

    def lev(node, stack=()):
        if node in level:
            return level[node]
        if node in stack:
            return "?"
        stack = stack + (node,)
        if "/" not in node:                      # output port
            src = driver.get(node)
            v = "?" if src is None or src == node else lev(src, stack)
        else:
            inst, pin = node.rsplit("/", 1)
            cell, conns = insts[inst]
            info = cells.get(cell)
            if info is None:
                v = "?"
            elif pin in info["out"]:
                ins = [lev("%s/%s" % (inst, r), stack) for r in sorted(info["out"][pin])
                       if r in conns]
                v = "?" if not ins or "?" in ins else 1 + max(ins)
            else:
                src = driver.get(conns[pin])
                v = "?" if src is None else lev(src, stack)
        level[node] = v
        return v

    for node in list(ctype):
        lev(node)
    return ctype, level


def print_groups(title, groups):
    print("\nmean |d| of pins.tsv by %s" % title)
    print("  %-10s %7s %10s %10s" % (title, "cells", "mean|d|", "max|d|"))

    def key(k):
        return (isinstance(k, str), k if not isinstance(k, str) else 0, str(k))
    for k in sorted(groups, key=key):
        v = groups[k]
        print("  %-10s %7d %10.4f %10.4f" % (k, len(v), sum(v) / len(v), max(v)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Correlate two golden-format directories.")
    ap.add_argument("golden")
    ap.add_argument("actual")
    ap.add_argument("--tol", type=float, default=0.001)
    ap.add_argument("--design")
    ap.add_argument("--lib")
    args = ap.parse_args(argv)
    if bool(args.design) != bool(args.lib):
        ap.error("--design and --lib go together")

    deltas, pin_deltas = [], {}
    fails, row_fails = 0, 0
    only = []
    blocks = []
    for fname in ("pins.tsv", "endpoints.tsv"):
        gold = read_tsv(os.path.join(args.golden, fname))
        act = read_tsv(os.path.join(args.actual, fname))
        if gold[0] != act[0]:
            print("FAIL: %s headers differ" % fname)
            return 1
        cols, stats, f = compare_tsv(fname, gold, act, args.tol, deltas,
                                     pin_deltas if fname == "pins.tsv" else None)
        fails += f
        g_only = sorted(set(gold[1]) - set(act[1]))
        a_only = sorted(set(act[1]) - set(gold[1]))
        row_fails += len(g_only) + len(a_only)
        only.append((fname, g_only, a_only))
        blocks.append((fname, cols, stats))

    gp = read_paths(os.path.join(args.golden, "paths.txt"))
    ap_ = read_paths(os.path.join(args.actual, "paths.txt"))
    same, mismatch, slack_over = [], [], 0
    for key in sorted(set(gp) & set(ap_)):
        (gs, gseq), (as_, aseq) = gp[key], ap_[key]
        if gseq == aseq:
            same.append(key)
        else:
            mismatch.append(key)
        if abs(as_ - gs) > args.tol + 1e-9:
            slack_over += 1
    g_missing = sorted(set(gp) - set(ap_))
    a_extra = sorted(set(ap_) - set(gp))
    path_fails = len(mismatch) + len(g_missing) + len(a_extra) + slack_over

    ok = fails == 0 and row_fails == 0 and path_fails == 0
    print("%s  tol %g  cells over/NA %d  rows only one side %d  paths bad %d"
          % ("PASS" if ok else "FAIL", args.tol, fails, row_fails, path_fails))
    for fname, cols, stats in blocks:
        print_stats(fname, cols, stats)

    print("\nlargest |d| (top %d)" % TOP)
    deltas.sort(key=lambda t: (-t[0], t[1], t[2], t[3]))
    for ad, fname, pin, col, g, a, d in deltas[:TOP]:
        if ad == 0:
            break
        print("  %-13s %-16s %-13s golden %10s actual %10s d %+.4f" % (fname, pin, col, g, a, d))

    for fname, g_only, a_only in only:
        print("\n%s: %d only in golden, %d only in actual" % (fname, len(g_only), len(a_only)))
        for p in g_only[:TOP]:
            print("  golden-only %s" % p)
        for p in a_only[:TOP]:
            print("  actual-only %s" % p)

    print("\npaths")
    for key in mismatch[:TOP]:
        print("  path-mismatch %s %s" % key)
        print("    golden: %s" % " -> ".join(gp[key][1]))
        print("    actual: %s" % " -> ".join(ap_[key][1]))
    for key in g_missing[:TOP]:
        print("  golden-only %s %s" % key)
    for key in a_extra[:TOP]:
        print("  actual-only %s %s" % key)
    print("  same %d  mismatch %d  golden-only %d  actual-only %d  slack over tol %d"
          % (len(same), len(mismatch), len(g_missing), len(a_extra), slack_over))

    if args.design:
        ctype, level = classify(args.design, args.lib)
        by_cell, by_level = {}, {}
        for pin, ds in pin_deltas.items():
            by_cell.setdefault(ctype.get(pin, "?"), []).extend(ds)
            by_level.setdefault(level.get(pin, "?"), []).extend(ds)
        print_groups("cell", by_cell)
        print_groups("level", by_level)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
