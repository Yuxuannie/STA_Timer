"""ASCII form of the timing graph (R6)."""


def write(g):
    """Return the graph as text: two header lines, then each node followed by its out-edges."""
    edges = [e for node in g.nodes for e in node.edges]
    net_count = sum(1 for e in edges if e.kind == "net")
    lines = [
        "# design %s | library %s | cap_unit %s%s"
        % (g.design, g.library, "{:g}".format(g.cap_unit[0]), g.cap_unit[1]),
        "# nodes %d | edges %d (net %d, cell %d)"
        % (len(g.nodes), len(edges), net_count, len(edges) - net_count),
    ]
    for node in g.nodes:
        if node.kind in ("PI", "PO"):
            lines.append("%s [%s]" % (node.name, node.kind))
        elif node.kind == "input":
            lines.append("%s [%s input cap=%s]" % (node.name, node.cell, "{:g}".format(node.cap)))
        else:
            lines.append("%s [%s output]" % (node.name, node.cell))
        for e in node.edges:
            if e.kind == "cell":
                lines.append("  cell -> %s  %s" % (e.dst, ",".join(e.senses)))
        for e in node.edges:
            if e.kind == "net":
                target = g.node(e.dst)
                if target.kind == "PO":
                    lines.append("  net  -> %s  PO" % e.dst)
                else:
                    lines.append("  net  -> %s  cap=%s" % (e.dst, "{:g}".format(target.cap)))
    return "\n".join(lines) + "\n"
