#!/usr/bin/env python3
"""Independent oracle for stage P2 golden files.

This script shares NO code with the timer.  It has its own minimal Liberty,
Verilog and SDC readers (they understand only what the test files use) and it
evaluates library tables by fitting a plane to the table (every table in
toy2.lib is affine), not by bilinear interpolation.  If a table is not affine
it refuses to run.  It implements the semantics written in
docs/contracts/p2_semantics.md and writes the three golden files described in
docs/contracts/golden_format.md.

    python3 tools/oracle/oracle.py --lib data/toy2.lib --verilog data/ff2.v \
        --sdc data/sdc/ff2_default.sdc --out tests/golden/ff2_default

Python 3.8+, standard library only.
"""
import argparse
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_UP

EPS = 1e-9
RF = ("r", "f")


def die(msg):
    sys.stderr.write("oracle: %s\n" % msg)
    sys.exit(2)


# ----------------------------------------------------------------------------
# Liberty (minimal)
# ----------------------------------------------------------------------------
class Group:
    def __init__(self, name, args):
        self.name, self.args, self.attrs, self.groups = name, args, {}, []


def lib_tokens(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = text.replace("\\\n", " ")
    return re.findall(r'"[^"]*"|[{}();:,]|[^\s{}();:,]+', text)


def lib_parse(text):
    toks = lib_tokens(text)
    pos = [0]

    def peek(k=0):
        return toks[pos[0] + k] if pos[0] + k < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def parse_args():
        assert take() == "("
        args, cur = [], []
        while True:
            t = take()
            if t == ")":
                if cur:
                    args.append(" ".join(cur))
                return args
            if t == ",":
                args.append(" ".join(cur))
                cur = []
            else:
                cur.append(t.strip('"'))

    def parse_group():
        name = take()
        args = parse_args()
        g = Group(name, args)
        assert take() == "{"
        while peek() != "}":
            n = take()
            if peek() == ":":
                take()
                vals = []
                while peek() != ";":
                    vals.append(take().strip('"'))
                take()
                g.attrs[n] = " ".join(vals)
            elif peek() == "(":
                if peek_group_after_args():
                    pos[0] -= 1
                    g.groups.append(parse_group())
                else:
                    a = parse_args()
                    assert take() == ";"
                    g.attrs[n] = a
            else:
                die("unexpected token %r" % n)
        take()
        return g

    def peek_group_after_args():
        depth, k = 0, 0
        while True:
            t = peek(k)
            if t == "(":
                depth += 1
            elif t == ")":
                depth -= 1
                if depth == 0:
                    return peek(k + 1) == "{"
            k += 1

    return parse_group()


class Plane:
    """value = a + b1*x1 + b2*x2, fitted from an affine table; refuses non-affine tables."""

    def __init__(self, idx1, idx2, vals, vars_):
        v00, v10, v01 = vals[0][0], vals[1][0], vals[0][1]
        self.b1 = (v10 - v00) / (idx1[1] - idx1[0])
        self.b2 = (v01 - v00) / (idx2[1] - idx2[0])
        self.a = v00 - self.b1 * idx1[0] - self.b2 * idx2[0]
        for i, x1 in enumerate(idx1):
            for j, x2 in enumerate(idx2):
                if abs(self.a + self.b1 * x1 + self.b2 * x2 - vals[i][j]) > 1e-6:
                    die("table is not affine; this oracle only handles affine tables")
        self.vars = vars_  # (name of x1, name of x2)

    def __call__(self, **kw):
        return self.a + self.b1 * kw[self.vars[0]] + self.b2 * kw[self.vars[1]]


def floats(s):
    return [float(x) for x in s.replace(",", " ").split()]


class Lib:
    def __init__(self, path):
        with open(path) as f:
            root = lib_parse(f.read())
        self.templates = {}
        for g in root.groups:
            if g.name == "lu_table_template":
                self.templates[g.args[0]] = (g.attrs["variable_1"], g.attrs["variable_2"],
                                             floats(g.attrs["index_1"][0]), floats(g.attrs["index_2"][0]))
        self.cells = {}
        for g in root.groups:
            if g.name == "cell":
                self.cells[g.args[0]] = self._cell(g)

    def _table(self, tg):
        v1, v2, i1, i2 = self.templates[tg.args[0]]
        if "index_1" in tg.attrs:
            i1 = floats(tg.attrs["index_1"][0])
        if "index_2" in tg.attrs:
            i2 = floats(tg.attrs["index_2"][0])
        rows = [floats(r) for r in tg.attrs["values"]]
        return Plane(i1, i2, rows, (v1, v2))

    def _cell(self, cg):
        cell = {"pins": {}, "arcs": []}
        for pg in cg.groups:
            if pg.name != "pin":
                continue
            pname = pg.args[0]
            cell["pins"][pname] = {"dir": pg.attrs.get("direction"),
                                   "cap": float(pg.attrs.get("capacitance", "0")),
                                   "clock": pg.attrs.get("clock") == "true"}
            for tg in pg.groups:
                if tg.name != "timing":
                    continue
                arc = {"pin": pname, "related": tg.attrs["related_pin"],
                       "type": tg.attrs.get("timing_type", "combinational"),
                       "sense": tg.attrs.get("timing_sense"), "tables": {}}
                for t in tg.groups:
                    arc["tables"][t.name] = self._table(t)
                cell["arcs"].append(arc)
        return cell


# ----------------------------------------------------------------------------
# Verilog (minimal: flat module, named connections, scalar nets)
# ----------------------------------------------------------------------------
class Netlist:
    def __init__(self, path):
        with open(path) as f:
            text = re.sub(r"//[^\n]*", "", f.read())
        toks = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[();,.]", text)
        self.ports, self.inputs, self.outputs, self.insts = [], [], [], []
        i = 0
        while i < len(toks):
            t = toks[i]
            if t == "module":
                j = toks.index(")", i)
                self.ports = [x for x in toks[i + 2:j] if x not in (",", "(")]
                i = j + 2
            elif t in ("input", "output", "wire"):
                j = toks.index(";", i)
                names = [x for x in toks[i + 1:j] if x != ","]
                if t == "input":
                    self.inputs += names
                elif t == "output":
                    self.outputs += names
                i = j + 1
            elif t == "endmodule":
                break
            else:
                cell, inst = toks[i], toks[i + 1]
                j = toks.index(";", i)
                conn, k = {}, i + 3
                while k < j:
                    if toks[k] == ".":
                        conn[toks[k + 1]] = toks[k + 3]
                        k += 5
                    else:
                        k += 1
                self.insts.append((inst, cell, conn))
                i = j + 1


# ----------------------------------------------------------------------------
# SDC (minimal)
# ----------------------------------------------------------------------------
class Sdc:
    def __init__(self, path):
        self.clock = None  # (name, period, port)
        self.clock_latency, self.pin_latency = 0.0, {}
        self.clock_transition = 0.0
        self.unc = {"setup": 0.0, "hold": 0.0}
        self.in_delay, self.out_delay, self.in_tran, self.load = {}, {}, {}, {}
        with open(path) as f:
            for ln, line in enumerate(f, 1):
                line = line.split("#")[0].strip()
                if line:
                    self._cmd(line, ln)

    def _cmd(self, line, ln):
        m = re.match(r"(\S+)(.*?)(\[get_(ports|pins|clocks) (\S+)\])?\s*$", line)
        cmd, rest, kind, target = m.group(1), m.group(2).split(), m.group(4), m.group(5)
        opts, vals = {}, []
        i = 0
        while i < len(rest):
            tok = rest[i]
            if re.fullmatch(r"-?\d+(\.\d+)?", tok):
                vals.append(float(tok))
                i += 1
            elif tok in ("-min", "-max", "-setup", "-hold"):
                opts[tok] = True
                i += 1
            elif tok in ("-name", "-period", "-clock"):
                opts[tok] = rest[i + 1]
                i += 2
            else:
                die("%s: line %d: unexpected token %s" % ("sdc", ln, tok))
        v = vals[0] if vals else None
        if cmd == "create_clock":
            self.clock = (opts["-name"], float(opts["-period"]), target)
        elif cmd == "set_clock_transition":
            self.clock_transition = v
        elif cmd == "set_clock_latency":
            if kind == "pins":
                self.pin_latency[target] = v
            else:
                self.clock_latency = v
        elif cmd == "set_clock_uncertainty":
            if "-setup" in opts or not ("-hold" in opts):
                self.unc["setup"] = v
            if "-hold" in opts or not ("-setup" in opts):
                self.unc["hold"] = v
        elif cmd in ("set_input_delay", "set_output_delay"):
            d = self.in_delay if cmd == "set_input_delay" else self.out_delay
            e = d.setdefault(target, {})
            if "-min" in opts or not ("-max" in opts):
                e["min"] = v
            if "-max" in opts or not ("-min" in opts):
                e["max"] = v
        elif cmd == "set_input_transition":
            self.in_tran[target] = v
        elif cmd == "set_load":
            self.load[target] = v
        else:
            die("%s: line %d: unknown command %s" % ("sdc", ln, cmd))


# ----------------------------------------------------------------------------
# Timing
# ----------------------------------------------------------------------------
class Node:
    def __init__(self, name):
        self.name = name
        self.at = {"late": {}, "early": {}}     # rf -> value
        self.slew = {"late": {}, "early": {}}
        self.rat = {"late": {}, "early": {}}
        self.pred = {"late": {}, "early": {}}   # rf -> (node, rf)
        self.ins, self.outs = [], []            # arcs
        self.is_pi = self.is_po = self.is_ck = self.is_d = False
        self.check = []                         # (type, rf, Plane) for D pins
        self.ck_of_d = None


class Arc:
    """Timed edge u(rf_u) -> v(rf_v).  delay/trans are Planes or None (net edge)."""

    def __init__(self, u, v, pairs, delay, trans, kind):
        self.u, self.v, self.pairs, self.delay, self.trans, self.kind = u, v, pairs, delay, trans, kind


def build(lib, nl, sdc):
    nodes, nets = {}, {}  # nets: net -> {"driver": node, "loads": [node], "po": port or None}

    def node(name):
        if name not in nodes:
            nodes[name] = Node(name)
        return nodes[name]

    def net(n):
        return nets.setdefault(n, {"driver": None, "loads": [], "po": None})

    for p in nl.inputs:
        n = node(p)
        n.is_pi = True
        net(p)["driver"] = n
    for p in nl.outputs:
        n = node(p)
        n.is_po = True
        net(p)["loads"].append(n)
        net(p)["po"] = p
    for inst, cname, conn in nl.insts:
        cell = lib.cells[cname]
        for pin, nname in conn.items():
            pn = node(inst + "/" + pin)
            info = cell["pins"][pin]
            pn.cap = info["cap"]
            pn.cell, pn.inst, pn.pin = cname, inst, pin
            if info["dir"] == "output":
                if net(nname)["driver"] is not None:
                    die("net %s has two drivers" % nname)
                net(nname)["driver"] = pn
            else:
                net(nname)["loads"].append(pn)
                if info["clock"]:
                    pn.is_ck = True

    # clock
    cname_, period, cport = sdc.clock
    cnet = nets[cport]
    for ld in cnet["loads"]:
        if not ld.is_ck:
            die("clock port %s drives a non-clock pin %s" % (cport, ld.name))
    clock_port = nodes[cport]
    clock_port.is_pi = False
    clock_port.is_clock_port = True

    # loads
    for nname, nt in nets.items():
        if nt["driver"] is None:
            continue
        total = sum(ld.cap for ld in nt["loads"] if not ld.is_po)
        if nt["po"] is not None:
            total += sdc.load.get(nt["po"], 0.0)
        nt["driver"].load = total

    arcs = []
    # net edges (data nets only)
    for nname, nt in nets.items():
        if nt["driver"] is None or nname == cport:
            continue
        for ld in nt["loads"]:
            a = Arc(nt["driver"], ld, [("r", "r"), ("f", "f")], None, None, "net")
            arcs.append(a)
            nt["driver"].outs.append(a)
            ld.ins.append(a)
    # cell arcs
    for inst, cname, conn in nl.insts:
        cell = lib.cells[cname]
        for arc in cell["arcs"]:
            u = nodes[inst + "/" + arc["related"]]
            v = nodes[inst + "/" + arc["pin"]]
            t = arc["type"]
            if t == "combinational":
                s = arc["sense"]
                pairs = {"positive_unate": [("r", "r"), ("f", "f")],
                         "negative_unate": [("r", "f"), ("f", "r")],
                         "non_unate": [("r", "r"), ("r", "f"), ("f", "r"), ("f", "f")]}[s]
                a = Arc(u, v, pairs, arc["tables"], None, "cell")
            elif t == "rising_edge":
                a = Arc(u, v, [("r", "r"), ("r", "f")], arc["tables"], None, "ckq")
            elif t in ("setup_rising", "hold_rising"):
                v.is_d = True
                v.ck_of_d = u
                v.check.append((t.split("_")[0], arc["tables"]))
                continue
            else:
                die("unsupported timing_type %s" % t)
            arcs.append(a)
            u.outs.append(a)
            v.ins.append(a)
    return nodes, nets, arcs, period


def arc_delay(a, rf_u, rf_v, slew_u, mode):
    """(delay, output slew) of arc a for transition rf_u -> rf_v given the input slew."""
    if a.kind == "net":
        return 0.0, slew_u
    tabs = a.delay
    d = tabs["cell_rise" if rf_v == "r" else "cell_fall"]
    t = tabs["rise_transition" if rf_v == "r" else "fall_transition"]
    kw = {"input_net_transition": slew_u, "total_output_net_capacitance": a.v.load}
    return d(**kw), t(**kw)


def better(mode, x, y):
    """True if x is a strictly better (later for late / earlier for early) value than y."""
    return (x > y + EPS) if mode == "late" else (x < y - EPS)


def topo(nodes):
    indeg = {n: len(n.ins) for n in nodes.values()}
    order, stack = [], sorted([n for n in nodes.values() if indeg[n] == 0], key=lambda n: n.name)
    while stack:
        n = stack.pop(0)
        order.append(n)
        for a in n.outs:
            indeg[a.v] -= 1
            if indeg[a.v] == 0:
                stack.append(a.v)
        stack.sort(key=lambda n: n.name)
    if len(order) != len(nodes):
        die("combinational loop")
    return order


def forward(nodes, sdc):
    for n in nodes.values():
        if n.is_ck:
            lat = sdc.pin_latency.get(n.name, sdc.clock_latency)
            for mode in ("late", "early"):
                n.at[mode]["r"] = lat
                n.slew[mode]["r"] = sdc.clock_transition
        elif n.is_pi:
            d = sdc.in_delay.get(n.name, {})
            for rf in RF:
                n.at["late"][rf] = d.get("max", 0.0)
                n.at["early"][rf] = d.get("min", 0.0)
                n.slew["late"][rf] = n.slew["early"][rf] = sdc.in_tran.get(n.name, 0.0)
    for v in topo(nodes):
        if v.is_ck or v.is_pi or getattr(v, "is_clock_port", False):
            continue
        for mode in ("late", "early"):
            cand = {}  # rf_v -> list of (at, slew, (u, rf_u))
            for a in v.ins:
                for rf_u, rf_v in a.pairs:
                    if rf_u not in a.u.at[mode]:
                        continue
                    d, s = arc_delay(a, rf_u, rf_v, a.u.slew[mode][rf_u], mode)
                    cand.setdefault(rf_v, []).append((a.u.at[mode][rf_u] + d, s, (a.u, rf_u)))
            for rf_v, lst in cand.items():
                lst.sort(key=lambda c: (c[2][0].name, 0 if c[2][1] == "r" else 1))
                best = lst[0]
                for c in lst[1:]:
                    if better(mode, c[0], best[0]):
                        best = c
                v.at[mode][rf_v] = best[0]
                v.pred[mode][rf_v] = best[2]
                slews = [c[1] for c in lst]
                v.slew[mode][rf_v] = max(slews) if mode == "late" else min(slews)


def check(nodes, sdc, period):
    endpoints = []
    for n in nodes.values():
        if n.is_d:
            ck = n.ck_of_d
            cks_late, cks_early = ck.slew["late"]["r"], ck.slew["early"]["r"]
            for kind, tabs in n.check:
                for rf in RF:
                    tab = tabs["rise_constraint" if rf == "r" else "fall_constraint"]
                    if kind == "setup":
                        if rf not in n.slew["late"]:
                            continue
                        tsu = tab(constrained_pin_transition=n.slew["late"][rf], related_pin_transition=cks_late)
                        n.rat["late"][rf] = ck.at["late"]["r"] + period - tsu - sdc.unc["setup"]
                    else:
                        if rf not in n.slew["early"]:
                            continue
                        th = tab(constrained_pin_transition=n.slew["early"][rf], related_pin_transition=cks_early)
                        n.rat["early"][rf] = ck.at["early"]["r"] + th + sdc.unc["hold"]
            endpoints.append(n)
        elif n.is_po and n.name in sdc.out_delay:
            d = sdc.out_delay[n.name]
            for rf in RF:
                if "max" in d:
                    n.rat["late"][rf] = period - d["max"]
                if "min" in d:
                    n.rat["early"][rf] = 0.0 - d["min"]
            endpoints.append(n)
    return sorted(endpoints, key=lambda n: n.name)


def backward(nodes, endpoints):
    ep = set(endpoints)
    for u in reversed(topo(nodes)):
        if u in ep:
            continue
        for mode in ("late", "early"):
            cand = {}
            for a in u.outs:
                for rf_u, rf_v in a.pairs:
                    if rf_v not in a.v.rat[mode] or rf_u not in u.slew[mode]:
                        continue
                    d, _ = arc_delay(a, rf_u, rf_v, u.slew[mode][rf_u], mode)
                    cand.setdefault(rf_u, []).append(a.v.rat[mode][rf_v] - d)
            for rf_u, lst in cand.items():
                u.rat[mode][rf_u] = min(lst) if mode == "late" else max(lst)


def slack(n, mode, rf):
    if mode == "late":
        if rf in n.rat["late"] and rf in n.at["late"]:
            return n.rat["late"][rf] - n.at["late"][rf]
    else:
        if rf in n.rat["early"] and rf in n.at["early"]:
            return n.at["early"][rf] - n.rat["early"][rf]
    return None


def worst_rf(n, mode):
    best = None
    for rf in RF:  # rise first: ties go to rise
        s = slack(n, mode, rf)
        if s is None:
            continue
        if best is None or s < best[0] - EPS:
            best = (s, rf)
    return best


def trace(n, mode, rf):
    path = [(n, rf)]
    while rf in n.pred[mode]:
        n, rf = n.pred[mode][rf]
        path.append((n, rf))
    return list(reversed(path))


def f4(v):
    """Golden number format: kill FP noise at 1e-9, then round half away from zero to 4 places."""
    if v is None:
        return "NA"
    d = Decimal(repr(round(v, 9))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    s = str(d)
    return "0.0000" if s == "-0.0000" else s


def write(out, nodes, endpoints):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "endpoints.tsv"), "w") as f:
        f.write("pin\tsetup_at\tsetup_rat\tsetup_slack\thold_at\thold_rat\thold_slack\n")
        for n in endpoints:
            row = [n.name]
            for mode in ("late", "early"):
                w = worst_rf(n, mode)
                if w is None:
                    row += ["NA", "NA", "NA"]
                else:
                    rf = w[1]
                    row += [f4(n.at[mode][rf]), f4(n.rat[mode][rf]), f4(w[0])]
            f.write("\t".join(row) + "\n")
    with open(os.path.join(out, "pins.tsv"), "w") as f:
        f.write("pin\tat_late_r\tat_late_f\tat_early_r\tat_early_f\trat_late_r\trat_late_f\t"
                "rat_early_r\trat_early_f\tslew_late_r\tslew_late_f\tslew_early_r\tslew_early_f\n")
        for name in sorted(nodes):
            n = nodes[name]
            row = [name]
            for attr in ("at", "rat", "slew"):
                for mode in ("late", "early"):
                    for rf in RF:
                        row.append(f4(getattr(n, attr)[mode].get(rf)))
            f.write("\t".join(row) + "\n")
    with open(os.path.join(out, "paths.txt"), "w") as f:
        for n in endpoints:
            for mode, label in (("late", "setup"), ("early", "hold")):
                w = worst_rf(n, mode)
                if w is None:
                    continue
                p = trace(n, mode, w[1])
                f.write("%s %s %s : %s\n" % (n.name, label, f4(w[0]),
                                             " -> ".join("%s(%s)" % (x.name, rf) for x, rf in p)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--verilog", required=True)
    ap.add_argument("--sdc", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    lib, nl, sdc = Lib(a.lib), Netlist(a.verilog), Sdc(a.sdc)
    nodes, nets, arcs, period = build(lib, nl, sdc)
    forward(nodes, sdc)
    endpoints = check(nodes, sdc, period)
    backward(nodes, endpoints)
    write(a.out, nodes, endpoints)


if __name__ == "__main__":
    main()
