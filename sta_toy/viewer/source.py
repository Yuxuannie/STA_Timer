"""Viewer data sources without Tk (R28, viewer_p4.md): the in-process engine, or one saved
bundle (bundle_v1.md). Both answer the same questions, so model.py and app.py never ask
which one they have:

  rows()               endpoint rows {pin, kind, setup_slack, hold_slack}
  summary(check)       {wns, tns, nvp} or None
  paths(endpoint)      {"setup": path object | None, "hold": ...} (json_v1.md)
  instance(inst)       {"cell", "pins": [{"name", "direction", "clock"}]} in library order
  driver(pin)          the pin driving an input pin over a net, or None
  arrival(pin, check)  (AT, rf) of the check's mode, worst transition (ties to r), or None
  pin(name)            {"pin", "kind", "cell", "at", "rat", "slew", "slack", "load"} or None
  arcs(inst)           [{"from", "to", "kind", "delay": {mode: {pair: value}}}]
"""

import json

from sta_toy import P2Error, design, paths, timer

SCHEMA = "sta_toy.bundle/1"
MODE = {"setup": "late", "hold": "early"}
PAIRS = ("rr", "rf", "fr", "ff")


def _worst(values, mode):
    """(value, rf) of the worse transition in `mode` (late max, early min; ties to r)."""
    found = [(values[rf], rf) for rf in ("r", "f") if values[rf] is not None]
    if not found:
        return None
    pick = max if mode == "late" else min
    best = pick(v for v, _ in found)
    return [(v, rf) for v, rf in found if v == best][0]


class EngineSource:
    """Runs the engine once on a design."""

    mode = "engine"

    def __init__(self, lib_paths, verilog_path, sdc_path):
        lib, netlist, linked = design.load(lib_paths, verilog_path)
        self.g = design.timed(lib, netlist, linked, sdc_path)
        self.design_name = netlist.name
        self.clock_name = self.g.sdc.clock_name
        self.period = self.g.sdc.period
        self._cells = dict((i.name, i.cell) for i in netlist.instances)

    def rows(self):
        out = []
        for e in self.g.endpoints:
            row = {"pin": e.name, "kind": e.kind}
            for check in ("setup", "hold"):
                rf = timer.worst_rf(e, check)
                row[check + "_slack"] = None if rf is None else timer.slack(e, check, rf)
            out.append(row)
        return out

    def summary(self, check):
        return paths.summary(self.g)[check]

    def paths(self, endpoint):
        node = self.g.by_name[endpoint]
        out = {}
        for check in ("setup", "hold"):
            p = paths.worst_path(node, check)
            out[check] = None if p is None else paths.path_json(p, self.g.sdc, check)
        return out

    def instance(self, inst):
        cell = self._cells[inst]
        return {"cell": cell, "pins": [{"name": p.name, "direction": p.direction,
                                        "clock": p.is_clock}
                                       for p in self.g.lib.cells[cell].pins]}

    def driver(self, pin):
        node = self.g.by_name.get(pin)
        found = [a.src.name for a in node.fanin if a.kind == "net"] if node else []
        return found[0] if found else None

    def arrival(self, pin, check):
        node = self.g.by_name.get(pin)
        return _worst(node.at[MODE[check]], MODE[check]) if node else None

    def pin(self, name):
        n = self.g.by_name.get(name)
        if n is None:
            return None
        slack = {}
        for check in ("setup", "hold"):
            found = [timer.slack(n, check, rf) for rf in ("r", "f")]
            found = [s for s in found if s is not None]
            slack[check] = min(found) if found else None
        drives = any(a.kind == "net" for a in n.fanout)
        return {"pin": n.name, "kind": n.kind, "cell": n.cell, "at": n.at, "rat": n.rat,
                "slew": n.slew, "slack": slack, "load": n.load if drives else None}

    def arcs(self, inst):
        out = []
        for n in self.g.nodes:
            if n.name.split("/")[0] != inst or "/" not in n.name:
                continue
            for a in n.fanin:
                if a.kind not in ("cell", "ckq"):
                    continue
                delay = {}
                for m in timer.MODES:
                    delay[m] = {}
                    for ab in PAIRS:
                        ok = (ab[0], ab[1]) in a.pairs and a.src.slew[m][ab[0]] is not None
                        delay[m][ab] = timer.arc_delay(a, m, ab[0], ab[1])[0] if ok else None
                out.append({"from": a.src.name, "to": n.name, "kind": a.kind, "delay": delay})
        return out


class BundleSource:
    """One saved bundle: only its endpoint is listed, and only its cone can be expanded."""

    mode = "bundle"

    def __init__(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            raise P2Error(None, None, "cannot read %s: %s" % (path, getattr(e, "strerror", None) or e))
        try:
            data = json.loads(text)
        except ValueError:
            raise P2Error(None, None, "%s is not JSON" % path)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise P2Error(None, None, "%s is not a %s bundle" % (path, SCHEMA))
        if "instances" not in data:
            raise P2Error(None, None, "%s has no instances; write it again with --bundle" % path)
        self.data = data
        self.design_name = data["endpoint"]
        self.clock_name = data["clock"]["name"]
        self.period = data["clock"]["period"]
        self.nodes = dict((n["pin"], n) for n in data["nodes"])
        self.drivers = dict((e["v"], e["u"]) for e in data["edges"] if e["kind"] == "net")

    def rows(self):
        n = self.nodes[self.data["endpoint"]]
        return [{"pin": n["pin"], "kind": n["kind"], "setup_slack": n["slack"]["setup"],
                 "hold_slack": n["slack"]["hold"]}]

    def summary(self, check):
        return None

    def paths(self, endpoint):
        found = dict((p["check"], p) for p in self.data["paths"])
        return {"setup": found.get("setup"), "hold": found.get("hold")}

    def instance(self, inst):
        return self.data["instances"][inst]

    def driver(self, pin):
        return self.drivers.get(pin)

    def arrival(self, pin, check):
        n = self.nodes.get(pin)
        return _worst(n["at"][MODE[check]], MODE[check]) if n else None

    def pin(self, name):
        n = self.nodes.get(name)
        if n is None:
            return None
        return {"pin": n["pin"], "kind": n["kind"], "cell": n["cell"], "at": n["at"],
                "rat": n["rat"], "slew": n["slew"], "slack": n["slack"], "load": n["cap"]}

    def arcs(self, inst):
        return [{"from": e["u"], "to": e["v"], "kind": e["kind"], "delay": e["delay"]}
                for e in self.data["edges"]
                if e["kind"] in ("cell", "ckq") and e["v"].split("/")[0] == inst and "/" in e["v"]]
