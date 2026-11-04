# CLI (contract, P2 subset)

The stage 1 entry point and its options keep working exactly as before:
with no `--sdc`, the program does what stage 1 did (parse, link, print the
ASCII graph), and the stage 1 tests must still pass.

New in P2:

```
<entry> --lib LIB [--lib LIB ...] --verilog TOP.v --sdc FILE.sdc --dump-tsv DIR
```

- `--sdc FILE` runs the timing analysis described in `p2_semantics.md`.
- `--dump-tsv DIR` writes `endpoints.tsv`, `pins.tsv`, `paths.txt` into DIR
  (created if missing) in the format of `golden_format.md`.
- `--sdc` and `--dump-tsv` must be given together; one without the other is
  an error. With both, **stdout is empty** (the stage 1 ASCII graph is not
  printed) and the exit code is 0 on success.

Errors (any stage): exactly one line on stderr,
`<file>:<line>: <one sentence>` when a file position is known, otherwise
`error: <one sentence>`; exit code **1**. No stack traces for expected
errors, no usage text. This includes unknown options and missing required
options: the default `argparse` behavior (usage text, exit code 2) must be
overridden. Errors that stage 1 already reports keep their stage 1 message.

The later report options (`--report-timing`, `--json`, `--bundle`, ...) are
not part of P2; they are unknown options for now.
