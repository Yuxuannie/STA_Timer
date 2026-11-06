#!/usr/bin/env python3
"""Convert an ISCAS .bench netlist to flat Verilog on toy2.lib cells.

    python3 tools/bench2v.py IN.bench OUT.v --top NAME

The Verilog uses only what the stage 1 parser reads: one module, `input` /
`output` / `wire` declarations, named connections.  Gate mapping:

    NOT -> INV, BUF / BUFF -> BUF, 2-input AND / OR / NAND / NOR -> AND2 /
    OR2 / NAND2 / NOR2; n > 2 inputs -> a balanced tree of AND2 / OR2 whose
    last stage is NAND2 / NOR2 for the inverting kinds; 1 input -> BUF (AND,
    OR) or INV (NAND, NOR); XOR(a, b) -> OR2(AND2(a, INV b), AND2(INV a, b));
    XNOR -> that plus INV; DFF(d) -> DFF (.CK(clk), .D(d), .Q(q)) with a
    top-level `input clk`.

Names: an instance is named after the net it drives, `U<net>` for gates and
`FF<net>` for flip-flops, where a leading `G` before a digit is dropped
(`G14` -> `U14`, as data/s27.v does).  Decomposition intermediates are nets
`<net>_t<i>` (i from 0 in creation order), driven by `U<net>_t<i>`.
Instance counts per cell are printed on stdout.
"""
import argparse
import re
import sys

CLOCK = "clk"
TWO_INPUT = {"AND": "AND2", "OR": "OR2", "NAND": "NAND2", "NOR": "NOR2"}
TREE = {"AND": ("AND2", "AND2"), "OR": ("OR2", "OR2"),
        "NAND": ("AND2", "NAND2"), "NOR": ("OR2", "NOR2")}

LINE_IO = re.compile(r"^(INPUT|OUTPUT)\s*\(\s*([^\s()]+)\s*\)$")
LINE_GATE = re.compile(r"^([^\s=]+)\s*=\s*([A-Za-z]+)\s*\(([^()]*)\)$")


class BenchError(Exception):
    pass


def parse_bench(text, path="<bench>"):
    """Return (inputs, outputs, gates); gates are (out_net, KIND, [in_nets], line)."""
    inputs, outputs, gates = [], [], []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = LINE_IO.match(line)
        if m:
            (inputs if m.group(1) == "INPUT" else outputs).append(m.group(2))
            continue
        m = LINE_GATE.match(line)
        if not m:
            raise BenchError("%s:%d: cannot parse line: %s" % (path, lineno, line))
        args = [a.strip() for a in m.group(3).split(",") if a.strip()]
        if not args:
            raise BenchError("%s:%d: gate %s has no inputs" % (path, lineno, m.group(1)))
        gates.append((m.group(1), m.group(2).upper(), args, lineno))
    return inputs, outputs, gates


def inst_name(prefix, net):
    if len(net) > 1 and net[0] == "G" and net[1].isdigit():
        net = net[1:]
    return prefix + net


class Builder:
    def __init__(self):
        self.instances = []   # (cell, name, [(pin, net)])
        self.wires = []       # intermediate nets, in creation order
        self.counter = {}

    def add(self, cell, out, ins):
        pins = list(zip(("A", "B"), ins)) + [("Y", out)]
        self.instances.append((cell, inst_name("U", out), pins))

    def temp(self, net):
        i = self.counter.get(net, 0)
        self.counter[net] = i + 1
        name = "%s_t%d" % (net, i)
        self.wires.append(name)
        return name

    def tree(self, cell, ins, net):
        """Balanced tree of `cell` over ins; returns the net carrying the result."""
        if len(ins) == 1:
            return ins[0]
        half = (len(ins) + 1) // 2
        a = self.tree(cell, ins[:half], net)
        b = self.tree(cell, ins[half:], net)
        out = self.temp(net)
        self.add(cell, out, [a, b])
        return out

    def gate(self, out, kind, ins, where):
        n = len(ins)
        if kind == "DFF":
            if n != 1:
                raise BenchError("%s: DFF %s needs 1 input, has %d" % (where, out, n))
            self.instances.append(("DFF", inst_name("FF", out),
                                   [("CK", CLOCK), ("D", ins[0]), ("Q", out)]))
        elif kind == "NOT" or kind in ("BUF", "BUFF"):
            if n != 1:
                raise BenchError("%s: %s %s needs 1 input, has %d" % (where, kind, out, n))
            self.add("INV" if kind == "NOT" else "BUF", out, ins)
        elif kind in TWO_INPUT:
            if n == 1:
                self.add("INV" if kind in ("NAND", "NOR") else "BUF", out, ins)
            elif n == 2:
                self.add(TWO_INPUT[kind], out, ins)
            else:
                inner, last = TREE[kind]
                half = (n + 1) // 2
                a = self.tree(inner, ins[:half], out)
                b = self.tree(inner, ins[half:], out)
                self.add(last, out, [a, b])
        elif kind in ("XOR", "XNOR"):
            if n != 2:
                raise BenchError("%s: %s %s needs 2 inputs, has %d" % (where, kind, out, n))
            a, b = ins
            nb = self.temp(out)
            self.add("INV", nb, [b])
            t1 = self.temp(out)
            self.add("AND2", t1, [a, nb])
            na = self.temp(out)
            self.add("INV", na, [a])
            t2 = self.temp(out)
            self.add("AND2", t2, [na, b])
            if kind == "XOR":
                self.add("OR2", out, [t1, t2])
            else:
                x = self.temp(out)
                self.add("OR2", x, [t1, t2])
                self.add("INV", out, [x])
        else:
            raise BenchError("%s: unsupported gate kind %s" % (where, kind))


def convert(text, top, path="<bench>"):
    """Return (verilog_text, {cell: count})."""
    inputs, outputs, gates = parse_bench(text, path)
    driven = {}
    for net in inputs:
        if net in driven:
            raise BenchError("%s: net %s declared INPUT twice" % (path, net))
        driven[net] = "input"
    for out, _kind, _ins, line in gates:
        if out in driven:
            raise BenchError("%s:%d: net %s has two drivers" % (path, line, out))
        driven[out] = line
    names = set(driven)
    for _out, _kind, ins, line in gates:
        for net in ins:
            if net not in names:
                raise BenchError("%s:%d: net %s is never driven" % (path, line, net))
    for net in outputs:
        if net not in names:
            raise BenchError("%s: OUTPUT %s is never driven" % (path, net))
        if driven[net] == "input":
            raise BenchError("%s: OUTPUT %s is an INPUT (needs a buffer)" % (path, net))
    if CLOCK in names:
        raise BenchError("%s: net name %s is reserved for the clock" % (path, CLOCK))

    b = Builder()
    for out, kind, ins, line in gates:
        b.gate(out, kind, ins, "%s:%d" % (path, line))

    outset = set(outputs)
    wires = [out for out, _k, _i, _l in gates if out not in outset] + b.wires
    lines = ["// %s - converted from %s by tools/bench2v.py (toy2.lib cells)." % (top, path),
             "module %s (%s);" % (top, ", ".join([CLOCK] + inputs + outputs)),
             "  input %s;" % CLOCK]
    lines += ["  input %s;" % n for n in inputs]
    lines += ["  output %s;" % n for n in outputs]
    lines += ["  wire %s;" % n for n in wires]
    counts = {}
    for cell, name, pins in b.instances:
        counts[cell] = counts.get(cell, 0) + 1
        conns = ", ".join(".%s(%s)" % (p, n) for p, n in pins)
        lines.append("  %s %s (%s);" % (cell, name, conns))
    lines.append("endmodule")
    return "\n".join(lines) + "\n", counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="ISCAS .bench -> flat Verilog on toy2.lib")
    ap.add_argument("bench")
    ap.add_argument("out")
    ap.add_argument("--top", required=True)
    args = ap.parse_args(argv)
    try:
        with open(args.bench) as f:
            text = f.read()
        verilog, counts = convert(text, args.top, args.bench)
        with open(args.out, "w") as f:
            f.write(verilog)
    except (OSError, BenchError) as e:
        sys.stderr.write("error: %s\n" % e)
        return 1
    for cell in sorted(counts):
        print("%-6s %d" % (cell, counts[cell]))
    print("%-6s %d" % ("total", sum(counts.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
