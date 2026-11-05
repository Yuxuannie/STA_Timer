"""Viewer model without Tk (R28, viewer_p4.md): the endpoint list, a path's stages pin to
pin, its capture rows, and the path schematic with cells drawn as modules on a grid."""

from sta_toy.tsv import fmt4

MODE = {"setup": "late", "hold": "early"}

# Schematic grid (pixels at zoom 1).
W_MOD, W_PORT, H_PORT = 132, 60, 28
GAP, PITCH, HEAD, PAD = 120, 28, 30, 10
LANE_GAP, STUB, MARGIN_X, MARGIN_Y = 46, 22, 110, 60


class EndpointList:
    """Rows {pin, kind, setup_slack, hold_slack}: worst first for the current check
    (undefined slack last, ties by pin), filtered by a case-insensitive substring."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.check = "setup"
        self.text = ""

    def view(self):
        key = self.check + "_slack"
        rows = [r for r in self.rows if self.text.lower() in r["pin"].lower()]
        return sorted(rows, key=lambda r: (r[key] is None, r[key] or 0.0, r["pin"]))

    def neighbour(self, pin, step):
        """The pin `step` rows away from `pin` in view(), wrapping; the first shown row if
        `pin` is not shown; None if nothing is shown."""
        pins = [r["pin"] for r in self.view()]
        if not pins:
            return None
        if pin not in pins:
            return pins[0]
        return pins[(pins.index(pin) + step) % len(pins)]


def _short(pin):
    return pin.split("/")[-1]


def stages(path):
    """One row per path point (json_v1.md path object), pin to pin. Row 0's delta is its
    launch time (input delay or clock latency), so the deltas add up to the arrival; `share`
    is a cell row's delta over the largest cell delay of the path."""
    pts = path["points"]
    rows = []
    for k, p in enumerate(pts):
        if k == 0:
            arc, rf, delta = ("input" if p["cell"] is None else "clock"), p["rf"], p["at"]
        elif p["arc"] == "net":
            arc, rf, delta = "net", p["rf"], p["incr"]
        else:
            arc = "%s→%s" % (_short(pts[k - 1]["pin"]), _short(p["pin"]))
            rf, delta = "%s→%s" % (pts[k - 1]["rf"], p["rf"]), p["incr"]
        rows.append({"index": k, "pin": p["pin"], "cell": p["cell"], "kind": p["arc"],
                     "arc": arc, "rf": rf, "delta": delta, "at": p["at"], "slew": p["slew"]})
    big = max([r["delta"] for r in rows if r["kind"] in ("cell", "ckq")] or [0.0])
    for r in rows:
        r["share"] = r["delta"] / big if big > 0 and r["kind"] in ("cell", "ckq") else 0.0
    return rows


def capture_rows(path):
    """The requirement side of a path as rows {label, delta, value}: clock edge, then
    latency, uncertainty and library time (flop) or output delay (port), then required,
    arrival and slack. Values are the rounded numbers of the path object."""
    cap, check = path["capture"], path["check"]
    value = cap["clock_edge"]
    rows = [{"label": "clock %s (rise edge)" % path["capture_clock"], "delta": None, "value": value}]
    if cap["pin"] is not None:
        sign = -1.0 if check == "setup" else 1.0
        value += cap["latency"]
        rows.append({"label": "clock latency", "delta": cap["latency"], "value": value})
        value += sign * cap["uncertainty"]
        rows.append({"label": "clock uncertainty", "delta": sign * cap["uncertainty"], "value": value})
        rows.append({"label": "library %s time" % check, "delta": sign * cap["check"],
                     "value": path["required"]})
    else:
        rows.append({"label": "output delay", "delta": path["required"] - value,
                     "value": path["required"]})
    met = not fmt4(path["slack"]).startswith("-")
    rows += [{"label": "required", "delta": None, "value": path["required"]},
             {"label": "arrival", "delta": None, "value": path["arrival"]},
             {"label": "slack (MET)" if met else "slack (VIOLATED)", "delta": None,
              "value": path["slack"]}]
    return rows


def _col_x(col):
    return col * (W_MOD + GAP)


class _Layout:
    """Builds the schematic of one path; see schematic()."""

    def __init__(self, path, source):
        self.source = source
        self.check = path["check"]
        self.points = {p["pin"]: p for p in path["points"]}
        self.elements = []
        self.by_pin = {}          # pin -> (element, pin record), for every drawn pin
        self.wires = []
        self.fed = set()          # side inputs wired to an expanded driver
        self.top = 0.0            # smallest y0 placed so far
        self.bottom = 0.0         # largest y1 placed so far

    def module(self, inst, col, path_in=None, path_out=None):
        info = self.source.instance(inst)
        ins = [p for p in info["pins"] if p["direction"] == "input"]
        outs = [p for p in info["pins"] if p["direction"] == "output"]
        n = max(len(ins), len(outs), 1)
        e = {"kind": "module", "name": inst, "cell": info["cell"], "col": col,
             "w": W_MOD, "h": HEAD + n * PITCH + PAD, "xoff": 0, "pins": [], "arc": None}
        for i, p in enumerate(ins):
            e["pins"].append(self._pin(inst + "/" + p["name"], p["name"], "in", p["clock"],
                                       0, HEAD + (i + 0.5) * PITCH, path_in))
        off = (n - len(outs)) * PITCH / 2.0
        for j, p in enumerate(outs):
            e["pins"].append(self._pin(inst + "/" + p["name"], p["name"], "out", False,
                                       W_MOD, HEAD + off + (j + 0.5) * PITCH, path_out))
        return e

    def port(self, name, col, direction):
        drives = direction == "in"
        e = {"kind": "port", "name": name, "cell": None, "col": col, "direction": direction,
             "w": W_PORT, "h": H_PORT, "xoff": W_MOD - W_PORT if drives else 0, "arc": None,
             "pins": [self._pin(name, name, "out" if drives else "in", False,
                                W_PORT if drives else 0, H_PORT / 2.0, name)]}
        e["pins"][0]["on_path"] = name in self.points
        return e

    def _pin(self, full, name, side, clock, dx, dy, on):
        return {"pin": full, "name": name, "side": side, "clock": clock, "dx": dx, "dy": dy,
                "on_path": full == on}

    def place(self, e, y0):
        e.setdefault("lane", 0)
        e["x0"] = _col_x(e["col"]) + e["xoff"]
        e["y0"] = y0
        for p in e["pins"]:
            p["x"], p["y"] = e["x0"] + p["dx"], y0 + p["dy"]
            if p["on_path"] or p["pin"] not in self.by_pin:
                self.by_pin[p["pin"]] = (e, p)
        self.top = min(self.top, y0)
        self.bottom = max(self.bottom, y0 + e["h"])
        self.elements.append(e)

    def place_on_path(self, e, anchor):
        """Lane 0: shift vertically so the on-path pin `anchor` sits on the baseline y = 0."""
        dy = [p["dy"] for p in e["pins"] if p["pin"] == anchor][0]
        self.place(e, -dy)

    def wire(self, a, b, bend, on_path):
        (xa, ya), (xb, yb) = self.xy(a), self.xy(b)
        points = [(xa, ya), (xb, yb)] if ya == yb else [(xa, ya), (bend, ya), (bend, yb), (xb, yb)]
        self.wires.append({"from": a, "to": b, "points": points, "on_path": on_path})

    def xy(self, pin):
        p = self.by_pin[pin][1]
        return p["x"], p["y"]

    def path(self, pts):
        col, k = 0, 0
        if pts[0]["cell"] is None:
            e = self.port(pts[0]["pin"], 0, "in")
            self.place_on_path(e, pts[0]["pin"])
            prev, k = pts[0]["pin"], 1
        else:                                   # launched by a flop: CK -> Q is its first hop
            inst = pts[0]["pin"].split("/")[0]
            e = self.module(inst, 0, pts[0]["pin"], pts[1]["pin"])
            e["arc"] = (pts[0]["pin"], pts[1]["pin"], pts[1]["incr"])
            self.place_on_path(e, pts[0]["pin"])
            prev, k = pts[1]["pin"], 2
        while k < len(pts):
            p = pts[k]
            col += 1
            if p["cell"] is None:
                e = self.port(p["pin"], col, "out")
                k += 1
            elif k + 1 < len(pts) and pts[k + 1]["arc"] in ("cell", "ckq"):
                e = self.module(p["pin"].split("/")[0], col, p["pin"], pts[k + 1]["pin"])
                e["arc"] = (p["pin"], pts[k + 1]["pin"], pts[k + 1]["incr"])
                k += 2
            else:                               # the capture flop's D pin
                e = self.module(p["pin"].split("/")[0], col, p["pin"])
                k += 1
            self.place_on_path(e, p["pin"])
            self.wire(prev, p["pin"], _col_x(col) - GAP / 2.0, True)
            prev = e["arc"][1] if e["arc"] else None

    def side_inputs(self):
        for e in self.elements:
            for p in e["pins"]:
                if p["side"] == "in" and not p["on_path"] and not p["clock"] \
                        and e["kind"] == "module":
                    yield e, p

    def expand(self, pin, count):
        """Draw the driver of side input `pin`: one column left of its consumer, in a new lane
        on the consumer's side of the path (above for a pin above the path line or a lane
        above it, else below), so expansion wires never cross the path."""
        shown = dict((p["pin"], (e, p)) for e, p in self.side_inputs())
        if pin not in shown or pin in self.fed:
            return False
        driver = self.source.driver(pin)
        if driver is None or driver in self.by_pin:
            return False
        consumer, p = shown[pin]
        up = consumer["lane"] > 0 or (consumer["lane"] == 0 and p["y"] < 0)
        col = consumer["col"] - 1
        if "/" in driver:
            e = self.module(driver.split("/")[0], col)
        else:
            e = self.port(driver, col, "in")
        if up:
            e["lane"] = 1 + max([x["lane"] for x in self.elements] + [0])
            self.place(e, self.top - LANE_GAP - e["h"])
        else:
            e["lane"] = -1 + min([x["lane"] for x in self.elements] + [0])
            self.place(e, self.bottom + LANE_GAP)
        bend = _col_x(col) + W_MOD + GAP / 2.0 - 10 * ((count - 1) % 4 + 1)
        self.wire(driver, pin, bend, False)
        self.fed.add(pin)
        return True

    def stubs(self):
        out = []
        for e, p in self.side_inputs():
            if p["pin"] in self.fed:
                continue
            driver = self.source.driver(p["pin"])
            arrival = self.source.arrival(p["pin"], self.check)
            stub = {"pin": p["pin"], "x": p["x"], "y": p["y"], "driver": driver,
                    "at": "%s %s" % (fmt4(arrival[0]), arrival[1]) if arrival else None}
            if driver is None:
                stub["state"] = "none"
            elif driver in self.by_pin:          # reconvergence: the driver is already drawn
                stub["state"] = "link"
            else:
                stub["state"] = "expand"
            out.append(stub)
        for e in self.elements:
            for p in e["pins"]:
                if p["clock"]:
                    arrival = self.source.arrival(p["pin"], self.check)
                    out.append({"pin": p["pin"], "x": p["x"], "y": p["y"], "state": "clock",
                                "driver": None,
                                "at": "L %s" % fmt4(arrival[0]) if arrival else None})
        return out

    def badges(self, pts):
        out = []
        end = pts[-1]["pin"]
        for e in self.elements:
            for p in e["pins"]:
                point = self.points.get(p["pin"])
                if point is None or not p["on_path"]:
                    continue
                if p["side"] == "out" or p["pin"] == end:
                    text = "%s %s" % (fmt4(point["at"]), point["rf"])
                    if p["pin"] == end:
                        out.append({"pin": p["pin"], "x": p["x"] - 8, "y": p["y"] + 7,
                                    "anchor": "ne", "text": text})
                    else:
                        out.append({"pin": p["pin"], "x": p["x"] + 8, "y": p["y"] - 6,
                                    "anchor": "sw", "text": text})
        return out


def schematic(path, source, expanded=()):
    """The path's cells as modules (json_v1.md path object, source = viewer source).

    Lane 0 holds the path left to right, one element per grid column, each module shifted so
    its on-path input pin is on the baseline. Each side input in `expanded` (in order) adds
    its driver in a new lane outside every lane on its side of the path, one column left of
    the consumer; a side input whose driver is already drawn is shown as a link instead.
    Wires bend only in column gaps, so no wire crosses a box and no two boxes overlap.
    Returns {"elements", "wires", "stubs", "badges", "expanded" (the expansions applied),
    "bbox"} with coordinates shifted so the drawing starts at (MARGIN_X, MARGIN_Y)."""
    lay = _Layout(path, source)
    lay.path(path["points"])
    applied = []
    for pin in expanded:
        if lay.expand(pin, len(applied) + 1):
            applied.append(pin)
    stubs, badges = lay.stubs(), lay.badges(path["points"])
    dx = MARGIN_X - min(e["x0"] for e in lay.elements)
    dy = MARGIN_Y - min(e["y0"] for e in lay.elements)
    for e in lay.elements:
        e["x0"] += dx
        e["y0"] += dy
        e["x1"], e["y1"] = e["x0"] + e["w"], e["y0"] + e["h"]
        for p in e["pins"]:
            p["x"] += dx
            p["y"] += dy
        if e["arc"]:
            e["arc"] = {"from": e["arc"][0], "to": e["arc"][1], "delay": e["arc"][2]}
    for w in lay.wires:
        w["points"] = [(x + dx, y + dy) for x, y in w["points"]]
    for item in stubs + badges:
        item["x"] += dx
        item["y"] += dy
    width = max(e["x1"] for e in lay.elements) + MARGIN_X
    height = max(e["y1"] for e in lay.elements) + MARGIN_Y
    return {"elements": lay.elements, "wires": lay.wires, "stubs": stubs, "badges": badges,
            "expanded": applied, "bbox": (0, 0, width, height)}
