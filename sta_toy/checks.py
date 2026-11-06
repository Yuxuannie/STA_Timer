"""--check-timing (R35, check_timing.md): what the run left unconstrained or could not
time, from the timed graph and the lookups recorded by timer.run(grid=...)."""

from sta_toy.tsv import fmt4


def _unclocked(g):
    return [n for n in g.nodes if n.kind == "CK" and n not in g.clocked]


def _grid_items(grid):
    """{(table kind, axis): [below, above, queries, grid lows, grid highs]} of §7."""
    items = {}
    for kind, table, detail in grid:
        for k, side in enumerate(detail["extrapolated"]):
            if side is None:
                continue
            axis = table.index_1 if k == 0 else table.index_2
            item = items.setdefault((kind, detail["axes"][k]), [0, 0, [], [], []])
            item[0 if side == "below" else 1] += 1
            item[2].append(detail["query"][k])
            item[3].append(axis[0])
            item[4].append(axis[-1])
    return items


def report(g, grid):
    """The check_timing.md text."""
    sdc, netlist = g.sdc, g.netlist
    unclocked = _unclocked(g)
    inputs = [p for p in netlist.inputs if p != sdc.clock_port]
    sections = []
    ends = [p for p in netlist.outputs if p not in sdc.output_delay]
    ends += [n.name for n in g.nodes
             if n.kind == "D" and any(c.ck in unclocked for c in n.checks)]
    sections.append(("unconstrained endpoints", None, sorted(ends)))
    sections.append(("unclocked registers", None,
                     sorted({n.name.split("/")[0] for n in unclocked})))
    sections.append(("input ports without set_input_delay", None,
                     sorted(p for p in inputs if p not in sdc.input_delay)))
    sections.append(("input ports without set_input_transition", None,
                     sorted(p for p in inputs if p not in sdc.input_transition)))
    sections.append(("output ports without set_load", None,
                     sorted(p for p in netlist.outputs if p not in sdc.load)))
    sections.append(("ignored timing arcs", str(sum(g.ignored.values())),
                     ["%s %s %s %s %d" % (key + (count,))
                      for key, count in sorted(g.ignored.items())]))
    outside = sum(1 for _, _, d in grid if d["extrapolated"] != [None, None])
    items = []
    for (kind, axis), (below, above, queries, lows, highs) in sorted(_grid_items(grid).items()):
        items.append("%s %s below %d above %d query %s..%s grid %s..%s"
                     % (kind, axis, below, above, fmt4(min(queries)), fmt4(max(queries)),
                        fmt4(min(lows)), fmt4(max(highs))))
    sections.append(("lookups outside the table grid", "%d of %d" % (outside, len(grid)), items))
    lines = []
    for title, count, rows in sections:
        lines.append("%s: %s" % (title, count if count is not None else len(rows)))
        lines += ["  " + r for r in rows]
    return "".join(line + "\n" for line in lines)
