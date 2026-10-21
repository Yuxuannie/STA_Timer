# Trace

ID | file | function | test name
---|---|---|---
R1 | sta_toy/liberty.py | parse, parse_file | test_liberty.TreeTests: test_grammar_constructs, test_define_kept_twice, test_leakage_power_groups_kept, test_tree_keeps_ocv_sigma, test_unclosed_group_reports_header_line
R2 | sta_toy/liberty.py | load, loads | test_liberty.AccessorTests: test_name_and_cap_unit, test_cell_count, test_nd2d1_signal_pins, test_input_capacitances, test_zn_timing_groups, test_cell_rise_table, test_ocv_sigma_not_nldm, test_invd1_indices_from_template, test_error_bad_direction, test_error_input_without_capacitance, test_error_table_shape
R3 | sta_toy/verilog.py | parse, load | test_verilog.VerilogTests: test_c17, test_positional_connection_error
R4 | sta_toy/graph.py | Graph | test_graph.GraphStructureTests: test_graph_structure
R5 | sta_toy/graph.py | link | test_graph.LinkTests: test_merge_and_split, test_unknown_cell, test_unknown_pin, test_net_without_driver, test_net_with_two_drivers
R6 | sta_toy/writer.py, sta_toy/__main__.py | write, main | test_graph.CliTests: test_golden, test_unknown_cell_error
R7 | data/c17.v, data/toy.lib | - | test_verilog.VerilogTests.test_c17, test_liberty.AccessorTests (3.2.2 values), test_graph.CliTests.test_golden
R8 | tests/test_liberty.py, tests/test_verilog.py, tests/test_graph.py, tests/golden/c17_graph.txt | - | -
R9 | README.md, TRACE.md, DECISIONS.md | - | -
