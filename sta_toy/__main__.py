"""CLI: python -m sta_toy --lib <file> [--lib <file> ...] --verilog <file> [--sdc <file>
<outputs>] (R6; --sdc and --dump-tsv from R18, cli_p2.md; reports, JSON and bundles
from R26, cli_p3.md; --check-timing from R35, cli_p5.md)."""

import re
import sys

from sta_toy import P2Error, StaError, design, tsv, writer

VALUE_OPTIONS = ("--lib", "--verilog", "--sdc", "--dump-tsv", "--path-delay", "--from", "--to",
                 "--through", "--max-paths", "--nworst", "--json", "--bundle", "--bundle-out",
                 "--depth", "--max-nodes")
FLAGS = ("--report-timing", "--report-summary", "--transition-time", "--capacitance",
         "--check-timing")
OUTPUTS = ("--dump-tsv", "--report-timing", "--report-summary", "--json", "--bundle",
           "--check-timing")
NEEDS = {"--path-delay": "--report-timing", "--from": "--report-timing", "--to": "--report-timing",
         "--through": "--report-timing", "--max-paths": "--report-timing",
         "--nworst": "--report-timing", "--transition-time": "--report-timing",
         "--capacitance": "--report-timing", "--depth": "--bundle", "--max-nodes": "--bundle",
         "--bundle-out": "--bundle", "--bundle": "--bundle-out"}
INTEGERS = (("--max-paths", 1), ("--nworst", 1), ("--depth", 0), ("--max-nodes", 1))


def arguments(argv):
    """Options as {option: value}: a list for --lib, True for flags, int for counts."""

    def error(message):
        raise P2Error(None, None, message)

    args = {"--lib": []}
    i = 0
    while i < len(argv):
        option = argv[i]
        i += 1
        if option in FLAGS:
            if option in args:
                error("%s given twice" % option)
            args[option] = True
            continue
        if option not in VALUE_OPTIONS:
            error("unknown option %s" % option)
        if i == len(argv):
            error("missing value for %s" % option)
        if option == "--lib":
            args[option].append(argv[i])
        elif option in args:
            error("%s given twice" % option)
        else:
            args[option] = argv[i]
        i += 1
    for option in ("--lib", "--verilog"):
        if not args.get(option):
            error("missing %s" % option)
    if "--sdc" in args and not any(o in args for o in OUTPUTS):
        error("--sdc needs an output option "
              "(--dump-tsv, --report-timing, --report-summary, --json, --bundle, "
              "--check-timing or --trace)")
    for option in OUTPUTS:
        if option in args and "--sdc" not in args:
            error("%s needs --sdc" % option)
    for option, other in NEEDS.items():
        if option in args and other not in args:
            error("%s needs %s" % (option, other))
    for option, low in INTEGERS:
        if option in args:
            if not re.match(r"[0-9]+$", args[option]) or int(args[option]) < low:
                error("%s needs an integer >= %d" % (option, low))
            args[option] = int(args[option])
    if args.get("--path-delay", "max") not in ("max", "min"):
        error("--path-delay needs max or min")
    return args


def run(args):
    """Everything after the arguments; returns (stdout text, warning line or None).
    Files are written last."""
    lib, netlist, linked = design.load(args["--lib"], args["--verilog"])
    if "--sdc" not in args:
        return writer.write(linked), None
    from sta_toy import bundle, checks, jsonout, paths, report
    grid = [] if "--check-timing" in args else None
    g = design.timed(lib, netlist, linked, args["--sdc"], grid=grid)
    text = ""
    if "--report-timing" in args:
        check = "setup" if args.get("--path-delay", "max") == "max" else "hold"
        found = paths.select(g, check, args.get("--max-paths", 1), args.get("--nworst", 1),
                             args.get("--from"), args.get("--to"), args.get("--through"))
        objs = [paths.path_json(p, g.sdc, "p%d" % (i + 1)) for i, p in enumerate(found)]
        text += report.report_timing(objs, "--transition-time" in args, "--capacitance" in args)
    if "--report-summary" in args:
        text += report.format_summary(paths.summary(g))
    if "--check-timing" in args:
        text += checks.report(g, grid)
    files = []
    if "--json" in args:
        info = {"name": netlist.name, "libs": args["--lib"], "verilog": args["--verilog"],
                "sdc": args["--sdc"], "units": jsonout.units(lib)}
        files.append((jsonout.report_json(g, info), args["--json"]))
    if "--bundle" in args:
        files.append((bundle.debug_bundle(g, args["--bundle"], args.get("--depth", 3),
                                          args.get("--max-nodes", 300)), args["--bundle-out"]))
    if "--dump-tsv" in args:
        tsv.dump(g, args["--dump-tsv"])
    for obj, path in files:
        jsonout.write(obj, path)
    ignored = sum(g.ignored.values())
    warning = "warning: %d timing arcs ignored (run --check-timing)" % ignored if ignored else None
    return text, warning


def main(argv):
    try:
        text, warning = run(arguments(argv))
    except P2Error as e:
        print(e, file=sys.stderr)
        return 1
    except StaError as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 1
    sys.stdout.buffer.write(text.encode("utf-8"))
    if warning is not None:
        sys.stdout.flush()
        print(warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
