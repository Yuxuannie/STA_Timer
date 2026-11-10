"""Stage P2 timer (p2_semantics.md). R12: the timing graph; R13: the SDC checks against the
design; R14: the clock model; R15: forward propagation; R16: endpoint checks;
R17: backward propagation; R18: slack, worst transition and paths. R50: clock networks
through cells, ideal or propagated; R51: several clocks."""

from fractions import Fraction

from sta_toy import P2Error, lookup

MODES = ("late", "early")
TOL = 1e-9
RF_RANK = {"r": 0, "f": 1}
DELAY_VARS = ("input_net_transition", "total_output_net_capacitance")
CHECK_VARS = ("constrained_pin_transition", "related_pin_transition")

# (input rf, output rf) pairs of a delay arc, by timing_sense for combinational arcs (§3).
SENSE_PAIRS = {
    "positive_unate": (("r", "r"), ("f", "f")),
    "negative_unate": (("r", "f"), ("f", "r")),
    "non_unate": (("r", "r"), ("r", "f"), ("f", "r"), ("f", "f")),
}
RISING_EDGE_PAIRS = (("r", "r"), ("r", "f"))
CHECK_KINDS = {"setup_rising": "setup", "hold_rising": "hold"}
# Tables chosen by the output transition of a delay arc, or the D transition of a check.
DELAY_TABLES = {"r": ("cell_rise", "rise_transition"), "f": ("cell_fall", "fall_transition")}
CHECK_TABLES = {"r": "rise_constraint", "f": "fall_constraint"}


def _per_mode():
    return {m: {"r": None, "f": None} for m in MODES}


class Node:
    """kind is 'clock_port', 'PI', 'PO', 'CK', 'D' or 'other'. `cap` is what the node adds
    to the load of the net it sits on (pin capacitance, or set_load for an output port);
    `load` is LOAD() of the net it drives. `cell` is the cell name of an instance pin
    (None for a port). `clock` is the Clock whose network holds the node (R50);
    `launch_clock` the clock that launches from a PI or CK node, `capture_clock` and
    `capture_edges` ({"setup": t, "hold": t}) those an endpoint checks against (R51)."""

    def __init__(self, name, kind, cap, cell=None):
        self.name = name
        self.kind = kind
        self.cap = cap
        self.cell = cell
        self.clock = None
        self.launch_clock = None
        self.capture_clock = None
        self.capture_edges = None
        self.load = 0.0
        self.fanin = []
        self.fanout = []
        self.checks = []
        self.at = _per_mode()
        self.slew = _per_mode()
        self.rat = _per_mode()
        self.pred = _per_mode()


class Arc:
    """A net edge (kind 'net', tables None: delay 0, slew copied) or the arc of one timing()
    group (kind 'cell', or 'ckq' for rising_edge), whose tables map the output rf to its
    (delay, transition) tables."""

    def __init__(self, src, dst, pairs, tables, kind):
        self.src = src
        self.dst = dst
        self.pairs = pairs
        self.tables = tables
        self.kind = kind


class Check:
    """A setup_rising / hold_rising group on a D pin; tables map the D rf to its constraint table."""

    def __init__(self, kind, ck, tables):
        self.kind = kind
        self.ck = ck
        self.tables = tables


class TimingGraph:
    """`ignored` counts the timing() arcs build() skipped, per (cell, pin, related_pin,
    type); `clocked` maps each CK node a clock's network reaches to that Clock (R50;
    check_timing.md)."""

    def __init__(self):
        self.nodes = []
        self.by_name = {}
        self.endpoints = []
        self.sdc = None
        self.ignored = {}
        self.clocked = {}

    def add_arc(self, src, dst, pairs, tables, kind):
        arc = Arc(src, dst, pairs, tables, kind)
        src.fanout.append(arc)
        dst.fanin.append(arc)


def _connection_line(netlist, name):
    """Netlist line of a load: its `.PIN(` for an instance pin, its declaration for a port."""
    if "/" not in name:
        return netlist.decl_lines[name]
    inst, pin = name.split("/")
    for i in netlist.instances:
        if i.name == inst:
            return [c.line for c in i.conns if c.pin == pin][0]


def _table(timing, kind, variables, fail):
    table = timing.tables.get(kind)
    if table is None:
        fail("missing %s table" % kind)
    if (sorted(table.variables) != sorted(variables)
            or len(table.index_1) < 2 or len(table.index_2) < 2):
        fail("%s must be a 2-D table over %s" % (kind, " and ".join(variables)))
    return table


def build(linked, netlist, lib, sdc):
    """Timing graph of a linked stage 1 design (§1-§3). Only the stage 1 net edges are
    reused; cell arcs come from the timing() groups. R50: the clock networks are traced
    afterwards; an ideal one keeps none of its arcs, as P2 left the clock net out."""
    clock_ports = {c.port for c in sdc.clocks.values()}
    port_loads = sdc.load
    g = TimingGraph()
    for n in linked.nodes:
        if n.kind in ("PI", "PO"):
            kind = "clock_port" if n.name in clock_ports else n.kind
            cap = port_loads.get(n.name, 0.0) if n.kind == "PO" else None
        else:
            pin = lib.cells[n.cell].pin(n.name.split("/")[1])
            kind = "CK" if pin.is_clock else "other"
            cap = n.cap if n.kind == "input" else None
        node = Node(n.name, kind, cap, n.cell)
        g.nodes.append(node)
        g.by_name[n.name] = node

    for n in linked.nodes:
        driver = g.by_name[n.name]
        sinks = [g.by_name[e.dst] for e in n.edges if e.kind == "net"]
        driver.load = sum(s.cap for s in sinks)
        for sink in sinks:
            g.add_arc(driver, sink, (("r", "r"), ("f", "f")), None, "net")

    for inst in netlist.instances:
        cell = lib.cells[inst.cell]
        for pin in cell.pins:
            dst = g.by_name[inst.name + "/" + pin.name]
            for timing in pin.timings:
                def fail(message):
                    raise P2Error(cell.file, timing.line,
                                  "cell %s pin %s: %s" % (cell.name, pin.name, message))
                srcs = [g.by_name[inst.name + "/" + r] for r in timing.related_pins]
                if timing.timing_type in CHECK_KINDS:
                    tables = {rf: _table(timing, kind, CHECK_VARS, fail)
                              for rf, kind in CHECK_TABLES.items()}
                    dst.kind = "D"
                    dst.checks.extend(Check(CHECK_KINDS[timing.timing_type], src, tables)
                                      for src in srcs)
                    continue
                if timing.timing_type == "rising_edge":
                    pairs = RISING_EDGE_PAIRS
                elif (timing.timing_type == "combinational"
                      and timing.timing_sense in SENSE_PAIRS):
                    pairs = SENSE_PAIRS[timing.timing_sense]
                else:
                    # P5 (p2_semantics.md "Changes in P5"): ignored and counted, not an error.
                    what = timing.timing_type
                    if what == "combinational":
                        what = "combinational:%s" % (timing.timing_sense or "none")
                    for r in timing.related_pins:
                        key = (cell.name, pin.name, r, what)
                        g.ignored[key] = g.ignored.get(key, 0) + 1
                    continue
                tables = {rf: (_table(timing, DELAY_TABLES[rf][0], DELAY_VARS, fail),
                               _table(timing, DELAY_TABLES[rf][1], DELAY_VARS, fail))
                          for rf in sorted(set(out for _, out in pairs))}
                kind = "ckq" if timing.timing_type == "rising_edge" else "cell"
                for src in srcs:
                    g.add_arc(src, dst, pairs, tables, kind)
    networks = [(clock, _trace_clock(g, clock, netlist)) for clock in sdc.clocks.values()]
    for clock, network in networks:
        _keep_own_arcs(clock, network)
    return g


def _drop(arc):
    arc.src.fanout.remove(arc)
    arc.dst.fanin.remove(arc)


def _trace_clock(g, clock, netlist):
    """R50: the network of `clock`: every node its port reaches over net edges and cell
    arcs, stopping at clock pins (CK). Reaching a data pin or an output port, a node of
    another clock's network, or a cell arc that is not positive unate is an error."""

    def error(node, message):
        raise P2Error(netlist.file, _connection_line(netlist, node.name),
                      "clock %s %s" % (clock.name, message))

    port = g.by_name[clock.port]
    port.clock = clock
    network = [port]
    for u in network:
        if u.kind == "CK" and u is not port:
            g.clocked[u] = clock
            continue
        for arc in u.fanout:
            v = arc.dst
            if arc.kind != "net" and arc.pairs != SENSE_PAIRS["positive_unate"]:
                error(v, "goes through %s -> %s, which is not positive unate (not supported yet)"
                      % (u.name, v.name))
            if v.kind in ("D", "PO"):
                error(v, "reaches the data pin %s" % v.name)
            if v.clock is clock:
                continue
            if v.clock is not None:
                error(v, "and clock %s both reach %s" % (v.clock.name, v.name))
            v.clock = clock
            network.append(v)
    return network


def _keep_own_arcs(clock, network):
    """R50, once every network is traced: an ideal network keeps no arc (its CK pins are
    sources), a propagated one only the arcs between its own nodes."""
    inner = [n for n in network if n.kind != "CK"]
    for n in inner:
        for arc in list(n.fanin):
            if not clock.propagated or arc.src.clock is not clock:
                _drop(arc)
        if not clock.propagated:
            for arc in list(n.fanout):
                _drop(arc)


def check_sdc(sdc, netlist, lib):
    """Semantic SDC errors (sdc_subset.md "Errors"), in file order."""

    def error(line, message):
        raise P2Error(sdc.file, line, message)

    if not sdc.clocks:
        error(sdc.last_line, "no create_clock in the file")
    clock_ports = {c.port for c in sdc.clocks.values()}
    pins, clock_pins = set(), set()
    for inst in netlist.instances:
        for pin in lib.cells[inst.cell].pins:
            pins.add(inst.name + "/" + pin.name)
            if pin.is_clock:
                clock_pins.add(inst.name + "/" + pin.name)
    inputs, outputs = set(netlist.inputs), set(netlist.outputs)
    for line, cmd, kind, name in sdc.objects:
        if kind == "get_clocks":
            if name not in sdc.clocks:
                error(line, "clock %s does not exist" % name)
            if sdc.clocks[name].line > line:
                error(line, "clock %s is named before its create_clock" % name)
        elif kind == "get_pins":
            if name not in pins:
                error(line, "pin %s does not exist" % name)
            if name not in clock_pins:
                error(line, "pin %s is not a clock pin" % name)
        elif name not in inputs and name not in outputs:
            error(line, "port %s does not exist" % name)
        elif cmd == "create_clock" and name in outputs:
            error(line, "create_clock on output port %s" % name)
        elif cmd in ("set_input_delay", "set_load") and name in clock_ports:
            # set_input_transition on a clock port is allowed: the source slew of a
            # propagated clock (R50).
            error(line, "%s on the clock port %s" % (cmd, name))
        elif cmd in ("set_input_delay", "set_input_transition") and name in outputs:
            error(line, "%s on output port %s" % (cmd, name))
        elif cmd in ("set_output_delay", "set_load") and name in inputs:
            error(line, "%s on input port %s" % (cmd, name))


def run(linked, netlist, lib, sdc, grid=None, log=None):
    """Everything after parsing, in the error order of §10; returns the timed graph.
    `grid`, if a list, receives every lookup of forward, check and backward
    (check_timing.md §7); `log`, if a list, the engine log of trace.md."""
    check_sdc(sdc, netlist, lib)
    g = build(linked, netlist, lib, sdc)
    g.sdc = sdc
    order = topological_order(g)
    set_sources(g, sdc, log)
    forward(g, order, log, grid)
    edges = capture_edges(g, sdc)
    g.endpoints = check(g, sdc, edges, log, grid)
    backward(g, order, g.endpoints, log, grid)
    return g


def topological_order(g):
    """Nodes in topological order of net edges and timing() arcs; a cycle is an error."""
    indegree = {n: len(n.fanin) for n in g.nodes}
    order = [n for n in g.nodes if indegree[n] == 0]
    for n in order:
        for arc in n.fanout:
            indegree[arc.dst] -= 1
            if indegree[arc.dst] == 0:
                order.append(arc.dst)
    if len(order) < len(g.nodes):
        # Every node left has a predecessor that is also left: walk back until one repeats.
        left = set(g.nodes) - set(order)
        walk = [[n for n in g.nodes if n in left][0]]
        while walk.count(walk[-1]) < 2:
            walk.append([a.src for a in walk[-1].fanin if a.src in left][0])
        loop = walk[walk.index(walk[-1]):][::-1]
        raise P2Error(None, None, "combinational loop: " + " -> ".join(n.name for n in loop))
    return order


def clock_latency(sdc, pin, clock=None):
    """R14: pin-level latency wins over the clock-level value, whatever the line order.
    `clock` is the pin's clock (R51; default the first)."""
    return sdc.pin_latency.get(pin, (clock or _first(sdc)).latency)


def _first(sdc):
    return next(iter(sdc.clocks.values()))


def is_source(n):
    """PIs, clock ports and the CK pins of ideal clocks take their values from the SDC;
    every other node, the CK pins of a propagated clock included, from its fanin (R50)."""
    if n.kind == "CK":
        return n.clock is None or not n.clock.propagated
    return n.kind in ("PI", "clock_port")


def set_sources(g, sdc, log=None):
    """§5: PIs from set_input_delay / set_input_transition, CK pins from the ideal clock.
    R50: a propagated clock's port rises at 0 and falls at half the period, with the
    port's set_input_transition as its slew; its latency and transition are not used.
    A CK pin that no clock reaches is clocked by the first clock, ideally (P2's rule);
    so is a PI without set_input_delay (R51)."""
    first = _first(sdc)
    for n in g.nodes:
        if n.kind == "PI":
            delay = sdc.input_delay.get(n.name, {})
            n.launch_clock = sdc.clocks.get(sdc.input_clock.get(n.name), first)
            for rf in ("r", "f"):
                n.at["late"][rf] = delay.get("max", 0.0)
                n.at["early"][rf] = delay.get("min", 0.0)
                for mode in MODES:
                    n.slew[mode][rf] = sdc.input_transition.get(n.name, 0.0)
        elif n.kind == "clock_port" and n.clock.propagated:
            for mode in MODES:
                n.at[mode]["r"], n.at[mode]["f"] = 0.0, n.clock.period / 2.0
                for rf in ("r", "f"):
                    n.slew[mode][rf] = sdc.input_transition.get(n.name, 0.0)
        elif n.kind == "CK":
            n.launch_clock = n.clock or first
            if not is_source(n):
                continue
            for mode in MODES:
                n.at[mode]["r"] = clock_latency(sdc, n.name, n.launch_clock)
                n.slew[mode]["r"] = n.launch_clock.transition
        else:
            continue
        if log is not None:
            for mode in MODES:
                for rf in ("r", "f"):
                    if n.at[mode][rf] is not None:
                        log.append({"phase": "forward", "pin": n.name, "mode": mode, "rf": rf,
                                    "at": n.at[mode][rf], "slew": n.slew[mode][rf],
                                    "candidates": [], "winner": None,
                                    "source": "input" if n.kind == "PI" else "clock"})


def _lookup(table, kind, args, grid):
    """lookup.lookup(); with a `grid` list, through lookup_detail, recording
    (table kind, table, detail)."""
    if grid is None:
        return lookup.lookup(table, args)
    detail = lookup.lookup_detail(table, args)
    grid.append((kind, table, detail))
    return detail["value"]


def _delay_args(arc, mode, rf_in):
    return {"input_net_transition": arc.src.slew[mode][rf_in],
            "total_output_net_capacitance": arc.dst.load}


def arc_delay(arc, mode, rf_in, rf_out, grid=None):
    """Delay and output slew of one arc pair, with the source's slew in `mode` (§3)."""
    slew = arc.src.slew[mode][rf_in]
    if arc.tables is None:
        return 0.0, slew
    delay, transition = arc.tables[rf_out]
    args = _delay_args(arc, mode, rf_in)
    kinds = DELAY_TABLES[rf_out]
    return _lookup(delay, kinds[0], args, grid), _lookup(transition, kinds[1], args, grid)


def _delay_only(arc, mode, rf_in, rf_out, grid):
    """arc_delay()[0] without the transition lookup (backward needs only the delay)."""
    if arc.tables is None:
        return 0.0
    return _lookup(arc.tables[rf_out][0], DELAY_TABLES[rf_out][0],
                   _delay_args(arc, mode, rf_in), grid)


def forward(g, order, log=None, grid=None):
    """§6: AT is the max (late) / min (early) over incoming arcs, ties to the first
    candidate by (source name, r before f); SLEW is the worst over all arcs."""
    for v in order:
        if is_source(v):
            continue
        for mode in MODES:
            for rf in ("r", "f"):
                cands = []
                for arc in v.fanin:
                    for rf_u, rf_v in arc.pairs:
                        at = arc.src.at[mode][rf_u]
                        if rf_v == rf and at is not None:
                            delay, slew = arc_delay(arc, mode, rf_u, rf, grid)
                            cands.append((arc.src.name, RF_RANK[rf_u], at + delay, slew,
                                          (arc.src, rf_u), at, delay))
                if not cands:
                    continue
                cands.sort(key=lambda c: c[:2])
                w = 0
                for k in range(1, len(cands)):
                    c, best = cands[k], cands[w]
                    if (c[2] > best[2] + TOL) if mode == "late" else (c[2] < best[2] - TOL):
                        w = k
                best = cands[w]
                v.at[mode][rf] = best[2]
                v.pred[mode][rf] = best[4]
                v.slew[mode][rf] = (max if mode == "late" else min)(c[3] for c in cands)
                if log is not None:
                    log.append({"phase": "forward", "pin": v.name, "mode": mode, "rf": rf,
                                "at": v.at[mode][rf], "slew": v.slew[mode][rf],
                                "candidates": [{"src": c[0], "rf": c[4][1], "at": c[5],
                                                "delay": c[6], "value": c[2], "slew": c[3]}
                                               for c in cands],
                                "winner": w, "source": None})


# R51: launch and capture edges are paired over at most this many launch periods.
MAX_EDGES = 10000


def edge_pair(launch, capture):
    """R51: (setup, hold) capture edge times for data launched at 0 by clock `launch` and
    captured by clock `capture`, both rising at 0 and every period. Over their common
    period, each launch edge pairs with the first capture edge after it for setup and with
    the last capture edge at or before it for hold; setup takes the smallest gap, hold the
    largest, as OpenSTA does (checked on nine period pairs)."""
    lp, cp = Fraction(repr(launch.period)), Fraction(repr(capture.period))
    count = (lp / cp).denominator
    if count > MAX_EDGES:
        raise P2Error(None, None, "clocks %s and %s have no common period within %d periods"
                      % (launch.name, capture.name, MAX_EDGES))
    setup = hold = None
    for k in range(count):
        e_l = k * lp
        e_c = (e_l // cp + 1) * cp
        s, h = e_c - e_l, (e_l // cp) * cp - e_l
        setup = s if setup is None else min(setup, s)
        hold = h if hold is None else max(hold, h)
    return float(setup), float(hold)


def capture_edges(g, sdc):
    """R51: {capture clock name: {"setup": t, "hold": t}} for every clock an endpoint
    checks against. One forward pass serves all launching clocks only when they pair with
    each capture clock at the same edges; otherwise this is an error (a pass per launching
    clock is not built yet)."""
    launch = []
    for n in g.nodes:
        if n.launch_clock is not None and n.launch_clock not in launch:
            launch.append(n.launch_clock)
    capture = []
    for n in g.nodes:
        if n.kind == "D":
            capture += [c.ck.launch_clock for c in n.checks]
        elif n.kind == "PO" and n.name in sdc.output_delay:
            capture.append(sdc.clocks[sdc.output_clock[n.name]])
    edges = {}
    for cap in capture:
        if cap.name in edges:
            continue
        pairs = [(clock, edge_pair(clock, cap)) for clock in launch or [_first(sdc)]]
        for clock, pair in pairs[1:]:
            if pair != pairs[0][1]:
                raise P2Error(None, None, "clocks %s and %s launch data that clock %s captures "
                              "at different edges (setup/hold %s and %s); one propagation "
                              "per launching clock is not supported yet"
                              % (pairs[0][0].name, clock.name, cap.name,
                                 "/".join(map(fmt, pairs[0][1])), "/".join(map(fmt, pair))))
        edges[cap.name] = {"setup": pairs[0][1][0], "hold": pairs[0][1][1]}
    return edges


def fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def check(g, sdc, edges, log=None, grid=None):
    """§7: required times of the D pins (constraint tables at D slew x CK slew) and of the
    output ports with set_output_delay. Returns the endpoints. R51: against the capture
    clock's edge from `edges` and that clock's uncertainty."""
    endpoints = []
    for n in g.nodes:
        if n.kind == "D":
            for c in n.checks:
                mode = "late" if c.kind == "setup" else "early"
                clock = c.ck.launch_clock
                n.capture_clock, n.capture_edges = clock, edges[clock.name]
                edge = n.capture_edges[c.kind]
                ck_at, ck_slew = c.ck.at[mode]["r"], c.ck.slew[mode]["r"]
                for rf in ("r", "f"):
                    if n.slew[mode][rf] is None or ck_at is None:
                        continue
                    t = _lookup(c.tables[rf], CHECK_TABLES[rf],
                                {"constrained_pin_transition": n.slew[mode][rf],
                                 "related_pin_transition": ck_slew}, grid)
                    if c.kind == "setup":
                        n.rat["late"][rf] = ck_at + edge - t - clock.uncertainty["setup"]
                    else:
                        n.rat["early"][rf] = ck_at + edge + t + clock.uncertainty["hold"]
                    if log is not None:
                        log.append({"phase": "check", "pin": n.name, "kind": c.kind, "rf": rf,
                                    "ck": c.ck.name, "d_slew": n.slew[mode][rf],
                                    "ck_slew": ck_slew, "t": t, "ck_at": ck_at,
                                    "period": n.capture_edges["setup"], "edge": edge,
                                    "uncertainty": clock.uncertainty[c.kind],
                                    "output_delay": None, "rat": n.rat[mode][rf]})
            endpoints.append(n)
        elif n.kind == "PO" and n.name in sdc.output_delay:
            delay = sdc.output_delay[n.name]
            clock = sdc.clocks[sdc.output_clock[n.name]]
            n.capture_clock, n.capture_edges = clock, edges[clock.name]
            for rf in ("r", "f"):
                if "max" in delay:
                    n.rat["late"][rf] = n.capture_edges["setup"] - delay["max"]
                if "min" in delay:
                    n.rat["early"][rf] = n.capture_edges["hold"] - delay["min"]
                if log is not None:
                    for facet, kind, mode in (("max", "setup", "late"), ("min", "hold", "early")):
                        if facet in delay:
                            log.append({"phase": "check", "pin": n.name, "kind": kind, "rf": rf,
                                        "ck": None, "d_slew": None, "ck_slew": None, "t": None,
                                        "ck_at": None, "period": n.capture_edges["setup"],
                                        "edge": n.capture_edges[kind],
                                        "uncertainty": None, "output_delay": delay[facet],
                                        "rat": n.rat[mode][rf]})
            endpoints.append(n)
    return endpoints


def backward(g, order, endpoints, log=None, grid=None):
    """§8: RAT is the min (late) / max (early) over outgoing arc pairs of RAT(v) - delay,
    the delay taken with this node's slew; endpoints keep their RAT from §7."""
    ends = set(endpoints)
    for u in reversed(order):
        # R50: no required time flows into a clock network.
        if u in ends or (u.clock is not None and u.kind != "CK"):
            continue
        for mode in MODES:
            for rf in ("r", "f"):
                if u.slew[mode][rf] is None:
                    continue
                steps = [(arc.dst, rf_v, _delay_only(arc, mode, rf, rf_v, grid))
                         for arc in u.fanout for rf_u, rf_v in arc.pairs
                         if rf_u == rf and arc.dst.rat[mode][rf_v] is not None]
                cands = [v.rat[mode][rf_v] - d for v, rf_v, d in steps]
                if cands:
                    u.rat[mode][rf] = (min if mode == "late" else max)(cands)
                    if log is not None:
                        log.append({"phase": "backward", "pin": u.name, "mode": mode, "rf": rf,
                                    "rat": u.rat[mode][rf],
                                    "candidates": [{"dst": v.name, "rf": rf_v,
                                                    "rat": v.rat[mode][rf_v], "delay": d,
                                                    "value": c}
                                                   for (v, rf_v, d), c in zip(steps, cands)],
                                    "winner": cands.index(u.rat[mode][rf])})


def slack(node, kind, rf, log=None):
    """§9: setup slack = RAT[late] - AT[late], hold slack = AT[early] - RAT[early]; None if undefined."""
    if kind == "setup":
        a, b = node.rat["late"][rf], node.at["late"][rf]
    else:
        a, b = node.at["early"][rf], node.rat["early"][rf]
    value = None if a is None or b is None else a - b
    if log is not None:
        mode = "late" if kind == "setup" else "early"
        log.append({"phase": "slack", "pin": node.name, "kind": kind, "rf": rf,
                    "at": node.at[mode][rf], "rat": node.rat[mode][rf], "slack": value})
    return value


def worst_rf(node, kind):
    """The transition with the smaller slack, ties to r; None if neither slack is defined."""
    r, f = slack(node, kind, "r"), slack(node, kind, "f")
    if r is None and f is None:
        return None
    if r is None or (f is not None and f < r - TOL):
        return "f"
    return "r"


def worst_path(node, kind, rf, log=None):
    """(node, rf) pairs from the startpoint to (node, rf), following PRED in the check's mode."""
    mode = "late" if kind == "setup" else "early"
    path = [(node, rf)]
    while path[-1][0].kind not in ("PI", "CK") and path[-1][0].pred[mode][path[-1][1]] is not None:
        path.append(path[-1][0].pred[mode][path[-1][1]])
    path = path[::-1]
    if log is not None:
        log.append({"phase": "path", "kind": kind, "pin": node.name, "rf": rf,
                    "points": [[n.name, p_rf] for n, p_rf in path]})
    return path
