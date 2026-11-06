"""Viewer data sources without Tk (R28, viewer_p4.md): the in-process engine, or one saved
bundle (bundle_v1.md). Both answer the same questions, so model.py and app.py never ask
which one they have:

  rows()               endpoint rows {pin, kind, setup_slack, hold_slack}
  summary(check)       {wns, tns, nvp} or None
  paths(endpoint)      {"setup": path object | None, "hold": ...} (json_v1.md)
  instance(inst)       {"cell", "sequential", "pins": [{"name", "direction", "clock", "function"}]}
                       in library order
  fanin(pin, check, rf)   forward merge: every candidate arrival into (pin, rf), the winner first
  fanout(pin, check, rf)  backward merge: every candidate required time from (pin, rf)'s fanout,
                          the binding one first
  driver(pin)          the pin driving an input pin over a net, or None
  arrival(pin, check)  (AT, rf) of the check's mode, worst transition (ties to r), or None
  pin(name)            {"pin", "kind", "cell", "at", "rat", "slew", "slack", "load", "fanout"} or None
  arcs(inst)           [{"from", "to", "kind", "delay": {mode: {pair: value}}}]
  arc_lookup(from_pin, to_pin, check, rf_from, rf_to)
                       {"delay", "slew"}: lookup.lookup_detail of the arc's tables, or None
  check_lookup(pin, check, rf)   lookup.lookup_detail of a D pin's constraint table, or None
  trace(endpoint)      the R36 trace entries of the endpoint (trace.md), or None
"""

import json

from sta_toy import P2Error, bundle, design, lookup, paths, timer, trace

SCHEMA = "sta_toy.bundle/1"
MODE = {"setup": "late", "hold": "early"}
PAIRS = ("rr", "rf", "fr", "ff")


def _merge(found, largest_first):
    """Candidates ordered binding first (largest or smallest value; ties by pin and r before f),
    each with `margin` = how far it is from the binding one (0 for the binding one)."""
    found.sort(key=lambda c: ((-c["value"]) if largest_first else c["value"],
                              c.get("from", c.get("to")), c["rf"] != "r"))
    for c in found:
        c["margin"] = abs(c["value"] - found[0]["value"])
    return found


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
        self._design = (lib, netlist, linked, sdc_path)
        self._traces, self._log = {}, None
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
        cell = self.g.lib.cells[self._cells[inst]]
        return {"cell": cell.name, "sequential": cell.sequential,
                "pins": [{"name": p.name, "direction": p.direction, "clock": p.is_clock,
                          "function": p.function} for p in cell.pins]}

    def fanin(self, pin, check, rf):
        node, mode = self.g.by_name[pin], MODE[check]
        found = []
        for a in node.fanin:
            for rf_u, rf_v in a.pairs:
                at = a.src.at[mode][rf_u]
                if rf_v == rf and at is not None:
                    d = timer.arc_delay(a, mode, rf_u, rf)[0]
                    found.append({"from": a.src.name, "rf": rf_u, "kind": a.kind, "at": at,
                                  "delay": d, "value": at + d})
        return _merge(found, mode == "late")

    def fanout(self, pin, check, rf):
        node, mode = self.g.by_name[pin], MODE[check]
        found = []
        if node.slew[mode][rf] is not None:
            for a in node.fanout:
                for rf_u, rf_v in a.pairs:
                    rat = a.dst.rat[mode][rf_v]
                    if rf_u == rf and rat is not None:
                        d = timer.arc_delay(a, mode, rf, rf_v)[0]
                        found.append({"to": a.dst.name, "rf": rf_v, "kind": a.kind, "rat": rat,
                                      "delay": d, "value": rat - d})
        return _merge(found, mode == "early")

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
        nets = sum(1 for a in n.fanout if a.kind == "net")
        return {"pin": n.name, "kind": n.kind, "cell": n.cell, "at": n.at, "rat": n.rat,
                "slew": n.slew, "slack": slack, "load": n.load if nets else None,
                "fanout": nets or None}

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

    def arc_lookup(self, from_pin, to_pin, check, rf_from, rf_to):
        """The delay and transition lookups of the cell / ckq arc from_pin -> to_pin at the
        arguments timer.arc_delay uses; of several such arcs, the one whose delay gives the
        arrival (late largest, early smallest; ties to the first)."""
        node, mode = self.g.by_name[to_pin], MODE[check]
        found = []
        for a in node.fanin:
            if a.src.name == from_pin and a.tables is not None and (rf_from, rf_to) in a.pairs \
                    and a.src.slew[mode][rf_from] is not None:
                delay, transition = a.tables[rf_to]
                args = {"input_net_transition": a.src.slew[mode][rf_from],
                        "total_output_net_capacitance": node.load}
                found.append({"delay": lookup.lookup_detail(delay, args),
                              "slew": lookup.lookup_detail(transition, args)})
        if not found:
            return None
        best = (max if mode == "late" else min)(d["delay"]["value"] for d in found)
        return [d for d in found if d["delay"]["value"] == best][0]

    def trace(self, endpoint):
        """R41: the entries `trace.format_trace` prints for `endpoint`, in log order. The
        design is timed once more with a log (the first time a trace is asked for)."""
        if endpoint not in self._traces:
            if self._log is None:
                self._log = []
                self._trace_g = design.timed(*self._design, log=self._log)
            log = list(self._log)
            e = trace.collect(self._trace_g, endpoint, log)
            cone = {n.name for n in bundle._cone(e, float("inf"))}
            keep = dict((phase, endpoint_only) for phase, _, endpoint_only in trace.SECTIONS)
            self._traces[endpoint] = [x for x in log
                                      if (x["pin"] == endpoint if keep[x["phase"]] else x["pin"] in cone)]
        return self._traces[endpoint]

    def check_lookup(self, pin, check, rf):
        """The setup / hold constraint lookup of D pin `pin` at (D slew, CK slew), as
        timer.check computes it (a later group of the same kind wins)."""
        node, mode = self.g.by_name[pin], MODE[check]
        found = None
        for c in node.checks:
            if c.kind == check and node.slew[mode][rf] is not None and c.ck.at[mode]["r"] is not None:
                found = lookup.lookup_detail(c.tables[rf], {"constrained_pin_transition": node.slew[mode][rf],
                                                           "related_pin_transition": c.ck.slew[mode]["r"]})
        return found


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
            raise P2Error(None, None, "bundle has no instances: write it again with --bundle")
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
        info = self.data["instances"][inst]
        return {"cell": info["cell"], "sequential": info.get("sequential", False),
                "pins": [dict({"function": None}, **p) for p in info["pins"]]}

    def fanin(self, pin, check, rf):
        mode = MODE[check]
        found = []
        for e in self.data["edges"]:
            if e["v"] != pin or e["kind"] == "check" or e["u"] not in self.nodes:
                continue
            for rf_u in ("r", "f"):
                d, at = e["delay"][mode][rf_u + rf], self.nodes[e["u"]]["at"][mode][rf_u]
                if d is not None and at is not None:
                    found.append({"from": e["u"], "rf": rf_u, "kind": e["kind"], "at": at,
                                  "delay": d, "value": at + d})
        return _merge(found, mode == "late")

    def fanout(self, pin, check, rf):
        mode = MODE[check]
        found = []
        for e in self.data["edges"]:
            if e["u"] != pin or e["kind"] == "check" or e["v"] not in self.nodes:
                continue
            for rf_v in ("r", "f"):
                d, rat = e["delay"][mode][rf + rf_v], self.nodes[e["v"]]["rat"][mode][rf_v]
                if d is not None and rat is not None:
                    found.append({"to": e["v"], "rf": rf_v, "kind": e["kind"], "rat": rat,
                                  "delay": d, "value": rat - d})
        return _merge(found, mode == "early")

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
                "rat": n["rat"], "slew": n["slew"], "slack": n["slack"], "load": n["cap"],
                "fanout": n.get("fanout")}      # only if the bundle carries it (its edges stop at the cone)

    def arcs(self, inst):
        return [{"from": e["u"], "to": e["v"], "kind": e["kind"], "delay": e["delay"]}
                for e in self.data["edges"]
                if e["kind"] in ("cell", "ckq") and e["v"].split("/")[0] == inst and "/" in e["v"]]

    def arc_lookup(self, from_pin, to_pin, check, rf_from, rf_to):
        return None                     # a bundle holds delays, not tables

    def check_lookup(self, pin, check, rf):
        return None

    def trace(self, endpoint):
        return None                     # R41: engine mode only
