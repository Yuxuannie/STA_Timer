"""report_timing text (R23) and the summary text (R24), report_p3.md §4-§5. A block is
formatted only from the json_v1.md path object, so a saved bundle prints the same way."""

from sta_toy.tsv import fmt4

SOURCE_KIND = "input port clocked by %s"
FLOP_KIND = "rising edge-triggered flip-flop clocked by %s"
PO_KIND = "output port clocked by %s"


def _line(name, incr="", path="", rf="", cap=None, trans=None):
    """One table line; cap / trans are None when their column is off ("" = empty cell)."""
    text = name.ljust(40)
    for cell in (cap, trans):
        if cell is not None:
            text += cell.rjust(10) + " "
    text += incr.rjust(10) + " " + path.rjust(10)
    if rf:
        text += " " + rf
    return text.rstrip()


def format_path(p, transition=False, capacitance=False):
    """One report block (report_p3.md §4) from a path object; ends with "\\n"."""
    clk = p["capture_clock"]
    launch, cap = p["launch"], p["capture"]
    empty = {"cap": "" if capacitance else None, "trans": "" if transition else None}

    def row(name, incr=None, path=None, rf=""):
        return _line(name, "" if incr is None else fmt4(incr),
                     "" if path is None else fmt4(path), rf, **empty)

    header = _line("Point", "Incr", "Path", cap="Cap" if capacitance else None,
                   trans="Trans" if transition else None)
    sep = "-" * len(header)
    pi_start = launch["input_delay"] is not None
    lines = ["Startpoint: %s (%s)" % (p["start"], (SOURCE_KIND if pi_start else FLOP_KIND) % clk),
             "Endpoint: %s (%s)" % (p["end"], (FLOP_KIND if cap["pin"] else PO_KIND) % clk),
             "Path Group: %s" % clk,
             "Path Type: %s" % p["type"],
             "", header, sep,
             row("clock %s (rise edge)" % p["launch_clock"], 0.0, 0.0)]
    if pi_start:
        lines.append(row("input external delay", launch["input_delay"], launch["input_delay"]))
    else:
        lines.append(row("clock network delay (ideal)", launch["latency"], launch["latency"]))

    for i, q in enumerate(p["points"]):
        if q["cell"] is not None:
            name = "%s (%s)" % (q["pin"], q["cell"])
        else:
            name = "%s (%s)" % (q["pin"], "in" if i == 0 else "out")
        lines.append(_line(name, fmt4(q["incr"]), fmt4(q["at"]), q["rf"],
                           cap=("" if q["cap"] is None else fmt4(q["cap"])) if capacitance else None,
                           trans=fmt4(q["slew"]) if transition else None))
    lines += [row("data arrival time", path=p["arrival"]), ""]

    edge = cap["clock_edge"]
    lines.append(row("clock %s (rise edge)" % clk, edge, edge))
    if cap["pin"]:
        sign = -1.0 if p["check"] == "setup" else 1.0
        at_pin = edge + cap["latency"] + sign * cap["uncertainty"]
        lines += [row("clock network delay (ideal)", cap["latency"], edge + cap["latency"]),
                  row("clock uncertainty", sign * cap["uncertainty"], at_pin),
                  row("%s (%s)" % (cap["pin"], cap["cell"]), path=at_pin, rf="r"),
                  row("library %s time" % p["check"], sign * cap["check"], p["required"])]
    else:
        lines.append(row("output external delay", p["required"] - edge, p["required"]))
    lines += [row("data required time", path=p["required"]), sep]
    if p["check"] == "setup":
        lines += [row("data required time", path=p["required"]),
                  row("data arrival time", path=-p["arrival"])]
    else:
        lines += [row("data arrival time", path=p["arrival"]),
                  row("data required time", path=-p["required"])]
    met = "VIOLATED" if fmt4(p["slack"]).startswith("-") else "MET"
    lines += [sep, row("slack (%s)" % met, path=p["slack"])]
    return "".join(line + "\n" for line in lines)


def report_timing(path_objs, transition=False, capacitance=False):
    """The blocks separated by one blank line, or "No paths.\\n"."""
    if not path_objs:
        return "No paths.\n"
    return "\n".join(format_path(p, transition, capacitance) for p in path_objs)


def format_summary(summary):
    """report_p3.md §5: a header and one row per check."""
    lines = ["check".ljust(8) + "wns".rjust(10) + "tns".rjust(10) + "nvp".rjust(6)]
    for check in ("setup", "hold"):
        s = summary[check]
        lines.append(check.ljust(8) + fmt4(s["wns"]).rjust(10) + fmt4(s["tns"]).rjust(10)
                     + str(s["nvp"]).rjust(6))
    return "".join(line + "\n" for line in lines)
