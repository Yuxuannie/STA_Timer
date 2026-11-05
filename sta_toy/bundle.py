"""Debug bundle v1 (R27, bundle_v1.md): the fan-in cone of one endpoint with its timing
values, edge delays, check values and worst paths, as a JSON-ready dict."""

import collections

from sta_toy import P2Error, paths, timer
from sta_toy.paths import num

PAIRS = ("rr", "rf", "fr", "ff")


def _cone(e, depth):
    """{node: depth}: minimum number of timing() arcs on a backward walk (net edges add 0)."""
    best = {e: 0}
    queue = collections.deque([e])
    while queue:
        v = queue.popleft()
        for arc in v.fanin:
            d = best[v] + (0 if arc.kind == "net" else 1)
            if d <= depth and (arc.src not in best or d < best[arc.src]):
                best[arc.src] = d
                if d == best[v]:
                    queue.appendleft(arc.src)
                else:
                    queue.append(arc.src)
    if e.kind == "D":
        for c in e.checks:
            best[c.ck] = 0
    return best


def _values(table):
    return {m: {rf: num(table[m][rf]) for rf in ("r", "f")} for m in timer.MODES}


def _slack(n):
    out = {}
    for check in ("setup", "hold"):
        slacks = [timer.slack(n, check, rf) for rf in ("r", "f")]
        slacks = [s for s in slacks if s is not None]
        out[check] = num(min(slacks)) if slacks else None
    return out


def _node(n, d):
    return {"pin": n.name, "cell": n.cell, "kind": n.kind, "depth": d,
            "at": _values(n.at), "rat": _values(n.rat), "slew": _values(n.slew),
            "slack": _slack(n),
            "cap": num(n.load) if any(a.kind == "net" for a in n.fanout) else None}


def _delay(arc):
    out = {}
    for m in timer.MODES:
        out[m] = {}
        for ab in PAIRS:
            a, b = ab[0], ab[1]
            ok = (a, b) in arc.pairs and arc.src.slew[m][a] is not None
            out[m][ab] = num(timer.arc_delay(arc, m, a, b)[0]) if ok else None
    return out


def _check_values(e, c, sdc):
    """t_su / t_h of report_p3.md §4 per D transition, for the check arc's own kind."""
    out = {"setup": {"r": None, "f": None}, "hold": {"r": None, "f": None}}
    for rf in ("r", "f"):
        if c.kind == "setup":
            rat, at = e.rat["late"][rf], c.ck.at["late"]["r"]
            if rat is not None and at is not None:
                out["setup"][rf] = num((at + sdc.period - sdc.uncertainty["setup"]) - rat)
        else:
            rat, at = e.rat["early"][rf], c.ck.at["early"]["r"]
            if rat is not None and at is not None:
                out["hold"][rf] = num(rat - (at + sdc.uncertainty["hold"]))
    return out


def debug_bundle(g, endpoint_name, depth=3, max_nodes=300):
    """The bundle_v1.md dict for endpoint `endpoint_name`."""
    e = g.by_name.get(endpoint_name)
    if e is None or e not in g.endpoints:
        raise P2Error(None, None, "--bundle %s is not an endpoint" % endpoint_name)
    cone = _cone(e, depth)
    order = sorted(cone, key=lambda n: (n is not e, cone[n], n.name))
    kept = set(order[:max_nodes])
    edges = [{"u": arc.src.name, "v": v.name, "kind": arc.kind, "delay": _delay(arc), "check": None}
             for v in order[:max_nodes] for arc in v.fanin if arc.src in kept]
    if e.kind == "D":
        # One check edge per capture CK pin, with the values of its setup and hold arcs.
        for ck in sorted({c.ck for c in e.checks if c.ck in kept}, key=lambda n: n.name):
            values = {"setup": {"r": None, "f": None}, "hold": {"r": None, "f": None}}
            for c in e.checks:
                if c.ck is ck:
                    values[c.kind] = _check_values(e, c, g.sdc)[c.kind]
            edges.append({"u": ck.name, "v": e.name, "kind": "check", "delay": None,
                          "check": values})
    edges.sort(key=lambda x: (x["v"], x["u"], x["kind"]))
    found = []
    for check in ("setup", "hold"):
        p = paths.worst_path(e, check)
        if p is not None:
            found.append(paths.path_json(p, g.sdc, check))
    # Cell and library pins of every instance in the cone or on a path, for drawing modules.
    cells = [(n.name, n.cell) for n in order[:max_nodes]]
    cells += [(q["pin"], q["cell"]) for p in found for q in p["points"]]
    instances = {}
    for pin, cell in cells:
        if cell is not None and pin.split("/")[0] not in instances:
            instances[pin.split("/")[0]] = {
                "cell": cell, "sequential": g.lib.cells[cell].sequential,
                "pins": [{"name": q.name, "direction": q.direction, "clock": q.is_clock,
                          "function": q.function} for q in g.lib.cells[cell].pins]}
    return {"schema": "sta_toy.bundle/1", "endpoint": e.name, "depth": depth,
            "max_nodes": max_nodes, "truncated": len(order) > max_nodes,
            "clock": {"name": g.sdc.clock_name, "period": num(g.sdc.period)},
            "nodes": [_node(n, cone[n]) for n in order[:max_nodes]],
            "edges": edges,
            "instances": dict(sorted(instances.items())),
            "paths": found}
