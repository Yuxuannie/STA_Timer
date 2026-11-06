# s1423 (ISCAS-89)

- Source: `https://www.pld.ttu.ee/~maksim/benchmarks/iscas89/bench/s1423.bench`
  (Tallinn University of Technology mirror of the ISCAS-89 set), downloaded
  2026-11-05.
- sha256 of `data/bench/s1423.bench`:
  `e99d9e45b4fb1ceb849977590e18a7efe6d005e5bc583dbbaf3da79671cbe057`
- Header of the file: 17 inputs, 5 outputs, 74 D flip-flops, 167 inverters,
  490 gates (197 AND, 64 NAND, 137 OR, 92 NOR). Fan-in: 2 AND3, 3 NAND3,
  2 NAND4, 2 NOR3, 2 NOR4, 1 OR4, the rest 1 or 2 inputs.

## Conversion

```
python3 tools/bench2v.py data/bench/s1423.bench data/s1423.v --top s1423
```

Instance counts printed by the tool (748 instances, of which 9 come from the
decomposition of the 3- and 4-input gates into 2-input trees):

```
AND2   206
DFF    74
INV    167
NAND2  64
NOR2   92
OR2    145
total  748
```

Ports: `clk` (added, drives every `DFF/CK`), `G0` ... `G16`; outputs `G726`,
`G729`, `G702`, `G727`, `G701BF`. `tests/test_bench2v.py` checks that
`data/s1423.v` is exactly the output of the tool.

## Constraints: `data/sdc/s1423.sdc`

- `create_clock -name clk -period 75.6`, `set_clock_transition 0.05`.
- Every PI: `set_input_delay 0.5`, `set_input_transition 0.05` (a grid
  point of the `toy2.lib` slew axis).
- Every PO: `set_output_delay 0.5`, `set_load 0.004` (a grid point of the
  capacitance axis).

The period was picked after a first run at 100 ns: the worst setup arrival is
`FF70/D` at 79.0795 with a setup time of 0.3061, so a period of 75.6 gives a
setup WNS of -3.7856 (-5.0 % of the period). Engine results at 75.6
(`python3 -m sta_toy --lib data/toy2.lib --verilog data/s1423.v --sdc
data/sdc/s1423.sdc --dump-tsv DIR`):

| | value |
|---|---|
| endpoints | 79 (74 D pins, 5 POs) |
| setup WNS / TNS / NVP | -3.7856 / -7.4815 / 3 |
| hold WNS / NVP | 2.6000 / 0 (met) |
| pins.tsv rows | 2100 |
| engine run time (`--dump-tsv`) | 0.8 s (python3 3.9.6), 1.2 s (python3.12) |
