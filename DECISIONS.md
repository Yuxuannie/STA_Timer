# Decisions

## Assumptions

- All input errors raise one exception class, `sta_toy.StaError`, with `file`, `line` (or `None`) and `message` attributes; each module re-exports it and tests check those attributes.
- Entry points the tests rely on: `liberty.parse`/`parse_file` (R1 tree), `liberty.load`/`loads` (R2 library), `verilog.parse`/`load`, `graph.Graph`, `graph.link`.
- R4 has its own test (`test_graph_structure`) that builds a graph by hand, so the data structure can be checked before the linker exists.
- `liberate_dbx2.pdf`, present in the folder before the run and not part of the spec, is left untracked.
- Liberty numbers and identifiers are one token kind ("word": any run of characters other than whitespace, `(){}:;,"\`, or the start of a comment), stored as strings; the accessors convert numbers.
- Attribute values and group names are stored as strings with quotes removed; the tree does not record whether an attribute was written simple or complex.
- A Liberty file holds exactly one top-level group; anything after it is a parse error.
- A Liberty parse error at end of file inside a group is reported as that innermost group being unclosed, at its header line.
- A newline inside a quoted Liberty string without a `\` continuation is kept as part of the string.
- When a Liberty attribute is repeated where one value is expected (`direction`, `capacitance`, `timing_sense`, ...), the first occurrence is used.
- Two `cell` groups with the same name: the later one replaces the earlier in `Library.cells`.
- `pin (A, B)` defines one signal pin per listed name, sharing the group's attributes; a `pin` group with no name is an error.
- A `pin` without `direction` is an error at the pin group's line.
- A `related_pin` that is not a signal pin of the same cell is an error at the `related_pin` line (the linker could not build the arc otherwise).
- A `timing ()` group without `related_pin` defines no arcs.
- A missing `capacitive_load_unit`, or one without exactly two values, is an error at the library line (the graph header needs it).
- A timing group with two NLDM tables of the same header keeps the later one; `Timing.tables` is keyed by header.
- The unknown-template check runs for every NLDM table, even one that gives both indices itself; templates come from `lu_table_template` only (plus the predefined `scalar`).
- Absent indices are returned as `[]`: 1-D tables have `index_2 == []`, `scalar` tables have both empty and `values == [[v]]`.
- An NLDM table with `index_2` but no `index_1` (own or from the template) is a shape error.
- A Verilog net must be declared (as a port or wire) before the connection that uses it; the error is reported at the net name.
- Verilog redeclarations other than `output` + `wire` are errors (`input` twice, `input` + `wire`, `input` + `output`, ...), as are `input`/`output` names missing from the module port list, duplicate instance names, a pin connected twice in one instance, and an instance with an empty connection list.
- Verilog keywords (`module`, `endmodule`, `input`, `output`, `wire`) cannot be used as names.
- An error at end of file (Liberty or Verilog, outside an open Liberty group) reports the line where the file ends.
- Link-time driver checks run over nets in declaration order, so the first bad net in the netlist is reported; for a net declared both `output` and `wire`, the reported line is its first declaration.
- An input port with no loads, or an instance output pin left unconnected, is not an error; such nodes simply have no net edges.

## Interventions
