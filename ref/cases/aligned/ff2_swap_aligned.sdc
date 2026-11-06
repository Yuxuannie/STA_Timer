# R40 aligned copy of data/sdc/ff2_swap.sdc (REPORT_P5.md §7): the P5-2..P5-4 policies neutralised;
# lines changed are marked. The comments below are the original file's.
# ff2 swap: launch latency on FF1/CK makes route A the slow one and route B the fast one.
# The clock-level latency line comes AFTER the pin-level line; the pin-level value still
# wins for FF1/CK, and FF2/CK takes the clock-level 0.3.
create_clock -name clk -period 10.0 [get_ports clk]
set_clock_transition 0.05 [get_clocks clk]
set_clock_latency 1.5 [get_pins FF1/CK]
# clock-level latency removed (P5-2)
set_input_delay 0.5 -clock clk [get_ports x]
set_input_transition 0.05 [get_ports x]
set_output_delay -max 2.0 -clock clk [get_ports y]
set_output_delay -min 0.5 -clock clk [get_ports y]
set_load 0.002 [get_ports y]
