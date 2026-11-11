"""Viewer data sources without Tk (R28, viewer_p4.md): the in-process engine, one saved
bundle (bundle_v1.md), or a report_timing text (R55, ptreport.py). All answer the same
questions, so model.py and app.py never ask which one they have:

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
import os
import re

from sta_toy import P2Error, bundle, design, lookup, paths, ptreport, timer, trace

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
        # R56: drivers from the netlist's nets, so an ideal clock net (left out of the timing
        # graph, R50) still has one and the clock view can trace it.
        self._drivers = dict((e.dst, n.name) for n in linked.nodes for e in n.edges if e.kind == "net")
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

    def cells(self):
        """R53: the names of the cells the design uses."""
        return sorted(set(self._cells.values()))

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
        return self._drivers.get(pin)

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

    def cells(self):
        """R53: the names of the cells of the bundle's instances."""
        return sorted(set(i["cell"] for i in self.data["instances"].values()))

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


class ReportSource:
    """R55: a report_timing text in PrimeTime's layout (ours from --format pt, or
    PrimeTime's). It holds only what a report shows: per endpoint its worst reported setup
    and hold path, and the cells and pins on the paths; no side inputs, no tables, no
    merges, no trace."""

    mode = "report"

    def __init__(self, path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            raise P2Error(None, None, "cannot read %s: %s" % (path, e.strerror or e))
        found = ptreport.parse(text, path)
        m = re.search(r"^\s*Design\s*:\s*(\S+)", text, re.M)
        self.design_name = m.group(1) if m else os.path.basename(path)
        self.by_end, self.nodes, self.insts, self.cell_arcs = {}, {}, {}, []
        for p in found:
            worst = self.by_end.setdefault(p["end"], {"setup": None, "hold": None})
            if worst[p["check"]] is None or p["slack"] < worst[p["check"]]["slack"]:
                worst[p["check"]] = p
        for p in found:
            self._add(p)
        setup = [p for p in found if p["check"] == "setup"]
        first = (setup or found)[0]
        self.clock_name = first["capture_clock"]
        self.period = (setup[0]["capture"]["clock_edge"] if setup else None) or 1.0

    def _add(self, p):
        mode = MODE[p["check"]]
        pts = p["points"]
        for k, q in enumerate(pts):
            n = self.nodes.setdefault(q["pin"], {"pin": q["pin"], "cell": q["cell"],
                                                 "at": {"late": {"r": None, "f": None}, "early": {"r": None, "f": None}},
                                                 "slew": {"late": {"r": None, "f": None}, "early": {"r": None, "f": None}},
                                                 "load": q["cap"], "driver": None,
                                                 "kind": "PI" if k == 0 and q["cell"] is None else "other"})
            n["at"][mode][q["rf"]] = q["at"]
            n["slew"][mode][q["rf"]] = q["slew"]
            if q["arc"] == "net" and k > 0:
                n["driver"] = pts[k - 1]["pin"]
            if q["arc"] in ("cell", "ckq"):
                self.cell_arcs.append((pts[k - 1]["pin"], q["pin"], q["arc"], mode, pts[k - 1]["rf"] + q["rf"], q["incr"]))
            if "/" in q["pin"] and q["cell"] is not None:
                out = q["arc"] in ("cell", "ckq")
                clock = k == 0 and p["launch"]["input_delay"] is None
                self._pin(q["pin"], q["cell"], "output" if out else "input", clock, sequential=clock)
        end = self.nodes[p["end"]]
        end["kind"] = "D" if p["capture"]["pin"] is not None else "PO"
        if p["capture"]["pin"] is not None:
            self._pin(p["capture"]["pin"], p["capture"]["cell"], "input", True, sequential=True)

    def _pin(self, pin, cell, direction, clock, sequential):
        inst, name = pin.split("/", 1)
        info = self.insts.setdefault(inst, {"cell": cell, "sequential": False, "pins": []})
        info["sequential"] = info["sequential"] or sequential
        if all(q["name"] != name for q in info["pins"]):
            info["pins"].append({"name": name, "direction": direction, "clock": clock, "function": None})

    def rows(self):
        return [{"pin": end, "kind": self.nodes[end]["kind"],
                 "setup_slack": w["setup"]["slack"] if w["setup"] else None,
                 "hold_slack": w["hold"]["slack"] if w["hold"] else None}
                for end, w in sorted(self.by_end.items())]

    def summary(self, check):
        return None

    def paths(self, endpoint):
        return dict(self.by_end.get(endpoint, {"setup": None, "hold": None}))

    def cells(self):
        return sorted(set(i["cell"] for i in self.insts.values()))

    def instance(self, inst):
        info = self.insts[inst]
        pins = sorted(info["pins"], key=lambda q: (q["direction"] != "input", not q["clock"], q["name"]))
        return {"cell": info["cell"], "sequential": info["sequential"], "pins": pins}

    def fanin(self, pin, check, rf):
        return []

    def fanout(self, pin, check, rf):
        return []

    def driver(self, pin):
        n = self.nodes.get(pin)
        return n["driver"] if n else None

    def arrival(self, pin, check):
        n = self.nodes.get(pin)
        return _worst(n["at"][MODE[check]], MODE[check]) if n else None

    def pin(self, name):
        n = self.nodes.get(name)
        if n is None:
            return None
        slack = dict((c, w[c]["slack"] if w[c] else None) for c, w in
                     ((c, self.by_end.get(name, {"setup": None, "hold": None})) for c in ("setup", "hold")))
        return {"pin": name, "kind": n["kind"], "cell": n["cell"], "at": n["at"],
                "rat": {"late": {"r": None, "f": None}, "early": {"r": None, "f": None}},
                "slew": n["slew"], "slack": slack, "load": n["load"], "fanout": None}

    def arcs(self, inst):
        found = {}
        for frm, to, kind, mode, pair, delay in self.cell_arcs:
            if to.split("/")[0] == inst:
                a = found.setdefault((frm, to), {"from": frm, "to": to, "kind": kind,
                                                 "delay": {"late": dict.fromkeys(PAIRS), "early": dict.fromkeys(PAIRS)}})
                a["delay"][mode][pair] = delay
        return list(found.values())

    def arc_lookup(self, from_pin, to_pin, check, rf_from, rf_to):
        return None                     # a report holds delays, not tables

    def check_lookup(self, pin, check, rf):
        return None

    def trace(self, endpoint):
        return None                     # R41: engine mode only
