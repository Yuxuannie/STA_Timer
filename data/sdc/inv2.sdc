# inv2: appendix A numbers. a arrives at 0; INV rise 1.2 / fall 0.8.
# Plain set_output_delay sets both -max and -min. set_load is seen by U3 (BUF).
create_clock -name clk -period 10.0 [get_ports clk]
set_clock_transition 0.05 [get_clocks clk]
set_input_delay 0.0 -clock clk [get_ports a]
set_input_transition 0.05 [get_ports a]
set_output_delay 1.0 -clock clk [get_ports y]
set_load 0.003 [get_ports y]
