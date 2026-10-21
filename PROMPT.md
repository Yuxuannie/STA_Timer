# Toy STA — Stage 1: Liberty + gate-level Verilog → flat timing graph (ASCII)

## 0. Purpose and who judges the result

You are building the front half of a static timing analyzer. It parses a Liberty library and a
flat gate-level Verilog netlist, links them into a pin-level timing graph, and prints the graph
as text, showing the input-pin capacitance of every cell input.

A reviewer will read this prompt and the resulting repo side by side. They will check two
things: that every requirement below can be traced to code and a test, and that nothing beyond
those requirements was built. Correctness is decided by a human-verified golden file
(section 5), not by your own judgment.

A later stage will run the same code on production TSMC Liberty files. That is why the Liberty
parser must handle the general grammar (section 3.1), even though this stage reads only a few
attributes.

## 1. Scope

### Build

Use these IDs in TRACE.md and in commit messages.

| ID | Requirement |
|----|-------------|
| R1 | Liberty parser: parse the full grammar in 3.1 into a generic tree. This layer has no knowledge of specific attribute names. |
| R2 | Liberty accessors: a thin layer over R1 that answers only the queries in 3.2. |
| R3 | Verilog parser for the subset in 3.3. |
| R4 | Graph data structure: the nodes and edges defined in 3.4. |
| R5 | Linker: netlist + library → timing graph, following the rules and errors in 3.4 and the error contract in 4.1. |
| R6 | ASCII writer (exact format in 3.5) and CLI (4.1). |
| R7 | Input files in `data/`, as specified in section 2. |
| R8 | Tests, as specified in section 5. |
| R9 | Docs: `README.md`, `TRACE.md`, `DECISIONS.md` (section 7). |

### Do not build

If you believe one of these is needed, stop and ask.

| ID | Non-goal |
|----|----------|
| N1 | Delay or slew calculation, table interpolation or extrapolation |
| N2 | Arrival, required time, slack, path reports, levelization or topological sort |
| N3 | Separate rise/fall nodes or values in the graph |
| N4 | Sequential cells, clocks, timing-check semantics (`timing_type` is stored and nothing more) |
| N5 | SDC, SPEF, wire-load models, any parasitics |
| N6 | Verilog outside 3.3: buses/vectors, `assign`, escaped identifiers, constants, multiple modules or hierarchy, positional connections |
| N7 | Interpreting CCS, ECSM, LVF or power data (the parser keeps it in the tree; nothing reads it) |
| N8 | Performance work for large libraries (this stage requires correctness only) |
| N9 | Drawing or graphics, colors, GUI, CLI options beyond 4.1, config files, logging frameworks, packaging (`setup.py`, `pyproject.toml`) |
| N10 | Third-party packages. Use the standard library only, including for tests (`unittest`). Code must run on Python 3.8 or newer. |

## 2. Inputs and where they come from

| File | Source | Your job |
|------|--------|----------|
| `data/c17.v` | Connectivity taken from the public ISCAS-85 c17 benchmark, rewritten as a mapped netlist | Write it exactly as given below |
| `data/toy.lib` | Structure follows the public Liberty standard, as found in production libraries | Write it so it contains every construct in 3.2.1 and every fixed value in 3.2.2. Choose the remaining values yourself; they must be positive, and delay/transition tables must increase along both indices. |
| `tests/golden/c17_graph.txt` | Written and checked by a human | Write it exactly as given in section 5 |

`data/c17.v` (instance U6 deliberately spans two lines):

```verilog
// ISCAS-85 c17, rewritten as a mapped gate-level netlist (named connections).
module c17 ( N1, N2, N3, N6, N7, N22, N23 );
  input  N1, N2, N3, N6, N7;
  output N22, N23;
  wire   N10, N11, N16, N19;

  ND2D1 U1 ( .A1(N1),  .A2(N3),  .ZN(N10) );
  ND2D1 U2 ( .A1(N3),  .A2(N6),  .ZN(N11) );
  ND2D1 U3 ( .A1(N2),  .A2(N11), .ZN(N16) );
  ND2D1 U4 ( .A1(N11), .A2(N7),  .ZN(N19) );
  ND2D1 U5 ( .A1(N10), .A2(N16), .ZN(N22) );
  /* last stage */
  ND2D1 U6 ( .A1(N16), .A2(N19),
             .ZN(N23) );
endmodule
```

## 3. Rules

### 3.1 Liberty grammar (R1)

- **Group**: `header ( [name[, name ...]] ) { ... }`.
  - The name list may be empty, as in `timing ()`.
  - Names may be quoted.
  - If there are several comma-separated names, keep them as a list.
  - Groups with the same header and name may repeat (for example several `timing ()` or `leakage_power ()` groups). Keep all of them, in file order.
- **Simple attribute**: `name : value ;`. The value is a number, an identifier or a quoted string.
- **Complex attribute**: `name ( v1, v2, ... ) ;`.
  - Each value is a number, an identifier or a quoted string.
  - A quoted string may contain commas and spaces, for example `"0.1, 0.2"`.
  - The same name may repeat within a group (for example `define`). Keep all occurrences, in order.
- **Lexical rules**:
  - `/* ... */` comments may span lines and may appear anywhere whitespace may.
  - A `\` at the end of a line is a line continuation, inside or outside quotes.
  - Numbers may use scientific notation, for example `1.25e-03`.
- **Unknown names**: unknown group headers and attribute names are parsed and kept, never rejected or dropped. Production libraries contain many of them (`ocv_*`, `internal_power`, `pg_pin`, `receiver_capacitance`, and others).
- **Line numbers**: every group and attribute records its source line. A parse error reports `file:line` and stops.

### 3.2 Liberty semantics used by the accessors (R2)

The accessors answer only these queries:

- the library name;
- `capacitive_load_unit`;
- looking up a cell by name;
- the signal pins of a cell, in file order;
- for each pin: `direction`, `capacitance`, `rise_capacitance`, `fall_capacitance`;
- the timing groups of a pin;
- the NLDM tables of a timing group.

Semantic rules:

- **Signal pins** are `pin` groups only. `pg_pin` groups are not pins. `direction` must be `input` or `output`. Any other value is an error that names the cell and the pin.
- **Graph capacitance**: the cap shown in the graph is `capacitance`. The accessor also exposes `rise_capacitance` and `fall_capacitance`, but the graph does not print them. An input pin without `capacitance` is an error.
- **Timing groups**: a `timing ()` group belongs to the pin that contains it (the *owner*).
  - It defines an arc from each pin listed in `related_pin` to the owner. `related_pin` is a whitespace-separated list.
  - Each arc carries `timing_sense`, `timing_type` (default `combinational`) and `when` (default empty).
  - Several timing groups may connect the same (related pin, owner) pair. Keep all of them.
- **NLDM tables**: a child group of `timing ()` whose header is exactly `cell_rise`, `cell_fall`, `rise_transition` or `fall_transition`. Headers that merely contain these words, such as `ocv_sigma_cell_rise`, are not NLDM tables.
  - The group name is the template name.
  - A table consists of:
    - `index_1` and `index_2`: floats, parsed from quoted comma-separated lists;
    - `values`: one row per quoted string.
  - If `index_1` or `index_2` is missing from the table, take it from the `lu_table_template` with that name. If the template has no `index_2` either, the table is 1-D.
  - Table shapes:
    - **2-D**: `len(index_1)` rows of `len(index_2)` values.
    - **1-D**: one quoted string with `len(index_1)` values.
    - **`scalar`**: a predefined template that needs no `lu_table_template`. It has no indices and one value.
    - Any other shape is an error.
  - Tables are stored as numbers only. Nothing interpolates them (N1).
- **When validation happens**: all the checks above (direction, missing capacitance, table shape, unknown template) run when the library is loaded. They cover every cell and every table, including cells the netlist does not use. Each error reports the line of the offending group or attribute.
- **Return types**:
  - the cap unit is a tuple `(float, str)`, for example `(1.0, 'pf')`;
  - an index is a `list` of `float`;
  - `values` is a `list` of row `list`s of `float`.

#### 3.2.1 Constructs that `data/toy.lib` must contain (each at least once)

- **Top of file**: a multi-line `/* */` comment.
- **Library level**:
  - `technology (cmos);`
  - `delay_model : table_lookup;`
  - `time_unit`, `voltage_unit`, `current_unit`, `leakage_power_unit` (quoted)
  - `capacitive_load_unit (1, pf);`
  - `nom_process`, `nom_voltage`, `nom_temperature`
  - one `operating_conditions` group, plus `default_operating_conditions`
  - two `define (...)` complex attributes (the name repeats)
  - `lu_table_template (delay_template_3x3)`
  - `power_lut_template (power_template_3x3)`
- **Two cells**: `ND2D1` (used by the netlist) and `INVD1` (unused). Each has:
  - `area`
  - `cell_leakage_power` written in scientific notation
  - at least two `leakage_power ()` groups, each with a `when`
  - `pg_pin (VDD)` and `pg_pin (VSS)`
- **Input pins**:
  - `related_power_pin` and `related_ground_pin`
  - `rise_capacitance_range (...)` and `fall_capacitance_range (...)`
  - one `internal_power ()` group
- **Output pins**:
  - `function`
  - `max_capacitance`
  - one `internal_power ()` group
- **Every `timing ()` group**:
  - `cell_rise`, `rise_transition`, `cell_fall`, `fall_transition`
  - `ocv_sigma_cell_rise` and `ocv_sigma_cell_fall`, each with `sigma_type`
- **Line continuations**: `values` blocks are written across lines with `\` continuations.

#### 3.2.2 Fixed values in `data/toy.lib` (the tests assert these)

| Item | Value |
|------|-------|
| library name | `toy_lib` |
| `capacitive_load_unit` | `(1, pf)` |
| `lu_table_template (delay_template_3x3)` | `variable_1 : input_net_transition;` `variable_2 : total_output_net_capacitance;` `index_1 ("0.005, 0.02, 0.08");` `index_2 ("0.0005, 0.002, 0.008");` |
| ND2D1 pin order | `A1`, `A2`, `ZN` |
| ND2D1 / A1 | `input`, `capacitance : 0.00071`, `rise_capacitance : 0.00070`, `fall_capacitance : 0.00072` |
| ND2D1 / A2 | `input`, `capacitance : 0.00064`, `rise_capacitance : 0.00063`, `fall_capacitance : 0.00065` |
| ND2D1 / ZN | `output`, `function : "!(A1&A2)"`. Two `timing ()` groups, in this order: `related_pin : "A1"`, then `related_pin : "A2"`. Both are `negative_unate` and `combinational`. |
| ND2D1 A1→ZN `cell_rise` | exactly the block below |
| INVD1 | pins `I` (`input`, `capacitance : 0.00055`) and `ZN` (`output`, `function : "!I"`). One timing group, `I`→`ZN`. Its four NLDM tables omit `index_1`/`index_2`, so the template fallback is exercised. |

```
        cell_rise (delay_template_3x3) {
          index_1 ("0.005, 0.02, 0.08");
          index_2 ("0.0005, 0.002, 0.008");
          values ("0.0110, 0.0175, 0.0420", \
                  "0.0135, 0.0200, 0.0445", \
                  "0.0210, 0.0280, 0.0530");
        }
```

### 3.3 Verilog subset (R3)

- One `module name ( port, ... );` ... `endmodule`.
- `input`, `output` and `wire` declarations. Names are comma-separated, scalars only, and a declaration may span lines.
- Instances: `CELL INST ( .PIN(NET), ... );`. An instance may span lines. Connections are by name only. Every NET must be a declared port or wire.
- Comments: `//` and `/* */`.
- Identifiers: `[A-Za-z_][A-Za-z0-9_$]*`.
- A net may be declared both as an `output` and as a `wire`. This is allowed.
- Each of the following is an error:
  - an empty connection `.PIN()`;
  - a port in the header with no `input`/`output` declaration;
  - a connection to a `pg_pin`, which counts as an unknown pin (3.4).
- Anything else not described above is an error that reports `file:line`. This includes a positional connection.

### 3.4 Graph rules (R4, R5)

- **Nodes**:
  - one per primary input port (PI);
  - one per primary output port (PO);
  - one per signal pin of each instance, named `<inst>/<pin>`. This covers every lib pin of the cell except `pg_pin`, whether or not it is connected.
- **Net edges**: for each net, one edge from its driver to each of its loads.
  - The driver is a PI port or an instance output pin.
  - A load is an instance input pin or a PO port.
  - Every port, and every wire that appears in at least one connection, must have exactly one driver. A declared wire that is never connected is ignored.
- **Cell edges**: for each timing group of an instance's cell, one edge from `<inst>/<related pin>` to `<inst>/<owner pin>`.
  - Timing groups with the same (from, to) pair merge into one edge.
  - That edge's annotation lists their distinct `timing_sense` values in file order, separated by commas. A group with no `timing_sense` contributes `none`.
- **Link errors**: each of the following stops the run. The message names the offending cell, pin or net, and the line follows 4.1.
  - unknown cell;
  - unknown pin on a cell;
  - a net with zero drivers;
  - a net with more than one driver.

### 3.5 ASCII format (R6)

- **Line 1**: `# design <module> | library <library name> | cap_unit <v><unit>`. Here `<v>` is the first `capacitive_load_unit` value formatted with `{:g}`, and `<unit>` is the second value.
- **Line 2**: `# nodes <N> | edges <E> (net <En>, cell <Ec>)`
- **Node order**:
  1. PI ports, in the order of the `input` declarations;
  2. instances, in netlist order, each with its pins in lib file order;
  3. PO ports, in the order of the `output` declarations.
- **Node lines**, one of:
  - `<name> [PI]`
  - `<name> [PO]`
  - `<inst>/<pin> [<cell> input cap=<c>]`
  - `<inst>/<pin> [<cell> output]`

  Here `<c>` is `capacitance` formatted with `{:g}`.
- **Edge lines** follow their source node, indented by two spaces:
  - `  net  -> <target>  cap=<c>` when the target is an instance input pin;
  - `  net  -> <target>  PO` when the target is a PO port;
  - `  cell -> <target>  <senses>`.
- **Edge order**:
  - Under one source pin, cell edges come before net edges.
  - Net edges: instance netlist order, then lib pin order within an instance, then PO ports in declaration order.
  - Cell edges: target pins in lib file order.
- **Whitespace**: `\n` line endings, a final newline, no trailing spaces.

## 4. Interfaces and layout

### 4.1 CLI

`python -m sta_toy --lib <file> --verilog <file>` prints the graph to stdout and exits with 0.

There are no other options, and no `-h` (do not use `argparse`).

**Error contract.** Every error stops the run, exits with 1, prints nothing to stdout, and
writes exactly one line to stderr:

- **Format**: `ERROR <file>:<line>: <message>`.
  - `<file>` is the path exactly as given on the command line.
  - `<message>` contains the name of the offending cell, pin or net.
- **Which line is reported**:

  | Error | Line reported |
  |-------|---------------|
  | Liberty parse error | the line of the offending token. For an unclosed group: the line of that group's header. |
  | Liberty semantic error (3.2) | the line of the offending group or attribute |
  | Verilog error (3.3) | the line of the offending token |
  | Unknown cell | the line containing the cell name of that instance |
  | Unknown pin | the line containing that `.PIN(` |
  | Net with zero or several drivers | the line of the net's `input`/`output`/`wire` declaration |

- **Errors with no line**:
  - an unreadable file: `ERROR <file>: <message>`;
  - bad or missing arguments: `ERROR: usage: python -m sta_toy --lib <file> --verilog <file>`.
- **Processing order**: the library is read first, then the netlist, then they are linked. The first error stops the run.

### 4.2 Repo layout

```
PROMPT.md          this prompt, verbatim
README.md          how to run the tool and the tests (10 lines at most)
TRACE.md           requirement → code → test (section 7)
DECISIONS.md       assumptions and deviations (section 7)
data/c17.v
data/toy.lib
sta_toy/__init__.py  __main__.py  liberty.py  verilog.py  graph.py  writer.py
tests/test_liberty.py  test_verilog.py  test_graph.py
tests/golden/c17_graph.txt
```

## 5. Oracle

The golden output for `python -m sta_toy --lib data/toy.lib --verilog data/c17.v` is the
following, byte for byte. Write it to `tests/golden/c17_graph.txt` exactly as shown, followed
by a single `\n`.

```
# design c17 | library toy_lib | cap_unit 1pf
# nodes 25 | edges 26 (net 14, cell 12)
N1 [PI]
  net  -> U1/A1  cap=0.00071
N2 [PI]
  net  -> U3/A1  cap=0.00071
N3 [PI]
  net  -> U1/A2  cap=0.00064
  net  -> U2/A1  cap=0.00071
N6 [PI]
  net  -> U2/A2  cap=0.00064
N7 [PI]
  net  -> U4/A2  cap=0.00064
U1/A1 [ND2D1 input cap=0.00071]
  cell -> U1/ZN  negative_unate
U1/A2 [ND2D1 input cap=0.00064]
  cell -> U1/ZN  negative_unate
U1/ZN [ND2D1 output]
  net  -> U5/A1  cap=0.00071
U2/A1 [ND2D1 input cap=0.00071]
  cell -> U2/ZN  negative_unate
U2/A2 [ND2D1 input cap=0.00064]
  cell -> U2/ZN  negative_unate
U2/ZN [ND2D1 output]
  net  -> U3/A2  cap=0.00064
  net  -> U4/A1  cap=0.00071
U3/A1 [ND2D1 input cap=0.00071]
  cell -> U3/ZN  negative_unate
U3/A2 [ND2D1 input cap=0.00064]
  cell -> U3/ZN  negative_unate
U3/ZN [ND2D1 output]
  net  -> U5/A2  cap=0.00064
  net  -> U6/A1  cap=0.00071
U4/A1 [ND2D1 input cap=0.00071]
  cell -> U4/ZN  negative_unate
U4/A2 [ND2D1 input cap=0.00064]
  cell -> U4/ZN  negative_unate
U4/ZN [ND2D1 output]
  net  -> U6/A2  cap=0.00064
U5/A1 [ND2D1 input cap=0.00071]
  cell -> U5/ZN  negative_unate
U5/A2 [ND2D1 input cap=0.00064]
  cell -> U5/ZN  negative_unate
U5/ZN [ND2D1 output]
  net  -> N22  PO
U6/A1 [ND2D1 input cap=0.00071]
  cell -> U6/ZN  negative_unate
U6/A2 [ND2D1 input cap=0.00064]
  cell -> U6/ZN  negative_unate
U6/ZN [ND2D1 output]
  net  -> N23  PO
N22 [PO]
N23 [PO]
```

The tests must assert at least the following. Every expected value comes from this prompt, never
from running your own code.

Tests import modules (`from sta_toy import liberty`), not individual names. That way, a function
from a later requirement that doesn't exist yet fails only its own tests.

**`test_liberty.py`**
- The library name is `toy_lib` and the cap unit is `(1.0, 'pf')`.
- `define` appears twice.
- The library has 2 cells.
- ND2D1's signal pins are exactly `[A1, A2, ZN]`, with `pg_pin` excluded.
- All three capacitances of A1 and A2 match 3.2.2.
- ZN has 2 timing groups, with related pins A1 and A2, `negative_unate` and `combinational`.
- For the A1→ZN `cell_rise` table, `index_1 == [0.005, 0.02, 0.08]` and `values[2][1] == 0.0280`.
- `ocv_sigma_cell_rise` exists in the generic tree but is not returned as an NLDM table.
- INVD1's table indices come from the template.
- At least 2 `leakage_power` groups are kept.
- A library string whose `pin (A) {` group is never closed raises an error that reports that header's line.
- Three small inline library strings each raise an error that reports the expected line:
  - `direction : inout;`
  - an input pin with no `capacitance`
  - a `values` table with 2 rows where the template has 3 `index_1` entries

**`test_verilog.py`**
- c17 parses to 7 ports with the correct directions, 4 wires and 6 instances, and U6's connections are correct.
- A positional connection raises an error that contains its line number.

**`test_graph.py`**
- The CLI output is byte-identical to `tests/golden/c17_graph.txt`.
- An inline fixture (a small lib string and netlist string inside the test) checks merging and splitting. Its cell has inputs A, B, C and output Z.
  - Two `timing ()` groups use `related_pin : "A"`, with different `when` and senses `positive_unate` then `negative_unate`. The test asserts they become one edge A→Z annotated `positive_unate,negative_unate`.
  - One group uses `related_pin : "B C"` with `positive_unate`. The test asserts it yields two edges, B→Z and C→Z.
- **Link errors (R5)**: one inline case per link error in 3.4. Each calls the linker and asserts that the error carries the file, the line given by 4.1, and the offending name.
- **CLI error path (R6)**: one netlist with an unknown cell. Through the CLI, it must exit with 1, leave stdout empty, and produce a stderr line that starts with `ERROR <path>:<line>:`.

**Immutability**: the golden file and the fixed values in 3.2.2 are immutable. If your output
differs from them, fix the code. If you believe the golden contradicts a rule in section 3, stop
and report the exact line and rule. Do not edit the golden.

## 6. Process

1. **Commit 1** contains `data/`, `tests/golden/`, all the tests, and a `DECISIONS.md` with its two section headings. The tests are expected to fail at this point.
2. Implement R1 → R6 in that order, one commit each. Each message starts with `R<n>:`. Run the full test suite before every commit. Tests that cover requirements already implemented must pass; tests for later requirements may still fail. From the R6 commit on, the whole suite must pass.
3. **Final commit**: `README.md`, `TRACE.md` and `PROMPT.md`. `DECISIONS.md` is appended to in whichever commit makes each decision.
4. Never weaken, skip or delete a test in order to make it pass.
5. Run to completion without asking for confirmation. The exceptions are the stop conditions: a contradiction with the golden (section 5), or a non-goal that seems necessary (section 1).
6. Where this prompt is silent, choose the simplest option that satisfies it, and record one line in `DECISIONS.md`.
7. If you use subagents for review, give them read-only tools.

## 7. Definition of done

- `python -m unittest discover -s tests` passes.
- The CLI output for c17 matches the golden byte for byte.
- `TRACE.md` has one row per R1–R9, in the form `ID | file[:function] | test name`. Use `-` in a column that doesn't apply, for example the function column for a data file.
- `DECISIONS.md` has two sections:
  - **Assumptions**: one line per choice made where this prompt was silent.
  - **Interventions**: left empty, for the human to log any mid-run correction.
- There are no imports outside the standard library.
- `git diff <commit 1> HEAD -- data tests/golden` is empty: the inputs and the golden were not touched after commit 1.
