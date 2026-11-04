"""--dump-tsv: endpoints.tsv, pins.tsv and paths.txt in the format of golden_format.md (R18)."""

import os
from decimal import Decimal, ROUND_HALF_UP

from sta_toy import P2Error, timer

PIN_COLUMNS = [(kind, mode, rf) for kind in ("at", "rat", "slew")
               for mode in timer.MODES for rf in ("r", "f")]


def fmt4(v):
    """p2_semantics.md §11, exactly."""
    if v is None:
        return "NA"
    d = Decimal(repr(round(v, 9))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    s = str(d)
    return "0.0000" if s == "-0.0000" else s


def _check_cells(node, kind):
    rf = timer.worst_rf(node, kind)
    if rf is None:
        return ["NA"] * 3
    mode = "late" if kind == "setup" else "early"
    return [fmt4(node.at[mode][rf]), fmt4(node.rat[mode][rf]), fmt4(timer.slack(node, kind, rf))]


def tables(g):
    """The three files as {name: text}."""
    endpoints = sorted(g.endpoints, key=lambda n: n.name)
    lines = ["pin\tsetup_at\tsetup_rat\tsetup_slack\thold_at\thold_rat\thold_slack"]
    for n in endpoints:
        lines.append("\t".join([n.name] + _check_cells(n, "setup") + _check_cells(n, "hold")))
    files = {"endpoints.tsv": lines}

    lines = ["pin\t" + "\t".join("%s_%s_%s" % c for c in PIN_COLUMNS)]
    for n in sorted(g.nodes, key=lambda n: n.name):
        lines.append("\t".join([n.name] + [fmt4(getattr(n, kind)[mode][rf])
                                           for kind, mode, rf in PIN_COLUMNS]))
    files["pins.tsv"] = lines

    lines = []
    for n in endpoints:
        for kind in ("setup", "hold"):
            rf = timer.worst_rf(n, kind)
            if rf is not None:
                path = " -> ".join("%s(%s)" % (p.name, p_rf) for p, p_rf in timer.worst_path(n, kind, rf))
                lines.append("%s %s %s : %s" % (n.name, kind, fmt4(timer.slack(n, kind, rf)), path))
    files["paths.txt"] = lines
    return {name: "".join(line + "\n" for line in text) for name, text in files.items()}


def dump(g, directory):
    try:
        os.makedirs(directory, exist_ok=True)
        for name, text in tables(g).items():
            with open(os.path.join(directory, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    except OSError as e:
        raise P2Error(None, None, "cannot write %s: %s" % (directory, e.strerror or e))
