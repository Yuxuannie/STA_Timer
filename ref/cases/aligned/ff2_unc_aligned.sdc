# R40 aligned copy of data/sdc/ff2_unc.sdc (REPORT_P5.md §7): the P5-2..P5-4 policies neutralised;
# lines changed are marked. The comments below are the original file's.
# ff2 uncertainty: a plain value sets both facets, a later -setup replaces only setup.
# Result: setup 0.5, hold 0.3.
create_clock -name clk -period 10.0 [get_ports clk]
# set_clock_uncertainty lines removed (P5-3: they reach the output-port checks in OpenSTA only)
set_clock_transition 0.05 [get_clocks clk]
set_input_delay 0.5 -clock clk [get_ports x]
set_input_transition 0.05 [get_ports x]
set_output_delay -max 2.0 -clock clk [get_ports y]
set_output_delay -min 0.5 -clock clk [get_ports y]
set_load 0.002 [get_ports y]
