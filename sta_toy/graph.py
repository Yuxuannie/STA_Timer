"""Pin-level timing graph (R4) and the linker that builds it from a netlist and a library (R5)."""

from sta_toy import StaError


class Edge:
    """kind is 'net' or 'cell'. A cell edge lists the distinct timing senses of its groups."""

    def __init__(self, src, dst, kind):
        self.src = src
        self.dst = dst
        self.kind = kind
        self.senses = []


class Node:
    """kind is 'PI', 'PO', 'input' or 'output'; cell and cap are set on instance pins."""

    def __init__(self, name, kind, cell, cap):
        self.name = name
        self.kind = kind
        self.cell = cell
        self.cap = cap
        self.edges = []


class Graph:
    """Nodes in insertion order, each holding its out-edges in insertion order."""

    def __init__(self, design, library, cap_unit):
        self.design = design
        self.library = library
        self.cap_unit = cap_unit
        self.nodes = []
        self._by_name = {}

    def node(self, name):
        return self._by_name[name]

    def add_node(self, name, kind, cell=None, cap=None):
        node = Node(name, kind, cell, cap)
        self.nodes.append(node)
        self._by_name[name] = node
        return node

    def add_net_edge(self, src, dst):
        self.node(src).edges.append(Edge(src, dst, "net"))

    def add_cell_edge(self, src, dst, sense):
        """Groups with the same (src, dst) share one edge; each new sense is appended."""
        edges = self.node(src).edges
        for edge in edges:
            if edge.kind == "cell" and edge.dst == dst:
                break
        else:
            edge = Edge(src, dst, "cell")
            edges.append(edge)
        if sense not in edge.senses:
            edge.senses.append(sense)


def link(netlist, lib):
    """Build the timing graph of `netlist` against `lib`. Errors point into the netlist file."""

    def error(line, message):
        raise StaError(netlist.file, line, message)

    g = Graph(netlist.name, lib.name, lib.cap_unit)
    for name in netlist.inputs:
        g.add_node(name, "PI")
    cells = []
    for inst in netlist.instances:
        cell = lib.cells.get(inst.cell)
        if cell is None:
            error(inst.line, "unknown cell %s (instance %s)" % (inst.cell, inst.name))
        for conn in inst.conns:
            if cell.pin(conn.pin) is None:
                error(conn.line, "unknown pin %s on cell %s (instance %s)"
                      % (conn.pin, cell.name, inst.name))
        for pin in cell.pins:
            g.add_node(inst.name + "/" + pin.name, pin.direction, cell.name, pin.capacitance)
        cells.append(cell)
    for name in netlist.outputs:
        g.add_node(name, "PO")

    for inst, cell in zip(netlist.instances, cells):
        for pin in cell.pins:
            for timing in pin.timings:
                for related in timing.related_pins:
                    g.add_cell_edge(inst.name + "/" + related, inst.name + "/" + pin.name,
                                    timing.timing_sense or "none")

    # Drivers and loads per net; loads in instance order, lib pin order, then PO ports.
    drivers, loads = {}, {}
    for name in netlist.inputs:
        drivers.setdefault(name, []).append(name)
    for inst, cell in zip(netlist.instances, cells):
        nets = {conn.pin: conn.net for conn in inst.conns}
        for pin in cell.pins:
            if pin.name in nets:
                side = drivers if pin.direction == "output" else loads
                side.setdefault(nets[pin.name], []).append(inst.name + "/" + pin.name)
    for name in netlist.outputs:
        loads.setdefault(name, []).append(name)

    # Every port is in drivers or loads; a wire only if it is connected.
    for net, line in netlist.decl_lines.items():
        if net in drivers or net in loads:
            count = len(drivers.get(net, []))
            if count == 0:
                error(line, "net %s has no driver" % net)
            if count > 1:
                error(line, "net %s has %d drivers: %s" % (net, count, ", ".join(drivers[net])))
    for net, sinks in loads.items():
        for sink in sinks:
            g.add_net_edge(drivers[net][0], sink)
    return g
