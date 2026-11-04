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
R10 | sta_toy/liberty.py | load (Table.variables, Pin.is_clock, TABLE_KINDS) | test_liberty.TimingAccessorTests: test_template_variables, test_flop_arcs, test_table_index_overrides_template; test_lookup.TemplateOrderTests
R11 | sta_toy/lookup.py | bilinear, lookup | test_lookup.InterpolationTests.test_points (R19b); test_lookup.TemplateOrderTests: test_buf_cell_rise, test_dff_hold_rise_constraint (R19c)
R12 | sta_toy/timer.py | build | test_timer.GraphTests: test_node_classes, test_clock_net_not_in_graph, test_no_d_to_q_edge, test_cell_and_net_arcs, test_check_arcs, test_loads; test_cli.ErrorContractTests: test_clock_port_drives_non_clock_pin, test_unsupported_timing_type
R13 | sta_toy/sdc.py, sta_toy/timer.py | sdc.parse, sdc.load, timer.check_sdc | test_sdc.ParseTests (every command form, each syntactic error class); test_cli.SdcSemanticErrorTests (each semantic error class)
R14 | sta_toy/timer.py | clock_latency, set_sources, check | test_timer.ForwardTests.test_pin_latency_beats_later_clock_latency; test_timer.CheckTests.test_ff2_scenarios (skew, unc); test_cli.GoldenTests.test_designs (ff2_swap, ff2_skew, ff2_unc, ff2_holdviol)
R15 | sta_toy/timer.py | topological_order, forward, arc_delay | test_timer.ForwardTests: test_two_routes_late_max_early_min, test_rise_fall_split, test_unset_facets_and_worst_slew, test_combinational_loop; test_cli.ForwardTieTests.test_tie; test_cli.ErrorContractTests.test_combinational_loop
R16 | sta_toy/timer.py | check | test_timer.CheckTests: test_ff2_scenarios, test_output_port_required_times, test_extrapolated_constraint, test_endpoints
R17 | sta_toy/timer.py | backward | test_timer.BackwardTests: test_fanout_merge, test_missing_facet_propagates_na; test_cli.GoldenTests.test_designs (pins.tsv RAT columns)
R18 | sta_toy/timer.py, sta_toy/tsv.py, sta_toy/__main__.py | slack, worst_rf, worst_path, tsv.fmt4, tsv.dump, main, arguments | test_cli.GoldenTests: test_designs, test_second_library; test_cli.ForwardTieTests.test_tie; test_cli.CliTests
R19 | tests/test_liberty.py, tests/test_lookup.py, tests/test_timer.py, tests/test_sdc.py, tests/test_cli.py | - | R19a test_cli.GoldenTests; R19b test_lookup.InterpolationTests; R19c test_lookup.TemplateOrderTests; R19d test_sdc.ParseTests, test_cli.SdcSemanticErrorTests; R19e test_cli.ErrorContractTests; R19f stage 1 tests (test_graph.CliTests.test_golden); R19g test_cli.ForwardTieTests; R19h test_cli.CliTests
R20 | README.md, TRACE.md, DECISIONS.md | - | -
