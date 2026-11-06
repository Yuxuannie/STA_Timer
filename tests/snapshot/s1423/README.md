# s1423 snapshot -- NOT an oracle

These three files are the engine's own output (`python3 -m sta_toy --lib
data/toy2.lib --verilog data/s1423.v --sdc data/sdc/s1423.sdc --dump-tsv
DIR`) at commit time of P5 / R39. They are a regression snapshot: a change in
them means the engine changed, not that it became wrong or right.

Why not an oracle: the R39 rule makes OpenSTA's `s1423` output the golden
only if the eight P2 designs correlate within 1 ps on every column. They do
not (OpenSTA 3.1.0, see `docs/notes/p5_w3.md`: CK pin slew and arrival
conventions under an ideal clock, clock latency added to input delays,
uncertainty on output ports, a missing `-min` input-delay facet), so the
engine's output is stored instead (N35: no hand-written golden for s1423).

Regenerate only on purpose, and say why in the commit.
