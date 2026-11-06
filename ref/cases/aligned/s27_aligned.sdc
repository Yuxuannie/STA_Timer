# R40 aligned copy of data/sdc/s27.sdc (REPORT_P5.md §7): the P5-2..P5-4 policies neutralised;
# lines changed are marked. The comments below are the original file's.
# s27: clock latency on the whole clock, uncertainty, mixed input delays,
# no set_clock_transition (CK slew defaults to 0, below the table grid).
# G1 has no set_input_delay (arrival defaults to 0); G2 has no set_input_transition (slew 0).
# G3 has only -max (the -min facet defaults to 0).
# G17 has only -max: its hold check is undefined (NA cells, no hold path line).
create_clock -name clk -period 10.0 [get_ports clk]
# set_clock_uncertainty lines removed (P5-3: they reach the output-port checks in OpenSTA only)
# latency removed (P5-2)
set_input_delay -max 1.0 -clock clk [get_ports G0]
set_input_delay -min 0.4 -clock clk [get_ports G0]
set_input_delay 0.5 -clock clk [get_ports G2]
# changed (P5-4): was -max 2.0 only
set_input_delay 2.0 -clock clk [get_ports G3]
set_input_transition 0.05 [get_ports G0]
set_input_transition 0.10 [get_ports G1]
set_input_transition 0.02 [get_ports G3]
set_output_delay -max 1.0 -clock clk [get_ports G17]
set_load 0.003 [get_ports G17]
# added (P5-4)
set_input_delay 0 -clock clk [get_ports G1]
