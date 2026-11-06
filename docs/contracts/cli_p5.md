# CLI (contract, P5 additions)

Everything in `cli_p2.md` and `cli_p3.md` still holds, except where this file says
otherwise.

```
python -m sta_toy --lib A.lib [--lib B.lib ...] --verilog TOP.v --sdc FILE.sdc
       [the P2 / P3 output options of cli_p3.md]
       [--check-timing]
       [--trace PIN]
python -m sta_toy.viewer ... [--scale S]
```

- `--check-timing` (a flag) prints the check_timing report of `check_timing.md` on
  stdout; exit 0.
- `--trace PIN` (one value, may appear once) prints the trace text of `trace.md` for
  endpoint `PIN` on stdout; exit 0. `PIN` that is not an endpoint of the run:
  `error: --trace PIN is not an endpoint` (with the pin name in place of `PIN`), exit 1,
  nothing written.
- Both count as output options: `--sdc` needs at least one of `--dump-tsv`,
  `--report-timing`, `--report-summary`, `--json`, `--bundle`, `--check-timing`,
  `--trace`, and each of them needs `--sdc`. The message for `--sdc` alone becomes
  `error: --sdc needs an output option (--dump-tsv, --report-timing, --report-summary,
  --json, --bundle, --check-timing or --trace)`.
- They may be combined with every other option. stdout order: the report_timing text,
  the summary text, the check_timing report, the trace text. Files are still written
  after every check has passed (an unknown `--trace` pin writes no file).
- `--scale S` belongs to the viewer (owner W1): `S` a decimal number in 0.6..2.0; out of
  range or not a number is one stderr line, exit 1.

## Ignored timing arcs (R35)

A `timing()` group the timer does not support is ignored and counted
(`p2_semantics.md` "Changes in P5"). At the end of every `--sdc` run that ignored at
least one arc, after stdout and every file has been written, exactly one line goes to
stderr and the exit code stays 0:

```
warning: <n> timing arcs ignored (run --check-timing)
```

`<n>` is the section 6 count of `check_timing.md` (also when `--check-timing` is
given). A run that ignored nothing prints nothing on stderr. No warning is printed for
lookups outside a table grid; those appear only in `--check-timing`.

## Errors

The error contract of `cli_p2.md` is unchanged: one stderr line, exit 1, no usage text,
nothing on stdout, no file written. The order of `p2_semantics.md` §10 holds; the
timing-graph stage no longer reports unsupported `timing_type` / `timing_sense`.
