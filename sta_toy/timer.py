"""Stage P2 timer (p2_semantics.md). R12: the timing graph; R13: the SDC checks against the
design; R14: the clock model; R15: forward propagation; R16: endpoint checks;
R17: backward propagation; R18: slack, worst transition and paths."""

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
    (None for a port)."""

    def __init__(self, name, kind, cap, cell=None):
        self.name = name
        self.kind = kind
        self.cap = cap
        self.cell = cell
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
    type); `clocked` is the set of CK nodes on the clock port's net (check_timing.md)."""

    def __init__(self):
        self.nodes = []
        self.by_name = {}
        self.endpoints = []
        self.sdc = None
        self.ignored = {}
        self.clocked = set()

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


def build(linked, netlist, lib, clock_port, port_loads):
    """Timing graph of a linked stage 1 design (§1-§3). Only the stage 1 net edges are
    reused; cell arcs come from the timing() groups, and the clock net is left out."""
    g = TimingGraph()
    for n in linked.nodes:
        if n.kind in ("PI", "PO"):
            kind = "clock_port" if n.name == clock_port else n.kind
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
        if driver.kind == "clock_port":
            for sink in sinks:
                if sink.kind != "CK":
                    raise P2Error(netlist.file, _connection_line(netlist, sink.name),
                                  "clock port %s drives a non-clock pin %s"
                                  % (driver.name, sink.name))
            g.clocked.update(sinks)
            continue
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
    return g


def check_sdc(sdc, netlist, lib):
    """Semantic SDC errors (sdc_subset.md "Errors"), in file order."""

    def error(line, message):
        raise P2Error(sdc.file, line, message)

    if sdc.clock_name is None:
        error(sdc.last_line, "no create_clock in the file")
    pins, clock_pins = set(), set()
    for inst in netlist.instances:
        for pin in lib.cells[inst.cell].pins:
            pins.add(inst.name + "/" + pin.name)
            if pin.is_clock:
                clock_pins.add(inst.name + "/" + pin.name)
    inputs, outputs = set(netlist.inputs), set(netlist.outputs)
    for line, cmd, kind, name in sdc.objects:
        if kind == "get_clocks":
            if name != sdc.clock_name:
                error(line, "clock %s does not exist" % name)
        elif kind == "get_pins":
            if name not in pins:
                error(line, "pin %s does not exist" % name)
            if name not in clock_pins:
                error(line, "pin %s is not a clock pin" % name)
        elif name not in inputs and name not in outputs:
            error(line, "port %s does not exist" % name)
        elif cmd == "create_clock" and name in outputs:
            error(line, "create_clock on output port %s" % name)
        elif (cmd in ("set_input_delay", "set_input_transition", "set_load")
              and name == sdc.clock_port):
            error(line, "%s on the clock port %s" % (cmd, name))
        elif cmd in ("set_input_delay", "set_input_transition") and name in outputs:
            error(line, "%s on output port %s" % (cmd, name))
        elif cmd in ("set_output_delay", "set_load") and name in inputs:
            error(line, "%s on input port %s" % (cmd, name))


def run(linked, netlist, lib, sdc, grid=None):
    """Everything after parsing, in the error order of §10; returns the timed graph.
    `grid`, if a list, receives every lookup of forward, check and backward
    (check_timing.md §7)."""
    check_sdc(sdc, netlist, lib)
    g = build(linked, netlist, lib, sdc.clock_port, sdc.load)
    g.sdc = sdc
    order = topological_order(g)
    set_sources(g, sdc)
    forward(g, order, grid=grid)
    g.endpoints = check(g, sdc, grid=grid)
    backward(g, order, g.endpoints, grid=grid)
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


def clock_latency(sdc, pin):
    """R14: pin-level latency wins over the clock-level value, whatever the line order."""
    return sdc.pin_latency.get(pin, sdc.clock_latency)


def set_sources(g, sdc):
    """§5: PIs from set_input_delay / set_input_transition, CK pins from the ideal clock."""
    for n in g.nodes:
        if n.kind == "PI":
            delay = sdc.input_delay.get(n.name, {})
            for rf in ("r", "f"):
                n.at["late"][rf] = delay.get("max", 0.0)
                n.at["early"][rf] = delay.get("min", 0.0)
                for mode in MODES:
                    n.slew[mode][rf] = sdc.input_transition.get(n.name, 0.0)
        elif n.kind == "CK":
            for mode in MODES:
                n.at[mode]["r"] = clock_latency(sdc, n.name)
                n.slew[mode]["r"] = sdc.clock_transition


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


def forward(g, order, grid=None):
    """§6: AT is the max (late) / min (early) over incoming arcs, ties to the first
    candidate by (source name, r before f); SLEW is the worst over all arcs."""
    for v in order:
        if v.kind in ("PI", "CK", "clock_port"):
            continue
        for mode in MODES:
            for rf in ("r", "f"):
                cands = []
                for arc in v.fanin:
                    for rf_u, rf_v in arc.pairs:
                        at = arc.src.at[mode][rf_u]
                        if rf_v == rf and at is not None:
                            delay, slew = arc_delay(arc, mode, rf_u, rf, grid)
                            cands.append((arc.src.name, RF_RANK[rf_u], at + delay, slew, (arc.src, rf_u)))
                if not cands:
                    continue
                cands.sort(key=lambda c: c[:2])
                best = cands[0]
                for c in cands[1:]:
                    if (c[2] > best[2] + TOL) if mode == "late" else (c[2] < best[2] - TOL):
                        best = c
                v.at[mode][rf] = best[2]
                v.pred[mode][rf] = best[4]
                v.slew[mode][rf] = (max if mode == "late" else min)(c[3] for c in cands)


def check(g, sdc, grid=None):
    """§7: required times of the D pins (constraint tables at D slew x CK slew) and of the
    output ports with set_output_delay. Returns the endpoints."""
    endpoints = []
    for n in g.nodes:
        if n.kind == "D":
            for c in n.checks:
                mode = "late" if c.kind == "setup" else "early"
                ck_at, ck_slew = c.ck.at[mode]["r"], c.ck.slew[mode]["r"]
                for rf in ("r", "f"):
                    if n.slew[mode][rf] is None or ck_at is None:
                        continue
                    t = _lookup(c.tables[rf], CHECK_TABLES[rf],
                                {"constrained_pin_transition": n.slew[mode][rf],
                                 "related_pin_transition": ck_slew}, grid)
                    if c.kind == "setup":
                        n.rat["late"][rf] = ck_at + sdc.period - t - sdc.uncertainty["setup"]
                    else:
                        n.rat["early"][rf] = ck_at + t + sdc.uncertainty["hold"]
            endpoints.append(n)
        elif n.kind == "PO" and n.name in sdc.output_delay:
            delay = sdc.output_delay[n.name]
            for rf in ("r", "f"):
                if "max" in delay:
                    n.rat["late"][rf] = sdc.period - delay["max"]
                if "min" in delay:
                    n.rat["early"][rf] = 0.0 - delay["min"]
            endpoints.append(n)
    return endpoints


def backward(g, order, endpoints, grid=None):
    """§8: RAT is the min (late) / max (early) over outgoing arc pairs of RAT(v) - delay,
    the delay taken with this node's slew; endpoints keep their RAT from §7."""
    ends = set(endpoints)
    for u in reversed(order):
        if u in ends:
            continue
        for mode in MODES:
            for rf in ("r", "f"):
                if u.slew[mode][rf] is None:
                    continue
                cands = [arc.dst.rat[mode][rf_v] - _delay_only(arc, mode, rf, rf_v, grid)
                         for arc in u.fanout for rf_u, rf_v in arc.pairs
                         if rf_u == rf and arc.dst.rat[mode][rf_v] is not None]
                if cands:
                    u.rat[mode][rf] = (min if mode == "late" else max)(cands)


def slack(node, kind, rf):
    """§9: setup slack = RAT[late] - AT[late], hold slack = AT[early] - RAT[early]; None if undefined."""
    if kind == "setup":
        a, b = node.rat["late"][rf], node.at["late"][rf]
    else:
        a, b = node.at["early"][rf], node.rat["early"][rf]
    return None if a is None or b is None else a - b


def worst_rf(node, kind):
    """The transition with the smaller slack, ties to r; None if neither slack is defined."""
    r, f = slack(node, kind, "r"), slack(node, kind, "f")
    if r is None and f is None:
        return None
    if r is None or (f is not None and f < r - TOL):
        return "f"
    return "r"


def worst_path(node, kind, rf):
    """(node, rf) pairs from the startpoint to (node, rf), following PRED in the check's mode."""
    mode = "late" if kind == "setup" else "early"
    path = [(node, rf)]
    while path[-1][0].pred[mode][path[-1][1]] is not None:
        path.append(path[-1][0].pred[mode][path[-1][1]])
    return path[::-1]
