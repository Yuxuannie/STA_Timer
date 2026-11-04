#!/usr/bin/env python3
"""Regenerate every golden directory under tests/golden/ with the oracle.

    python3 tools/oracle/make_golden.py

Golden files are only ever produced by this script.  Never edit them by hand.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESIGNS = [
    # golden dir      verilog        sdc
    ("ff2_default",   "ff2.v",  "ff2_default.sdc"),
    ("ff2_swap",      "ff2.v",  "ff2_swap.sdc"),
    ("ff2_setupviol", "ff2.v",  "ff2_setupviol.sdc"),
    ("ff2_holdviol",  "ff2.v",  "ff2_holdviol.sdc"),
    ("ff2_skew",      "ff2.v",  "ff2_skew.sdc"),
    ("ff2_unc",       "ff2.v",  "ff2_unc.sdc"),
    ("inv2",          "inv2.v", "inv2.sdc"),
    ("s27",           "s27.v",  "s27.sdc"),
]


def main():
    for name, v, sdc in DESIGNS:
        cmd = [sys.executable, os.path.join(ROOT, "tools", "oracle", "oracle.py"),
               "--lib", os.path.join(ROOT, "data", "toy2.lib"),
               "--verilog", os.path.join(ROOT, "data", v),
               "--sdc", os.path.join(ROOT, "data", "sdc", sdc),
               "--out", os.path.join(ROOT, "tests", "golden", name)]
        subprocess.run(cmd, check=True)
        print("golden:", name)


if __name__ == "__main__":
    main()
