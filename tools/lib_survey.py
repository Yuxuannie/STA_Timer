"""Survey Liberty libraries (R46): load each LIB as a design does (R49: the cells are parsed
when built), build every cell, and print the load and build times, the peak resident set
size and the cells that do not build, grouped by message.

    python3 tools/lib_survey.py LIB [LIB ...]

Exit status 1 when a library does not parse or lacks what every design needs (its name,
units, templates); a cell that does not build is reported, since it is an error only when a
netlist uses it.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sta_toy import StaError, liberty  # noqa: E402
from bench_parse import peak_rss_mb  # noqa: E402


def survey(path):
    """(seconds to load, seconds to build every cell, number of cells,
    {message: [(cell, line), ...]} of the cells not built)."""
    t0 = time.perf_counter()
    lib = liberty.load(path, cells=())
    t1 = time.perf_counter()
    names = list(lib.unbuilt)
    failed = {}
    for name in names:
        try:
            lib.build({name})
        except StaError as e:
            # "cell X pin Y: message" -> "message"; the cell is listed apart.
            failed.setdefault(e.message.split(": ", 1)[-1], []).append((name, e.line))
    return t1 - t0, time.perf_counter() - t1, len(names), failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="parse Liberty files and build every cell")
    ap.add_argument("lib", nargs="+")
    a = ap.parse_args(argv)
    status = 0
    for path in a.lib:
        try:
            load, build, count, failed = survey(path)
        except StaError as e:
            print("%s: does not load: %s" % (path, e))
            status = 1
            continue
        print("%s: loaded in %.2f s, %d cells, %d built in %.2f s, peak RSS %.1f MB"
              % (path, load, count, count - sum(len(c) for c in failed.values()), build,
                 peak_rss_mb()))
        for message, cells in sorted(failed.items(), key=lambda kv: -len(kv[1])):
            shown = ", ".join("%s (line %s)" % c for c in cells[:3])
            print("  %d not built: %s: %s%s" % (len(cells), message, shown,
                                                 ", ..." if len(cells) > 3 else ""))
    return status


if __name__ == "__main__":
    sys.exit(main())
