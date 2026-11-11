"""PrimeTime-style report_timing (R55): text for our path objects (json_v1.md), and a lenient
reader of such text, ours or a PrimeTime report's, back into path objects, so the viewer can
open a report file. The layout follows PrimeTime's default report_timing: a header block,
blocks indented by two spaces, start and end points named by instance (a port by name),
2 decimals unless asked otherwise, only output pins unless input pins are asked for (an
output pin's Incr then includes the net before it), "Path Type: max (recalculated)" for a
PBA path, a clock uncertainty line only when it is not 0."""

import re
from decimal import Decimal, ROUND_HALF_UP

from sta_toy import P2Error

SOURCE_KIND = "input port clocked by %s"
FLOP_KIND = "rising edge-triggered flip-flop clocked by %s"
PO_KIND = "output port clocked by %s"


def fmt(v, digits):
    """`v` rounded half up to `digits` decimals; "" for None; never "-0.00"."""
    if v is None:
        return ""
    q = Decimal(repr(round(v, 9))).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return str(abs(q) if q == 0 else q)


def header(design, options):
    """The block above the paths; `options` are the report_timing options it names."""
    lines = ["*" * 40, "Report : timing"] + ["        " + o for o in options]
    lines += ["Design : %s" % design, "Version: sta_toy", "*" * 40, "", ""]
    return "".join(line + "\n" for line in lines)


def _instance(pin):
    return pin.split("/")[0] if "/" in pin else pin


def format_path(p, digits=2, input_pins=False, transition=False, capacitance=False):
    """One block from a path object; ends with a blank line."""
    clk, launch_clk, launch, cap = p["capture_clock"], p["launch_clock"], p["launch"], p["capture"]
    pi_start, po_end = launch["input_delay"] is not None, cap["pin"] is None
    cols = (["Cap"] if capacitance else []) + (["Trans"] if transition else []) + ["Incr", "Path"]
    f = lambda v: fmt(v, digits)

    def line(name, rf="", **values):
        text = "  " + name.ljust(40)
        for col in cols:
            text += values.get(col.lower(), "").rjust(10) + " "
        return (text + rf).rstrip()

    out = ["  Startpoint: %s (%s)" % (p["start"] if pi_start else _instance(p["start"]),
                                      (SOURCE_KIND if pi_start else FLOP_KIND) % launch_clk),
           "  Endpoint: %s (%s)" % (p["end"] if po_end else _instance(p["end"]),
                                    (PO_KIND if po_end else FLOP_KIND) % clk),
           "  Path Group: %s" % clk,
           "  Path Type: %s%s" % (p["type"], " (recalculated)" if p.get("pba") else ""),
           "", line("Point", **{c.lower(): c for c in cols})]
    rule = "  " + "-" * (len(out[-1]) - 2)
    out += [rule,
            line("clock %s (rise edge)" % launch_clk, incr=f(launch["clock_edge"]), path=f(launch["clock_edge"]))]
    if pi_start:
        first = p["points"][0]
        out.append(line("input external delay", first["rf"], incr=f(launch["input_delay"]),
                        path=f(launch["input_delay"])))
    else:
        out.append(line("clock network delay (%s)" % launch.get("network", "ideal"),
                        incr=f(launch["latency"]), path=f(launch["latency"])))
    pending = 0.0
    last = len(p["points"]) - 1
    for k, q in enumerate(p["points"]):
        pending += q["incr"]
        is_input = q["cell"] is not None and k not in (0, last) and p["points"][k + 1]["arc"] in ("cell", "ckq")
        if is_input and not input_pins:
            continue
        name = "%s (%s)" % (q["pin"], q["cell"] if q["cell"] is not None else ("in" if k == 0 else "out"))
        out.append(line(name, q["rf"], cap=f(q["cap"]) if capacitance else "",
                        trans=f(q["slew"]) if transition else "", incr=f(pending), path=f(q["at"])))
        pending = 0.0
    out += [line("data arrival time", path=f(p["arrival"])), ""]
    edge = cap["clock_edge"]
    out.append(line("clock %s (rise edge)" % clk, incr=f(edge), path=f(edge)))
    if not po_end:
        sign = -1.0 if p["check"] == "setup" else 1.0
        at = edge + cap["latency"]
        out.append(line("clock network delay (%s)" % cap.get("network", "ideal"), incr=f(cap["latency"]),
                        path=f(at)))
        if cap["uncertainty"]:
            at += sign * cap["uncertainty"]
            out.append(line("clock uncertainty", incr=f(sign * cap["uncertainty"]), path=f(at)))
        out.append(line("%s (%s)" % (cap["pin"], cap["cell"]), "r", path=f(at)))
        out.append(line("library %s time" % p["check"], incr=f(sign * cap["check"]), path=f(p["required"])))
    else:
        out.append(line("output external delay", incr=f(p["required"] - edge), path=f(p["required"])))
    out += [line("data required time", path=f(p["required"])), rule]
    if p["check"] == "setup":
        out += [line("data required time", path=f(p["required"])), line("data arrival time", path=f(-p["arrival"]))]
    else:
        out += [line("data arrival time", path=f(p["arrival"])), line("data required time", path=f(-p["required"]))]
    met = "VIOLATED" if f(p["slack"]).startswith("-") else "MET"
    out += [rule, line("slack (%s)" % met, path=f(p["slack"])), "", ""]
    return "".join(x + "\n" for x in out)


def report_timing(path_objs, design, options, digits=2, input_pins=False, transition=False,
                  capacitance=False):
    """The header and every block; "No paths." when there are none."""
    body = "".join(format_path(p, digits, input_pins, transition, capacitance) for p in path_objs)
    return header(design, options) + (body or "No paths.\n")


# ------------------------------------------------------------------------------------ reader

_NUMBER = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")
_MARKS = {"&", "*", "H", "^", "<-", "#", "+", "c", "x"}       # annotation flags after numbers
_PIN = re.compile(r"^(\S+) \((.+)\)$")


def _split(line):
    """(name, [numbers], rf) of a table line: numbers and an r / f at its end, flags dropped."""
    tokens, values, rf = line.split(), [], None
    while tokens:
        t = tokens[-1]
        if t in ("r", "f") and rf is None and not values:
            rf = t
        elif _NUMBER.match(t):
            values.insert(0, float(t))
        elif t in _MARKS:
            pass
        else:
            break
        tokens.pop()
    return " ".join(tokens), values, rf


def parse(text, filename="report"):
    """Path objects (json_v1.md shape, as much as the text gives) of every block in `text`.
    Missing input pins (a report without -input_pins) become "<instance>/?" points with a 0
    Incr, so every cell keeps an input and an output on the path."""
    blocks, current = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Startpoint:"):
            current = [line]
            blocks.append(current)
        elif current is not None:
            current.append(line)
    paths = [_block(b, filename, i + 1) for i, b in enumerate(blocks)]
    if not paths:
        raise P2Error(None, None, "%s has no timing path (no Startpoint: line)" % filename)
    return paths


def _clock_of(kind_text):
    m = re.search(r"clocked by (\S+)", kind_text)
    return m.group(1).rstrip(")") if m else None


def _block(lines, filename, number):
    def error(message):
        raise P2Error(None, None, "%s, path %d: %s" % (filename, number, message))

    info = {}
    for line in lines[:8]:
        for key in ("Startpoint", "Endpoint", "Path Group", "Path Type"):
            if line.startswith(key + ":"):
                info[key] = line[len(key) + 1:].strip()
    if "Endpoint" not in info or "Path Type" not in info:
        error("no Endpoint / Path Type line")
    try:
        head = [k for k, line in enumerate(lines) if line.startswith("Point")][0]
    except IndexError:
        error("no Point table")
    cols = lines[head].split()[1:]
    launch_clock = _clock_of(info["Startpoint"])
    capture_clock = _clock_of(info["Endpoint"]) or info.get("Path Group")
    check = "hold" if info["Path Type"].startswith("min") else "setup"
    obj = {"id": "p%d" % number, "type": "min" if check == "hold" else "max", "check": check,
           "launch_clock": launch_clock, "capture_clock": capture_clock, "points": [],
           "launch": {"clock_edge": 0.0, "latency": None, "input_delay": None},
           "capture": {"clock_edge": None, "latency": None, "uncertainty": None, "check": None,
                       "output_delay": None, "rat": None, "pin": None, "cell": None},
           "arrival": None, "required": None, "slack": None}
    if "recalculated" in info["Path Type"]:
        obj["pba"] = "path"
    side, arrival_seen = "launch", False
    for line in lines[head + 1:]:
        if not line or set(line) == {"-"}:
            continue
        name, values, rf = _split(line)
        named = dict(zip(cols[len(cols) - len(values):], values))
        path_v, incr = named.get("Path"), named.get("Incr")
        low = name.lower()
        if low.startswith("slack"):
            obj["slack"] = path_v
            break
        if low == "data arrival time":
            if not arrival_seen:
                obj["arrival"], arrival_seen, side = path_v, True, "capture"
            continue
        if low == "data required time":
            if obj["required"] is None:
                obj["required"] = obj["capture"]["rat"] = path_v
            continue
        m = re.match(r"clock (\S+) \((rise|fall) edge\)", name)
        if m:
            obj[side]["clock_edge"] = path_v
            continue
        m = re.match(r"clock network delay \((\w+)\)", name)
        if m:
            obj[side]["latency"] = incr
            if m.group(1) == "propagated":
                obj[side]["network"] = "propagated"
            continue
        if low == "input external delay":
            obj["launch"]["input_delay"] = incr
            continue
        if low == "clock uncertainty":
            obj["capture"]["uncertainty"] = abs(incr or 0.0)
            continue
        if low.startswith("library ") and low.endswith(" time"):
            obj["capture"]["check"] = -incr if check == "setup" else incr
            continue
        if low == "output external delay":
            obj["capture"]["output_delay"] = -incr
            continue
        m = _PIN.match(name)
        if not m or m.group(2) == "net":
            continue                      # nets, clock reconvergence pessimism, other notes
        pin, cell = m.group(1), m.group(2)
        if side == "capture":
            obj["capture"]["pin"], obj["capture"]["cell"] = pin, cell
            continue
        obj["points"].append({"pin": pin, "cell": None if cell in ("in", "out") else cell,
                              "rf": rf or "r", "incr": incr if incr is not None else 0.0, "at": path_v,
                              "slew": named.get("Trans"), "cap": named.get("Cap"), "arc": None})
    if not obj["points"] or obj["slack"] is None:
        error("no path points or no slack line")
    obj["points"] = _arcs(obj["points"])
    obj["start"], obj["end"] = obj["points"][0]["pin"], obj["points"][-1]["pin"]
    if obj["capture"]["pin"] is not None:          # a flop: lines left out are 0
        for k in ("latency", "uncertainty"):
            if obj["capture"][k] is None:
                obj["capture"][k] = 0.0
    return obj


def _arcs(points):
    """Name the arc into every point, adding "<instance>/?" input points where a report
    left the input pins out (an output pin straight after another instance's pin)."""
    out = []
    for k, p in enumerate(points):
        if k == 0:
            p["arc"] = "start"
            out.append(p)
            continue
        prev = out[-1]
        inst, prev_inst = _instance(p["pin"]), _instance(prev["pin"])
        if p["cell"] is None or inst != prev_inst:
            last = k == len(points) - 1
            if p["cell"] is not None and not last and _instance(points[k + 1]["pin"]) == inst:
                p["arc"] = "net"                                   # an input pin, shown
            elif p["cell"] is not None and not last:
                # an output pin whose input was left out: a 0 net to "<inst>/?", then the cell
                out.append({"pin": inst + "/?", "cell": p["cell"], "rf": prev["rf"], "incr": 0.0,
                            "at": prev["at"], "slew": prev["slew"], "cap": None, "arc": "net"})
                p["arc"] = "cell"
            else:
                p["arc"] = "net"
        else:
            p["arc"] = "ckq" if k == 1 and prev["cell"] is not None else "cell"
        out.append(p)
    return out
