# SDC subset (contract)

Tcl-looking syntax, parsed line by line without a Tcl interpreter.

## Lexical rules

- One command per line. `#` starts a comment to end of line. Blank lines are ignored.
- Tokens are separated by whitespace. A token matching `-?[0-9]+(\.[0-9]+)?` is a
  **number**, never an option, so `-0.5` is the value minus 0.5.
- A token starting with `-` that is not a number is an **option**. Only the
  options listed below exist.
- The line may end with one object list: `[get_ports NAME]`, `[get_pins NAME]`
  or `[get_clocks NAME]`, where NAME is one literal name (no wildcards, no
  spaces, no braces, no nested lists).
- Options and the value may appear in any order (`set_input_delay 0.5 -clock clk [...]`
  and `set_input_delay -clock clk 0.5 [...]` are the same command).

## Commands

```
create_clock -name N -period P [get_ports PORT]          # exactly one per file; PORT is an input port
set_clock_transition V [get_clocks N]                     # slew at every CK pin of N; default 0
set_clock_latency V [get_clocks N]                        # latency of every CK pin of N; default 0
set_clock_latency V [get_pins INST/PIN]                   # latency of one CK pin
set_clock_uncertainty V [get_clocks N]                    # sets both the setup and the hold facet
set_clock_uncertainty -setup V [get_clocks N]
set_clock_uncertainty -hold V [get_clocks N]
set_input_delay V -clock N [get_ports PORT]               # sets both the min and the max facet
set_input_delay -max V -clock N [get_ports PORT]
set_input_delay -min V -clock N [get_ports PORT]
set_output_delay V -clock N [get_ports PORT]              # sets both facets
set_output_delay -max V -clock N [get_ports PORT]
set_output_delay -min V -clock N [get_ports PORT]
set_input_transition V [get_ports PORT]                   # both r and f; default 0
set_load V [get_ports PORT]                               # extra load on an output port; default 0
```

This list is exhaustive: any other command, option, object-list kind,
missing or extra token, or a line with both `-min` and `-max` (or both
`-setup` and `-hold`) is an error.

## Facets and overriding

Values with facets are stored per facet: `set_input_delay` and
`set_output_delay` have a `min` and a `max` facet per port;
`set_clock_uncertainty` has a `setup` and a `hold` facet. A later line
replaces only the facet(s) it names; the plain form replaces both. A facet
never set is 0. Example from `ff2_unc.sdc`: `set_clock_uncertainty 0.3`
then `set_clock_uncertainty -setup 0.5` gives setup 0.5, hold 0.3.

`set_clock_latency` on `[get_pins INST/CK]` always wins over the clock-level
value for that pin, regardless of the order of the two lines
(`ff2_swap.sdc` puts the pin line first). Two lines for the same pin, or two
clock-level lines: the later one wins.

## Order

Commands are applied in file order. `create_clock` must come before any line
that names its clock (`-clock N` or `[get_clocks N]`); otherwise that line is
an error ("clock N is not defined").

## Errors (all stop the run, exit code 1, one line with file name and line number)

Syntactic (detected by the parser module without the design):
unknown command; unknown option; both `-min` and `-max` (or `-setup` and
`-hold`) on one line; missing value; missing or malformed object list;
wildcard or multiple names in an object list; `-clock` missing on
`set_input_delay` / `set_output_delay`; second `create_clock`; a command
other than `create_clock` naming a clock before it is created.

Semantic (detected when the constraints are applied to the linked design):
`get_ports` naming a non-existent port; `get_pins` naming a non-existent pin
or a pin that is not a CK pin; `get_clocks` or `-clock` naming a non-existent
clock; `create_clock` on an output port; `set_input_delay`,
`set_input_transition` or `set_load` on the clock port; `set_input_delay` /
`set_input_transition` on an output port; `set_output_delay` / `set_load` on
an input port; no `create_clock` in the file.

## Module structure

The SDC parser is a separate module that turns a file into a plain
constraint object and raises the syntactic errors above; it has its own unit
tests (one valid file using every command form including a negative value,
and one test per syntactic error class). Semantic errors are raised where the
constraints are applied to the design and are tested through the CLI (exit 1,
one line on stderr).
