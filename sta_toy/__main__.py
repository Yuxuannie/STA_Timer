"""CLI: python -m sta_toy --lib <file> [--lib <file> ...] --verilog <file>
[--sdc <file> --dump-tsv <dir>] (R6; --sdc and --dump-tsv from R18, cli_p2.md)."""

import sys

from sta_toy import P2Error, StaError, design, tsv, writer

OPTIONS = ("--lib", "--verilog", "--sdc", "--dump-tsv")


def arguments(argv):
    """Options as {option: value}, with a list of values for --lib."""
    args = {"--lib": []}
    for i in range(0, len(argv), 2):
        option = argv[i]
        if option not in OPTIONS:
            raise P2Error(None, None, "unknown option %s" % option)
        if i + 1 == len(argv):
            raise P2Error(None, None, "missing value for %s" % option)
        if option == "--lib":
            args[option].append(argv[i + 1])
        elif option in args:
            raise P2Error(None, None, "%s given twice" % option)
        else:
            args[option] = argv[i + 1]
    for option in ("--lib", "--verilog"):
        if not args.get(option):
            raise P2Error(None, None, "missing %s" % option)
    if ("--sdc" in args) != ("--dump-tsv" in args):
        raise P2Error(None, None, "--sdc and --dump-tsv must be given together")
    return args


def main(argv):
    try:
        args = arguments(argv)
        lib, netlist, linked = design.load(args["--lib"], args["--verilog"])
        if "--sdc" not in args:
            text = writer.write(linked)
        else:
            tsv.dump(design.timed(lib, netlist, linked, args["--sdc"]), args["--dump-tsv"])
            text = ""
    except P2Error as e:
        print(e, file=sys.stderr)
        return 1
    except StaError as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 1
    sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
