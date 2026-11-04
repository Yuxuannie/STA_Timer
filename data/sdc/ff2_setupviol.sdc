# ff2 setup violation: period 4.0.
create_clock -name clk -period 4.0 [get_ports clk]
set_clock_transition 0.05 [get_clocks clk]
set_input_delay 0.5 -clock clk [get_ports x]
set_input_transition 0.05 [get_ports x]
set_output_delay -max 2.0 -clock clk [get_ports y]
set_output_delay -min 0.5 -clock clk [get_ports y]
set_load 0.002 [get_ports y]
