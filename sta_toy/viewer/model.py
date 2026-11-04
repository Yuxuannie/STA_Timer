"""Viewer model without Tk (R28, viewer_p4.md "Model"): the endpoint table, the path
timeline, the cone layout and the node details, all from bundle_v1.md / json_v1.md data."""

from sta_toy import timer
from sta_toy.tsv import fmt4

COLUMNS = ("pin", "kind", "setup_slack", "hold_slack")


class EndpointTable:
    """Endpoint rows {pin, kind, setup_slack, hold_slack} with sort, filter and paging."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.column, self.descending, self.text = "pin", False, ""

    @classmethod
    def from_graph(cls, g):
        """Rows of a timed graph: the slack at the worst transition, None if undefined."""
        rows = []
        for e in g.endpoints:
            row = {"pin": e.name, "kind": e.kind}
            for check in ("setup", "hold"):
                rf = timer.worst_rf(e, check)
                row[check + "_slack"] = None if rf is None else timer.slack(e, check, rf)
            rows.append(row)
        return cls(rows)

    @classmethod
    def from_bundle(cls, b):
        """The one row of a bundle: its endpoint node's own slacks."""
        node = [n for n in b["nodes"] if n["pin"] == b["endpoint"]][0]
        return cls([{"pin": node["pin"], "kind": node["kind"],
                     "setup_slack": node["slack"]["setup"], "hold_slack": node["slack"]["hold"]}])

    def sort(self, column, descending=False):
        self.column, self.descending = column, descending

    def filter(self, text):
        self.text = text

    def view(self):
        """All rows after filter and sort: None last in either direction, ties by pin."""
        text = self.text.lower()
        rows = sorted((r for r in self.rows if text in r["pin"].lower()), key=lambda r: r["pin"])
        known = [r for r in rows if r[self.column] is not None]
        known.sort(key=lambda r: r[self.column], reverse=self.descending)  # stable: pin order kept
        return known + [r for r in rows if r[self.column] is None]

    def page(self, n, size=50):
        return self.view()[n * size:(n + 1) * size]

    def pages(self, size=50):
        return max(1, (len(self.view()) + size - 1) // size)


def timeline(path, width, margin=40):
    """Drawing items {kind, x0, x1, label} of one json_v1.md path object (x in pixels)."""
    launch, cap = path["launch"], path["capture"]
    latency = cap["latency"] or 0.0
    times = [p["at"] for p in path["points"]]
    lo = min([0.0, launch["clock_edge"], path["required"], cap["clock_edge"] + latency] + times)
    hi = max(cap["clock_edge"] + latency, path["required"], path["arrival"])
    scale = (width - 2 * margin) / (hi - lo) if hi > lo else 0.0

    def item(kind, t0, t1, label):
        return {"kind": kind, "x0": margin + (t0 - lo) * scale, "x1": margin + (t1 - lo) * scale,
                "label": label}

    items = [item("launch_edge", launch["clock_edge"], launch["clock_edge"],
                  "launch edge %s" % fmt4(launch["clock_edge"])),
             item("capture_edge", cap["clock_edge"], cap["clock_edge"],
                  "capture edge %s" % fmt4(cap["clock_edge"])),
             item("arrival", path["arrival"], path["arrival"], "arrival %s" % fmt4(path["arrival"])),
             item("required", path["required"], path["required"],
                  "required %s" % fmt4(path["required"])),
             item("data", times[0], path["arrival"],
                  "data %s -> %s" % (fmt4(times[0]), fmt4(path["arrival"])))]
    if cap["pin"] is not None:
        if path["check"] == "setup":
            t0, t1 = path["required"], cap["clock_edge"] + latency
        else:
            t0, t1 = latency, path["required"]
        items.append(item("window", t0, t1, "%s window %s -> %s" % (path["check"], fmt4(t0), fmt4(t1))))
    return items


def _spread(n, lo, hi):
    """n positions evenly spaced from lo to hi (one in the middle)."""
    if n == 1:
        return [(lo + hi) / 2.0]
    return [lo + i * (hi - lo) / (n - 1) for i in range(n)]


def cone_layout(bundle, width, height, margin=40):
    """{"nodes": {pin: (x, y)}, "edges": [(u, v, kind, on_path)], "path_pins": set}."""
    columns = {}
    for n in bundle["nodes"]:
        columns.setdefault(n["depth"], []).append(n["pin"])
    deepest = max(columns)
    xs = [width - margin] if deepest == 0 else _spread(deepest + 1, width - margin, margin)
    nodes = {}
    for depth, pins in columns.items():
        for pin, y in zip(sorted(pins), _spread(len(pins), margin, height - margin)):
            nodes[pin] = (xs[depth], y)
    steps, path_pins = set(), set()
    for p in bundle["paths"]:
        pins = [q["pin"] for q in p["points"]]
        path_pins.update(pins)
        steps.update(zip(pins, pins[1:]))
    edges = [(e["u"], e["v"], e["kind"], (e["u"], e["v"]) in steps) for e in bundle["edges"]]
    return {"nodes": nodes, "edges": edges, "path_pins": path_pins}


def _cell(v):
    return fmt4(v).rjust(10)


def node_details(bundle, pin):
    """Text lines for one bundle node: kind, cell, depth, cap, AT / RAT / SLEW, slacks."""
    n = [n for n in bundle["nodes"] if n["pin"] == pin][0]
    lines = ["kind: %s" % n["kind"], "cell: %s" % (n["cell"] or "-"), "depth: %d" % n["depth"],
             "cap: %s" % fmt4(n["cap"]),
             "".ljust(6) + "".join(c.rjust(10) for c in ("late r", "late f", "early r", "early f"))]
    for key in ("at", "rat", "slew"):
        lines.append(key.upper().ljust(6) + "".join(_cell(n[key][m][rf])
                                                    for m in timer.MODES for rf in ("r", "f")))
    lines.append("setup slack: %s" % fmt4(n["slack"]["setup"]))
    lines.append("hold slack: %s" % fmt4(n["slack"]["hold"]))
    return lines
