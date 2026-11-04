"""Stage P2 timer (p2_semantics.md). R12: the timing graph; R13: the SDC checks against the design."""

from sta_toy import P2Error

MODES = ("late", "early")
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
    `load` is LOAD() of the net it drives."""

    def __init__(self, name, kind, cap):
        self.name = name
        self.kind = kind
        self.cap = cap
        self.load = 0.0
        self.fanin = []
        self.fanout = []
        self.checks = []
        self.at = _per_mode()
        self.slew = _per_mode()
        self.rat = _per_mode()
        self.pred = _per_mode()


class Arc:
    """A net edge (tables None: delay 0, slew copied) or the arc of one timing() group,
    whose tables map the output rf to its (delay, transition) tables."""

    def __init__(self, src, dst, pairs, tables):
        self.src = src
        self.dst = dst
        self.pairs = pairs
        self.tables = tables


class Check:
    """A setup_rising / hold_rising group on a D pin; tables map the D rf to its constraint table."""

    def __init__(self, kind, ck, tables):
        self.kind = kind
        self.ck = ck
        self.tables = tables


class TimingGraph:
    def __init__(self):
        self.nodes = []
        self.by_name = {}

    def add_arc(self, src, dst, pairs, tables):
        arc = Arc(src, dst, pairs, tables)
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
        node = Node(n.name, kind, cap)
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
            continue
        driver.load = sum(s.cap for s in sinks)
        for sink in sinks:
            g.add_arc(driver, sink, (("r", "r"), ("f", "f")), None)

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
                elif timing.timing_type != "combinational":
                    fail("unsupported timing_type %s" % timing.timing_type)
                elif timing.timing_sense not in SENSE_PAIRS:
                    fail("unsupported timing_sense %s" % (timing.timing_sense or "(none)"))
                else:
                    pairs = SENSE_PAIRS[timing.timing_sense]
                tables = {rf: (_table(timing, DELAY_TABLES[rf][0], DELAY_VARS, fail),
                               _table(timing, DELAY_TABLES[rf][1], DELAY_VARS, fail))
                          for rf in sorted(set(out for _, out in pairs))}
                for src in srcs:
                    g.add_arc(src, dst, pairs, tables)
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
