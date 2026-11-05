"""Viewer entry point (R29, viewer_p4.md "Start"):
python -m sta_toy.viewer --lib L [--lib L ...] --verilog V --sdc S [--theme NAME]
python -m sta_toy.viewer --bundle FILE [--theme NAME]
Errors follow cli_p2.md: one stderr line, exit 1."""

import sys

from sta_toy import P2Error, StaError
from sta_toy.viewer.source import BundleSource, EngineSource
from sta_toy.viewer.theme import NAMES

OPTIONS = ("--lib", "--verilog", "--sdc", "--bundle", "--theme")
NO_TK = "error: the viewer needs a Python with tkinter"


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
    if args.get("--theme", "light") not in NAMES:
        raise P2Error(None, None, "--theme needs one of %s" % ", ".join(NAMES))
    if "--bundle" in args:
        if args["--lib"] or "--verilog" in args or "--sdc" in args:
            raise P2Error(None, None, "--bundle cannot be combined with --lib, --verilog or --sdc")
        return args
    for option in ("--lib", "--verilog", "--sdc"):
        if not args.get(option):
            raise P2Error(None, None, "missing %s" % option)
    return args


def main(argv):
    try:
        args = arguments(argv)
        if "--bundle" in args:
            source = BundleSource(args["--bundle"])
        else:
            source = EngineSource(args["--lib"], args["--verilog"], args["--sdc"])
    except P2Error as e:
        print(e, file=sys.stderr)
        return 1
    except StaError as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 1
    try:
        import tkinter
        from sta_toy.viewer.app import App
    except ImportError:
        print(NO_TK, file=sys.stderr)
        return 1
    try:
        root = tkinter.Tk()
    except tkinter.TclError as e:
        print("error: cannot open the viewer window: %s" % e, file=sys.stderr)
        return 1
    App(root, source, args.get("--theme", "light"))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
