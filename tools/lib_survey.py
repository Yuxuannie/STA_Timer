"""Survey Liberty libraries (R46): parse each LIB, build every cell, and print the parse time,
the peak resident set size and the cells that do not build, grouped by message.

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
    """(seconds to load, number of cells, {message: [(cell, line), ...]} of the cells not built)."""
    t0 = time.perf_counter()
    lib = liberty.load(path, cells=())
    seconds = time.perf_counter() - t0
    names = list(lib.unbuilt)
    failed = {}
    for name in names:
        try:
            lib.build({name})
        except StaError as e:
            # "cell X pin Y: message" -> "message"; the cell is listed apart.
            failed.setdefault(e.message.split(": ", 1)[-1], []).append((name, e.line))
    return seconds, len(names), failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="parse Liberty files and build every cell")
    ap.add_argument("lib", nargs="+")
    a = ap.parse_args(argv)
    status = 0
    for path in a.lib:
        try:
            seconds, count, failed = survey(path)
        except StaError as e:
            print("%s: does not load: %s" % (path, e))
            status = 1
            continue
        print("%s: loaded in %.2f s, %d cells, %d built, peak RSS %.1f MB"
              % (path, seconds, count, count - sum(len(c) for c in failed.values()), peak_rss_mb()))
        for message, cells in sorted(failed.items(), key=lambda kv: -len(kv[1])):
            shown = ", ".join("%s (line %s)" % c for c in cells[:3])
            print("  %d not built: %s: %s%s" % (len(cells), message, shown,
                                                 ", ..." if len(cells) > 3 else ""))
    return status


if __name__ == "__main__":
    sys.exit(main())
