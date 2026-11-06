"""--trace PIN (R36, trace.md): the engine's own log, filtered to the endpoint's fan-in
cone and formatted. Every number printed comes from a log entry; nothing is recomputed."""

import os

from sta_toy import P2Error, bundle, timer
from sta_toy.tsv import fmt4

KINDS = ("setup", "hold")


def collect(g, name, log):
    """The endpoint `name` of a graph timed with `log`; appends its slack and path entries."""
    e = g.by_name.get(name)
    if e is None or e not in g.endpoints:
        raise P2Error(None, None, "--trace %s is not an endpoint" % name)
    for kind in KINDS:
        for rf in ("r", "f"):
            timer.slack(e, kind, rf, log)
    for kind in KINDS:
        rf = timer.worst_rf(e, kind)
        if rf is not None:
            timer.worst_path(e, kind, rf, log)
    return e


def _forward(x):
    lines = ["%s %s %s at %s slew %s" % (x["pin"], x["mode"], x["rf"], fmt4(x["at"]), fmt4(x["slew"]))]
    if x["source"] is not None:
        lines[0] += " source " + x["source"]
    for k, c in enumerate(x["candidates"]):
        lines.append("  %s %s(%s) %s + %s = %s slew %s"
                     % ("*" if k == x["winner"] else " ", c["src"], c["rf"], fmt4(c["at"]),
                        fmt4(c["delay"]), fmt4(c["value"]), fmt4(c["slew"])))
    return lines


def _check(x):
    head = "%s %s %s rat %s = " % (x["pin"], x["kind"], x["rf"], fmt4(x["rat"]))
    if x["ck"] is None:
        if x["kind"] == "setup":
            return [head + "period %s - output_delay %s" % (fmt4(x["period"]), fmt4(x["output_delay"]))]
        return [head + "0.0000 - output_delay %s" % fmt4(x["output_delay"])]
    if x["kind"] == "setup":
        terms = "ck_at %s + period %s - t %s - uncertainty %s" % (
            fmt4(x["ck_at"]), fmt4(x["period"]), fmt4(x["t"]), fmt4(x["uncertainty"]))
    else:
        terms = "ck_at %s + t %s + uncertainty %s" % (
            fmt4(x["ck_at"]), fmt4(x["t"]), fmt4(x["uncertainty"]))
    return [head + terms + "; t at d_slew %s ck_slew %s (%s)"
            % (fmt4(x["d_slew"]), fmt4(x["ck_slew"]), x["ck"])]


def _backward(x):
    lines = ["%s %s %s rat %s" % (x["pin"], x["mode"], x["rf"], fmt4(x["rat"]))]
    for k, c in enumerate(x["candidates"]):
        lines.append("  %s %s(%s) %s - %s = %s"
                     % ("*" if k == x["winner"] else " ", c["dst"], c["rf"], fmt4(c["rat"]),
                        fmt4(c["delay"]), fmt4(c["value"])))
    return lines


def _slack(x):
    return ["%s %s %s at %s rat %s slack %s" % (x["pin"], x["kind"], x["rf"], fmt4(x["at"]),
                                                fmt4(x["rat"]), fmt4(x["slack"]))]


def _path(x):
    return ["%s : %s" % (x["kind"], " -> ".join("%s(%s)" % (n, rf) for n, rf in x["points"]))]


SECTIONS = (("forward", _forward, False), ("check", _check, True),
            ("backward", _backward, False), ("slack", _slack, True), ("path", _path, True))


def format_trace(log, endpoint, cone, design, sdc_path):
    """The trace.md text from `log` alone; `cone` is the set of pin names to keep."""
    lines = ["trace %s (%s, %s)" % (endpoint, design, os.path.basename(sdc_path)),
             "cone: %d pins" % len(cone)]
    for phase, fmt, endpoint_only in SECTIONS:
        lines.append(phase)
        for x in log:
            if x["phase"] == phase and (x["pin"] == endpoint if endpoint_only else x["pin"] in cone):
                lines += fmt(x)
    return "".join(line + "\n" for line in lines)


def trace(g, name, log, sdc_path):
    """--trace text for endpoint `name` of a graph timed with `log`."""
    e = collect(g, name, log)
    cone = {n.name for n in bundle._cone(e, float("inf"))}
    return format_trace(log, e.name, cone, g.netlist.name, sdc_path)
