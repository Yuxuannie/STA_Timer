#!/usr/bin/env python3
"""Generate data/toy2.lib.

Every 3x3 table is affine in its two index variables:  v = a + b*x1 + c*x2.
Bilinear interpolation is exact on an affine function, so design-level golden
numbers stay hand-computable.  Constant tables are the special case b = c = 0.

Run:  python3 tools/gen_toy2_lib.py > data/toy2.lib

R37: --time ps --cap ff --suffix _P writes a copy in those units (every time and
capacitance scaled, the same circuit) with every cell name suffixed; the default
output is data/toy2.lib byte for byte.
"""

import argparse

SLEW = [0.01, 0.05, 0.20]        # input_net_transition (ns)
LOAD = [0.001, 0.004, 0.016]     # total_output_net_capacitance (pF)
CSLEW = [0.01, 0.05, 0.20]       # constrained_pin_transition = D slew
RSLEW = [0.01, 0.05, 0.20]       # related_pin_transition = CK slew

B_SLEW, C_LOAD = 2.0, 50.0       # delay slope per ns of slew / per pF of load
B_SLEW_T, C_LOAD_T = 0.2, 5.0    # transition slope

TIME_SCALE = {"ns": 1, "ps": 1000}   # values above are in ns and pF
CAP_SCALE = {"pf": 1, "ff": 1000}
T, C, SUFFIX = 1, 1, ""             # set by main()

FUNC = {"BUF": "A", "INV": "!A", "AND2": "A&B", "OR2": "A|B",
        "NAND2": "!(A&B)", "NOR2": "!(A|B)"}


def fmt(v):
    return "%g" % v


def table(ind, name, template, a, b1, b2, idx1, idx2, s1, s2):
    """Emit a table group. value(x1, x2) = a + b1*x1 + b2*x2, rows follow index_1.
    Values are times (scaled by T); s1 / s2 scale the printed index_1 / index_2."""
    p = " " * ind
    rows = [", ".join("%.4f" % ((a + b1 * x1 + b2 * x2) * T) for x2 in idx2) for x1 in idx1]
    s = "%s%s (%s) {\n" % (p, name, template)
    s += '%s  index_1 ("%s");\n' % (p, ", ".join(fmt(v * s1) for v in idx1))
    s += '%s  index_2 ("%s");\n' % (p, ", ".join(fmt(v * s2) for v in idx2))
    s += "%s  values ( \\\n" % p
    s += ", \\\n".join('%s    "%s"' % (p, r) for r in rows)
    s += " );\n%s}\n" % p
    return s


def delay_tables(ind, a_rise, a_fall, t_rise, t_fall, const):
    # Template del_3x3: x1 = load, x2 = slew.  value = a + C_LOAD*load + B_SLEW*slew
    if const:
        bs = cl = bst = clt = 0.0
    else:
        bs, cl, bst, clt = B_SLEW, C_LOAD, B_SLEW_T, C_LOAD_T
    s = table(ind, "cell_rise", "del_3x3", a_rise, cl, bs, LOAD, SLEW, C, T)
    s += table(ind, "cell_fall", "del_3x3", a_fall, cl, bs, LOAD, SLEW, C, T)
    s += table(ind, "rise_transition", "del_3x3", t_rise, clt, bst, LOAD, SLEW, C, T)
    s += table(ind, "fall_transition", "del_3x3", t_fall, clt, bst, LOAD, SLEW, C, T)
    return s


def comb_cell(name, inputs, sense, a_rise, a_fall, t_rise, t_fall, cap, const=False):
    s = "  cell (%s%s) {\n    area : 1.0;\n" % (name, SUFFIX)
    for p in inputs:
        s += "    pin (%s) {\n      direction : input;\n      capacitance : %.4f;\n    }\n" % (p, cap * C)
    s += '    pin (Y) {\n      direction : output;\n      function : "%s";\n' % FUNC[name]
    for p in inputs:
        s += "      timing () {\n"
        s += '        related_pin : "%s";\n' % p
        s += "        timing_type : combinational;\n"
        s += "        timing_sense : %s;\n" % sense
        s += delay_tables(8, a_rise, a_fall, t_rise, t_fall, const)
        s += "      }\n"
    s += "    }\n  }\n"
    return s


def dff_cell():
    s = "  cell (DFF%s) {\n    area : 4.0;\n" % SUFFIX
    s += '    ff (IQ, IQN) {\n      clocked_on : "CK";\n      next_state : "D";\n    }\n'
    s += ("    pin (CK) {\n      direction : input;\n      clock : true;\n"
          "      capacitance : %.4f;\n    }\n" % (0.001 * C))
    s += "    pin (D) {\n      direction : input;\n      capacitance : %.4f;\n" % (0.002 * C)
    s += '      timing () {\n        related_pin : "CK";\n        timing_type : setup_rising;\n'
    s += table(8, "rise_constraint", "cons_3x3", 0.25, 0.5, 0.5, CSLEW, RSLEW, T, T)
    s += table(8, "fall_constraint", "cons_3x3", 0.25, 0.5, 0.5, CSLEW, RSLEW, T, T)
    s += "      }\n"
    s += '      timing () {\n        related_pin : "CK";\n        timing_type : hold_rising;\n'
    s += table(8, "rise_constraint", "cons_3x3", -0.05, 1.0, 2.0, CSLEW, RSLEW, T, T)
    s += table(8, "fall_constraint", "cons_3x3", -0.05, 1.0, 2.0, CSLEW, RSLEW, T, T)
    s += "      }\n    }\n"
    s += '    pin (Q) {\n      direction : output;\n      function : "IQ";\n'
    s += '      timing () {\n        related_pin : "CK";\n        timing_type : rising_edge;\n        timing_sense : non_unate;\n'
    s += delay_tables(8, 1.0, 1.0, 0.05, 0.05, const=True)
    s += "      }\n    }\n  }\n"
    return s


HEADER = """/*
 * toy2.lib - test library for the STA timer, stage P2.
 *
 * Structure follows the public Liberty format.  Numbers are invented.
 * Every table is affine in its two index variables (constant tables have
 * zero slope), which keeps design-level golden values hand-computable.
 *
 * Template del_3x3 declares variable_1 = total_output_net_capacitance and
 * variable_2 = input_net_transition ON PURPOSE (the opposite of the common
 * order).  Template cons_3x3 declares variable_1 = constrained_pin_transition,
 * variable_2 = related_pin_transition.  A parser must read the template.
 *
 * Affine formulas (ns, pF):
 *   BUF   delay = 1.3 + 2.0*slew + 50*load            trans = 0.03 + 0.2*slew + 5*load
 *   NAND2 delay = 1.8 + 2.0*slew + 50*load            trans = 0.03 + 0.2*slew + 5*load   (rise = fall)
 *   INV   rise 1.2 / fall 0.8 (constant)              trans = 0.05 (constant)
 *   AND2  rise 0.9 / fall 0.7 + 2.0*slew + 50*load    trans rise 0.04 / fall 0.03 + 0.2*slew + 5*load
 *   OR2   rise 0.8 / fall 1.0 + 2.0*slew + 50*load    trans rise 0.03 / fall 0.04 + 0.2*slew + 5*load
 *   NOR2  rise 1.0 / fall 0.6 + 2.0*slew + 50*load    trans rise 0.04 / fall 0.03 + 0.2*slew + 5*load
 *   DFF   CK->Q = 1.0 (constant), Q trans = 0.05 (constant)
 *         setup = 0.25 + 0.5*Dslew + 0.5*CKslew        (rise_constraint = fall_constraint)
 *         hold  = -0.05 + 1.0*Dslew + 2.0*CKslew       (negative at small slews)
 */
library (toy2) {
  delay_model : table_lookup;
  time_unit : "1ns";
  voltage_unit : "1V";
  current_unit : "1mA";
  pulling_resistance_unit : "1kohm";
  leakage_power_unit : "1nW";
  capacitive_load_unit (1, pf);
  nom_process : 1.0;
  nom_temperature : 25.0;
  nom_voltage : 1.0;
  slew_lower_threshold_pct_rise : 20.0;
  slew_upper_threshold_pct_rise : 80.0;
  slew_lower_threshold_pct_fall : 20.0;
  slew_upper_threshold_pct_fall : 80.0;
  input_threshold_pct_rise : 50.0;
  input_threshold_pct_fall : 50.0;
  output_threshold_pct_rise : 50.0;
  output_threshold_pct_fall : 50.0;

  lu_table_template (del_3x3) {
    variable_1 : total_output_net_capacitance;
    variable_2 : input_net_transition;
    index_1 ("%s");
    index_2 ("%s");
  }
  lu_table_template (cons_3x3) {
    variable_1 : constrained_pin_transition;
    variable_2 : related_pin_transition;
    index_1 ("%s");
    index_2 ("%s");
  }
"""


def main():
    global T, C, SUFFIX
    ap = argparse.ArgumentParser(description="Generate toy2.lib (default: data/toy2.lib).")
    ap.add_argument("--time", choices=sorted(TIME_SCALE), default="ns")
    ap.add_argument("--cap", choices=sorted(CAP_SCALE), default="pf")
    ap.add_argument("--suffix", default="", help="appended to every cell name")
    args = ap.parse_args()
    T, C, SUFFIX = TIME_SCALE[args.time], CAP_SCALE[args.cap], args.suffix
    header = HEADER
    if (args.time, args.cap, args.suffix) != ("ns", "pf", ""):
        header = (header.replace('time_unit : "1ns";', 'time_unit : "1%s";' % args.time)
                  .replace("capacitive_load_unit (1, pf);", "capacitive_load_unit (1, %s);" % args.cap)
                  .replace("library (toy2) {", "library (toy2%s) {" % args.suffix))
    out = [header % (", ".join(fmt(v * C) for v in LOAD), ", ".join(fmt(v * T) for v in SLEW),
                     ", ".join(fmt(v * T) for v in CSLEW), ", ".join(fmt(v * T) for v in RSLEW))]
    out.append(comb_cell("BUF", ["A"], "positive_unate", 1.3, 1.3, 0.03, 0.03, 0.0015))
    out.append(comb_cell("INV", ["A"], "negative_unate", 1.2, 0.8, 0.05, 0.05, 0.0015, const=True))
    out.append(comb_cell("AND2", ["A", "B"], "positive_unate", 0.9, 0.7, 0.04, 0.03, 0.0020))
    out.append(comb_cell("OR2", ["A", "B"], "positive_unate", 0.8, 1.0, 0.03, 0.04, 0.0020))
    out.append(comb_cell("NAND2", ["A", "B"], "negative_unate", 1.8, 1.8, 0.03, 0.03, 0.0020))
    out.append(comb_cell("NOR2", ["A", "B"], "negative_unate", 1.0, 0.6, 0.04, 0.03, 0.0020))
    out.append(dff_cell())
    out.append("}\n")
    print("".join(out), end="")


if __name__ == "__main__":
    main()
