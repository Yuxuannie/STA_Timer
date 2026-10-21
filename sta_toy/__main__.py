"""CLI: python -m sta_toy --lib <file> --verilog <file> (R6)."""

import sys

from sta_toy import StaError, graph, liberty, verilog, writer

USAGE = "ERROR: usage: python -m sta_toy --lib <file> --verilog <file>"


def main(argv):
    args = dict(zip(argv[0::2], argv[1::2]))
    if len(argv) != 4 or sorted(args) != ["--lib", "--verilog"]:
        print(USAGE, file=sys.stderr)
        return 1
    try:
        lib = liberty.load(args["--lib"])
        netlist = verilog.load(args["--verilog"])
        text = writer.write(graph.link(netlist, lib))
    except StaError as e:
        print("ERROR %s" % e, file=sys.stderr)
        return 1
    sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
