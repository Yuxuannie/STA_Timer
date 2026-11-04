# s27: clock latency on the whole clock, uncertainty, mixed input delays,
# no set_clock_transition (CK slew defaults to 0, below the table grid).
# G1 has no set_input_delay (arrival defaults to 0); G2 has no set_input_transition (slew 0).
# G3 has only -max (the -min facet defaults to 0).
# G17 has only -max: its hold check is undefined (NA cells, no hold path line).
create_clock -name clk -period 10.0 [get_ports clk]
set_clock_latency 0.2 [get_clocks clk]
set_clock_uncertainty -setup 0.1 [get_clocks clk]
set_clock_uncertainty -hold 0.05 [get_clocks clk]
set_input_delay -max 1.0 -clock clk [get_ports G0]
set_input_delay -min 0.4 -clock clk [get_ports G0]
set_input_delay 0.5 -clock clk [get_ports G2]
set_input_delay -max 2.0 -clock clk [get_ports G3]
set_input_transition 0.05 [get_ports G0]
set_input_transition 0.10 [get_ports G1]
set_input_transition 0.02 [get_ports G3]
set_output_delay -max 1.0 -clock clk [get_ports G17]
set_load 0.003 [get_ports G17]
