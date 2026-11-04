# Golden format (contract)

Three files per design, written by the timer with `--dump-tsv DIR` and by
`tools/oracle/oracle.py --out DIR`. Compared with `tools/diff_ref.py`.
The same layout will be produced by the OpenSTA / PrimeTime adapters in a
later stage, so it must not change.

All numbers use `fmt4` from `docs/contracts/p2_semantics.md` §10.
Undefined values are the literal `NA`. Tab-separated, `\n` line endings,
no trailing whitespace, one header line.

## endpoints.tsv

```
pin	setup_at	setup_rat	setup_slack	hold_at	hold_rat	hold_slack
```
One row per endpoint (D pins and constrained output ports), sorted by pin
name with plain string ordering. The three setup columns are
`AT[late][rf*]`, `RAT[late][rf*]`, `setup_slack[rf*]` for the setup worst
transition `rf*`; the hold columns likewise with the hold worst transition.
If a check has no defined slack for either transition, its three cells are `NA`.

## pins.tsv

```
pin	at_late_r	at_late_f	at_early_r	at_early_f	rat_late_r	rat_late_f	rat_early_r	rat_early_f	slew_late_r	slew_late_f	slew_early_r	slew_early_f
```
One row per node (every port and every instance pin, including the clock
port and CK pins), sorted by name with plain string ordering.

## paths.txt

One line per endpoint per check, endpoints in name order, `setup` before
`hold`; a check with no defined slack is omitted:
```
<endpoint> <setup|hold> <slack> : <node>(<rf>) -> <node>(<rf>) -> ... -> <endpoint>(<rf>)
```
Example:
```
FF2/D hold 2.9000 : FF1/CK(r) -> FF1/Q(f) -> U2/A(f) -> U2/Y(r) -> FF2/D(r)
```
The first node is the startpoint (a PI or a CK pin). Net edges appear as
consecutive nodes with the same transition.

## Comparison

`python3 tools/diff_ref.py <golden_dir> <actual_dir>` exits 0 only if every
cell of both TSVs and every line of `paths.txt` is identical (`--tol 0`, the
P2 setting). `--tol T` relaxes numeric cells only; `NA`, names, row sets and
path node sequences always compare exactly.
