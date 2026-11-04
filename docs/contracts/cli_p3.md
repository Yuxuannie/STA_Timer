# CLI (contract, P3 and P4 additions)

Everything in `cli_p2.md` still holds, except the rule "`--sdc` and `--dump-tsv` must be
given together", which becomes: **`--sdc` needs at least one output option**, and every
output option needs `--sdc`.

```
python -m sta_toy --lib LIB [--lib LIB ...] --verilog TOP.v --sdc FILE.sdc
       [--dump-tsv DIR]
       [--report-timing [--path-delay max|min] [--from P] [--to E] [--through Q]
                        [--max-paths N] [--nworst K] [--transition-time] [--capacitance]]
       [--report-summary]
       [--json FILE]
       [--bundle E --bundle-out FILE [--depth K] [--max-nodes N]]
```
- Output options: `--dump-tsv`, `--report-timing`, `--report-summary`, `--json`,
  `--bundle`. With `--sdc` and none of them: `error: --sdc needs an output option
  (--dump-tsv, --report-timing, --report-summary, --json or --bundle)`. Any of them
  without `--sdc`: `error: <option> needs --sdc`.
- `--path-delay` (default `max`), `--from`, `--to`, `--through`, `--max-paths`
  (default 1), `--nworst` (default 1), `--transition-time`, `--capacitance` need
  `--report-timing`; `--depth` (default 3), `--max-nodes` (default 300) and
  `--bundle-out` need `--bundle`, and `--bundle` needs `--bundle-out`. Otherwise
  `error: <option> needs <other option>`.
- `--max-paths`, `--nworst`, `--depth`, `--max-nodes` take a decimal integer ≥ 1
  (`--depth` ≥ 0); `--path-delay` takes `max` or `min`. Otherwise
  `error: <option> needs ...`.
- Flags without a value: `--report-timing`, `--report-summary`, `--transition-time`,
  `--capacitance`. Every other option takes exactly one value and may appear once
  (`--lib` may repeat).
- stdout: the report_timing text (if asked), then the summary text (if asked), nothing
  else. Files are written after every check has passed. Errors: one stderr line, exit 1,
  as in `cli_p2.md`.
