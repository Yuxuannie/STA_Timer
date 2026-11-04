# Debug bundle, schema v1 (contract)

`debug_bundle(g, endpoint, depth=3, max_nodes=300)` returns a JSON-ready dict; the CLI
writes it with `--bundle E --bundle-out FILE [--depth K] [--max-nodes N]`, formatted
like the JSON report (indent 2, final `\n`, numbers `float(fmt4(v))`, NA → null).
The cut is made in the engine; the viewer only draws what the bundle holds.

## Cone

Start from the endpoint `e` (a D pin or constrained PO; anything else is the error
`error: --bundle x is not an endpoint`). Walk backwards over fan-in arcs (net edges
and timing() arcs, never the clock net). The **depth** of a node is the minimum
number of timing() arcs (`cell` or `ckq`) on any backward walk from `e` to it; net
edges add 0. Keep every node with depth ≤ `depth`. For a D endpoint also keep the
capture CK pin of each of its check arcs, at depth 0.

Order the kept nodes by `(depth, name)`. If there are more than `max_nodes`, keep the
first `max_nodes` and set `truncated: true`. Edges are the fan-in arcs whose both ends
are kept, plus one `check` edge per check arc of `e` (CK pin → `e`) when both are kept.

## Schema

```
{
  "schema": "sta_toy.bundle/1",
  "endpoint": <e>, "depth": K, "max_nodes": N, "truncated": bool,
  "clock": {"name": <clk>, "period": T},
  "nodes": [{"pin": <name>, "cell": <cell>|null, "kind": <timer node kind>,
             "depth": d,
             "at":   {"late": {"r": .., "f": ..}, "early": {"r": .., "f": ..}},
             "rat":  {...same shape...},
             "slew": {...same shape...},
             "slack": {"setup": .., "hold": ..},
             "cap": LOAD|null}],
  "edges": [{"u": <src>, "v": <dst>, "kind": "net"|"cell"|"ckq"|"check",
             "delay": {"late": {"rr": .., "rf": .., "fr": .., "ff": ..}, "early": {...}},
             "check": {"setup": {"r": .., "f": ..}, "hold": {"r": .., "f": ..}}|null}],
  "paths": [<path object of json_v1.md>, ...]
}
```
- Node `slack.setup` = min over rf of `RAT[late] − AT[late]`, `slack.hold` = min over
  rf of `AT[early] − RAT[early]` (only rf where both terms are defined; null if none).
- Edge `delay[m][ab]` = the delay of pair `a → b` in mode m (as in forward, with the
  source's SLEW in m), null for pairs the arc does not have or whose source slew is
  undefined. A `check` edge has `delay` null and `check` = the constraint values
  (`t_su`, `t_h` of report_p3.md §4, per D transition; null where undefined). Edge
  order: by `(v, u, kind)` names; several timing() arcs between the same pins are
  listed in graph order.
- `paths` = the endpoint's worst setup path then worst hold path (those that exist),
  ids `"setup"` and `"hold"`.
