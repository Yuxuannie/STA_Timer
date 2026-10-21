"""Pin-level timing graph (R4)."""


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
