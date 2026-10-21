# Decisions

## Assumptions

- All input errors raise one exception class, `sta_toy.StaError`, with `file`, `line` (or `None`) and `message` attributes; each module re-exports it and tests check those attributes.
- Entry points the tests rely on: `liberty.parse`/`parse_file` (R1 tree), `liberty.load`/`loads` (R2 library), `verilog.parse`/`load`, `graph.Graph`, `graph.link`.
- R4 has its own test (`test_graph_structure`) that builds a graph by hand, so the data structure can be checked before the linker exists.
- `liberate_dbx2.pdf`, present in the folder before the run and not part of the spec, is left untracked.

## Interventions
