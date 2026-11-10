"""JSON report, schema v1 (R25, json_v1.md): clocks, summary, endpoints and the worst
setup / hold path object of every endpoint."""

import json

from sta_toy import P2Error, paths, timer
from sta_toy.paths import num

SCHEMA = "sta_toy.report/1"


def units(lib):
    """The library's units, never converted: time_unit and capacitive_load_unit."""
    value, unit = lib.cap_unit
    return {"time": lib.time_unit, "cap": "{:g}{}".format(value, unit)}


def _clock(g, clock):
    """One clock (R51: one per create_clock); pin_latency lists the CK pins it clocks."""
    pins = {n.name for n in g.nodes if n.kind == "CK" and n.launch_clock is clock}
    return {"name": clock.name, "period": num(clock.period), "port": clock.port,
            "latency": num(clock.latency),
            "pin_latency": {pin: num(v) for pin, v in sorted(g.sdc.pin_latency.items())
                            if pin in pins},
            "transition": num(clock.transition),
            "uncertainty": {"setup": num(clock.uncertainty["setup"]),
                            "hold": num(clock.uncertainty["hold"])}}


def _check(e, check):
    rf = timer.worst_rf(e, check)
    if rf is None:
        return {"rf": None, "at": None, "rat": None, "slack": None}
    mode = paths.MODE[check]
    return {"rf": rf, "at": num(e.at[mode][rf]), "rat": num(e.rat[mode][rf]),
            "slack": num(timer.slack(e, check, rf))}


def report_json(g, design_info):
    """The whole report; design_info is the json_v1 "design" object (units included)."""
    endpoints, objs = [], []
    for e in sorted(g.endpoints, key=lambda n: n.name):
        ids = {}
        for check in ("setup", "hold"):
            path = paths.worst_path(e, check)
            ids[check] = None
            if path is not None:
                ids[check] = "p%d" % (len(objs) + 1)
                objs.append(paths.path_json(path, g.sdc, ids[check]))
        endpoints.append({"pin": e.name, "kind": e.kind, "clock": e.capture_clock.name,
                          "setup": _check(e, "setup"), "hold": _check(e, "hold"),
                          "worst_path": ids})
    summary = {check: {"wns": num(s["wns"]), "tns": num(s["tns"]), "nvp": s["nvp"]}
               for check, s in paths.summary(g).items()}
    return {"schema": SCHEMA, "design": design_info,
            "clocks": [_clock(g, c) for c in g.sdc.clocks.values()],
            "summary": summary, "endpoints": endpoints, "paths": objs}


def dumps(obj):
    return json.dumps(obj, indent=2) + "\n"


def write(obj, path):
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(dumps(obj))
    except OSError as e:
        raise P2Error(None, None, "cannot write %s: %s" % (path, e.strerror or e))
