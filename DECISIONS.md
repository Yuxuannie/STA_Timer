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

## Interventions
