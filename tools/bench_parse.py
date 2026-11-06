"""Parse benchmark for the Liberty reader (R42).

    python3 tools/bench_parse.py LIB [--repeat N]

Reads LIB once, then runs liberty.parse on its text N times (default 5) and prints the
best and mean wall-clock seconds per parse and the process's peak resident set size.
"""
import argparse
import os
import resource
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sta_toy import liberty, read_file  # noqa: E402


def peak_rss_mb():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024.0 * 1024.0) if sys.platform == "darwin" else rss / 1024.0   # bytes on macOS, KiB elsewhere


def main(argv=None):
    ap = argparse.ArgumentParser(description="time liberty.parse on one file")
    ap.add_argument("lib")
    ap.add_argument("--repeat", type=int, default=5)
    a = ap.parse_args(argv)
    if a.repeat < 1:
        ap.error("--repeat must be at least 1")
    text = read_file(a.lib)
    times = []
    for _ in range(a.repeat):
        t0 = time.perf_counter()
        liberty.parse(text, a.lib)
        times.append(time.perf_counter() - t0)
    print("%s: %d bytes, %d runs, best %.3f s, mean %.3f s, peak RSS %.1f MB"
          % (a.lib, len(text), a.repeat, min(times), sum(times) / len(times), peak_rss_mb()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
