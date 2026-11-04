"""P3 paths (report_p3.md): the path model (R21), worst and K-worst paths and endpoint
selection (R22), the summary (R24), and the path object of json_v1.md."""

import heapq
import itertools

from sta_toy import P2Error, timer
from sta_toy.tsv import fmt4

MODE = {"setup": "late", "hold": "early"}
SOURCES = ("PI", "CK")


def num(v):
    """A number as written to JSON: float(fmt4(v)), None stays None."""
    return None if v is None else float(fmt4(v))


class Point:
    """One (node, rf) of a path; arc names the arc into it ('start' for the first)."""

    def __init__(self, node, rf, arc, incr, at):
        self.node = node
        self.rf = rf
        self.arc = arc
        self.incr = incr
        self.at = at


class Path:
    def __init__(self, check, points, required):
        self.check = check
        self.points = points
        self.start = points[0].node
        self.endpoint = points[-1].node
        self.rf = points[-1].rf
        self.arrival = points[-1].at
        self.required = required
        self.slack = (required - self.arrival) if check == "setup" else (self.arrival - required)

    def key(self):
        return _key(self.points[::-1])

    def text(self):
        return " -> ".join("%s(%s)" % (p.node.name, p.rf) for p in self.points)


def _key(points_from_end):
    return tuple((p.node.name if isinstance(p, Point) else p[0].name,
                  timer.RF_RANK[p.rf if isinstance(p, Point) else p[1]]) for p in points_from_end)


def _build(check, steps, required):
    """steps = [(node, rf, arc into it)] from the startpoint (arc None for the first)."""
    mode = MODE[check]
    node, rf, _ = steps[0]
    at = node.at[mode][rf]
    points = [Point(node, rf, "start", 0.0, at)]
    for (u, rf_u, _), (v, rf_v, arc) in zip(steps, steps[1:]):
        incr = timer.arc_delay(arc, mode, rf_u, rf_v)[0]
        at += incr
        points.append(Point(v, rf_v, arc.kind, incr, at))
    return Path(check, points, required)


def worst_path(endpoint, check):
    """The PRED chain from (endpoint, rf*) of p2_semantics.md §9, or None."""
    rf = timer.worst_rf(endpoint, check)
    if rf is None:
        return None
    mode = MODE[check]
    steps = [(endpoint, rf, None)]
    while steps[-1][0].pred[mode][steps[-1][1]] is not None:
        v, rf_v, _ = steps[-1]
        u, rf_u = v.pred[mode][rf_v]
        # The arc PRED went through: among arcs u -> v with this pair, the one giving the AT.
        arcs = [a for a in v.fanin if a.src is u and (rf_u, rf_v) in a.pairs]
        pick = max if mode == "late" else min
        arc = pick(arcs, key=lambda a: timer.arc_delay(a, mode, rf_u, rf_v)[0])
        steps[-1] = (v, rf_v, arc)
        steps.append((u, rf_u, None))
    return _build(check, steps[::-1], endpoint.rat[mode][rf])


def _bound_slack(check, required, arrival):
    return (required - arrival) if check == "setup" else (arrival - required)


def enumerate_paths(endpoint, check, k=1, frm=None, through=None):
    """The first k paths at endpoint in path order (report_p3.md §1-§2), optionally only
    those starting at node name `frm` and/or passing node name `through`."""
    mode = MODE[check]
    heap, tie, found = [], itertools.count(), []
    for rf in ("r", "f"):
        required = endpoint.rat[mode][rf]
        if required is None or endpoint.at[mode][rf] is None:
            continue
        suffix = ((endpoint, rf, None),)
        bound = _bound_slack(check, required, endpoint.at[mode][rf])
        heapq.heappush(heap, (round(bound, 9), _key(suffix), next(tie), 0.0, required, suffix))
    while heap and len(found) < k:
        _, _, _, delay, required, suffix = heapq.heappop(heap)
        v, rf_v, _ = suffix[-1]
        if v.kind in SOURCES:
            if (frm is None or v.name == frm) and (through is None or
                                                   any(s[0].name == through for s in suffix)):
                found.append(_build(check, _steps(suffix), required))
            continue
        for arc in v.fanin:
            for rf_u, rf_out in arc.pairs:
                at = arc.src.at[mode][rf_u]
                if rf_out != rf_v or at is None:
                    continue
                d = delay + timer.arc_delay(arc, mode, rf_u, rf_v)[0]
                new = suffix[:-1] + ((v, rf_v, arc), (arc.src, rf_u, None))
                bound = _bound_slack(check, required, at + d)
                heapq.heappush(heap, (round(bound, 9), _key(new), next(tie), d, required, new))
    return found


def _steps(suffix):
    """Suffix entries (node, rf, arc into node), endpoint first -> steps from the start."""
    return list(suffix[::-1])


def select(g, check, max_paths=1, nworst=1, frm=None, to=None, through=None):
    """report_timing's endpoint selection (report_p3.md §3); returns the paths in order."""
    if frm is not None and (frm not in g.by_name or g.by_name[frm].kind not in SOURCES):
        raise P2Error(None, None, "--from %s is not a startpoint" % frm)
    if through is not None and through not in g.by_name:
        raise P2Error(None, None, "--through %s is not a node" % through)
    endpoints = g.endpoints
    if to is not None:
        endpoints = [e for e in g.endpoints if e.name == to]
        if not endpoints:
            raise P2Error(None, None, "--to %s is not an endpoint" % to)
    picked = []
    for e in endpoints:
        found = enumerate_paths(e, check, nworst, frm, through)
        if found:
            picked.append((round(found[0].slack, 9), e.name, found))
    picked.sort(key=lambda t: t[:2])
    return [p for _, _, found in picked[:max_paths] for p in found]


def summary(g):
    """report_p3.md §5: wns / tns / nvp per check over the endpoints' worst transitions."""
    out = {}
    for check in ("setup", "hold"):
        slacks = []
        for e in g.endpoints:
            rf = timer.worst_rf(e, check)
            if rf is not None:
                slacks.append(timer.slack(e, check, rf))
        out[check] = {"wns": min(slacks) if slacks else None,
                      "tns": sum(min(s, 0.0) for s in slacks),
                      "nvp": sum(1 for s in slacks if s < -timer.TOL)}
    return out


def capture(path, sdc):
    """Capture-side values of a path (report_p3.md §4, json_v1.md `capture`)."""
    e, check = path.endpoint, path.check
    edge = sdc.period if check == "setup" else 0.0
    if e.kind == "D":
        ck = [c.ck for c in e.checks if c.kind == check][0]
        latency = ck.at[MODE[check]]["r"]
        if check == "setup":
            u = sdc.uncertainty["setup"]
            t = (latency + edge - u) - path.required
        else:
            u = sdc.uncertainty["hold"]
            t = path.required - (latency + u)
        return {"clock_edge": edge, "latency": latency, "uncertainty": u, "check": t,
                "output_delay": None, "rat": path.required, "pin": ck.name, "cell": ck.cell}
    delay = sdc.output_delay[e.name]["max" if check == "setup" else "min"]
    return {"clock_edge": edge, "latency": None, "uncertainty": None, "check": None,
            "output_delay": delay, "rat": path.required, "pin": None, "cell": None}


def path_json(path, sdc, pid):
    """The path object of json_v1.md."""
    mode = MODE[path.check]
    first = path.points[0]
    points = [{"pin": p.node.name, "cell": p.node.cell, "arc": p.arc, "rf": p.rf,
               "incr": num(p.incr), "at": num(p.at), "slew": num(p.node.slew[mode][p.rf]),
               "cap": num(p.node.load) if any(a.kind == "net" for a in p.node.fanout) else None}
              for p in path.points]
    cap = capture(path, sdc)
    return {"id": pid, "type": "max" if path.check == "setup" else "min", "check": path.check,
            "start": path.start.name, "end": path.endpoint.name,
            "launch_clock": sdc.clock_name, "capture_clock": sdc.clock_name,
            "points": points,
            "launch": {"clock_edge": 0.0,
                       "latency": num(first.at) if first.node.kind == "CK" else None,
                       "input_delay": num(first.at) if first.node.kind == "PI" else None},
            "capture": {k: (num(v) if isinstance(v, float) else v) for k, v in cap.items()},
            "arrival": num(path.arrival), "required": num(path.required), "slack": num(path.slack)}
