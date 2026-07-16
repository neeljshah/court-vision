# Analytics Verification Contract -- binding, for ANY LLM client

Parent contract: [docs/AI_CONSUMER_CONTRACT.md](AI_CONSUMER_CONTRACT.md). Read
that first -- it defines the resolver envelope, the refusal rules, and the
no-edge-claims boundary that this document inherits without restating.

## 1. What this layer is

The analytics-verification layer is a claims-verification system, not a
claims-generation one. Every displayed analytics stat on this platform
(attribution, calibration decay, sentinel checks, contradiction scans) is
backed by a receipt file that names its own inputs, its own age, and whether
it has been independently re-derived and found to match. An AI answering a
question about "how good is this claim / is this stat still trustworthy" must
route through these receipts, never assert trustworthiness from memory.

## 2. The four artifacts

All four live under `data/cache/analytics_verify/` and are LOCAL-only
(gitignored -- absent from a fresh clone until their producer has run).
Every artifact carries `generated_at` (or `as_of`), `edge_claimed` (must be
`false`), and an `honest_note`.

| Artifact | Producer (refresh with) | Schema (top-level keys) |
|---|---|---|
| `attribution_rollup.json` | `python -m scripts.platformkit.analytics_verify.attribution` | `generated_at, edge_claimed, honest_note, link_method_mix, join_rates, by_family: {family: {n_bets, n_settled, mean_clv_pct, median_clv_pct, pct_beat_close, flat_units_result, n_proxy_close}}, by_card: {...}` |
| `claim_survival.json` | `python -m scripts.platformkit.analytics_verify.regrader` | `generated_at, edge_claimed, honest_note, n_cards_total, n_eligible, verdict_counts, survival: {7d/30d/60d fractions or null}, decayed_cards, insufficient_cards` |
| `sentinel_report.json` | `python -m scripts.platformkit.analytics_verify.sentinel` | `as_of, edge_claimed, honest_note, checks: [{stat, served_value, recomputed_value, delta, verdict, ...}], n_verified, n_discrepant, n_stale, n_uncheckable, overall` |
| `contradiction_report.json` | `python -m scripts.platformkit.analytics_verify.contradiction` | `as_of, edge_claimed, honest_note, families_scanned, n_claims, conflicts: [...], by_family_consistency, n_conflicts_by_kind` |
| `system_map.json` | `python -m scripts.platformkit.analytics_verify.system_map` | `generated_at, edge_claimed, honest_note, n_nodes, n_edges, n_verified, n_unverified, nodes: [{id, kind, path, description, verified, mtime}], edges: [{src, dst, relation}]` |

Extra/unknown keys in any artifact are tolerated by the resolvers (lenient
reading); nothing outside the schema above is guaranteed present.

## 3. How to query -- the resolver registry

Route every analytics-verification question through
`scripts/platformkit/answers/resolver_registry.py`, exactly as
`AI_CONSUMER_CONTRACT.md` rule 1 requires for any other question type. Four
new categories are registered:

- `analytics_attribution` (args: `family?`, `card_id?`)
- `analytics_claim_survival` (no args)
- `analytics_verification` (args: `stat?`)
- `analytics_contradictions` (args: `family?`)
- `system_map` (args: `node?`) -- "how does the system work / what produces X /
  what consumes Y"; whole-graph summary if `node` omitted, else that node's
  `produced_by`/`consumed_by` edges. Curated dataflow graph, disk-verified per
  node, `edge_claimed: false`; see [PLATFORM.md](PLATFORM.md#system-intelligence-map-machine-readable-dataflow-graph).

```python
from scripts.platformkit.answers import resolver_registry as R

env = R.resolve("show me the clv attribution for player_prop", sport="nba",
                 category="analytics_attribution", family="player_prop")
```

Example `ok` response:

```json
{
  "status": "ok",
  "category": "analytics_attribution",
  "sport": "nba",
  "source_artifact": "data/cache/analytics_verify/attribution_rollup.json",
  "as_of": "2026-07-15T12:00:00+00:00",
  "family": "player_prop",
  "receipt": {"n_bets": 40, "n_settled": 40, "mean_clv_pct": 1.2, "pct_beat_close": 0.55}
}
```

The underlying resolvers also live directly in
`scripts.platformkit.analytics_verify.answers` (`attribution`,
`claim_survival`, `verification`, `contradictions`) if a caller needs to
bypass free-text classification and call a category explicitly, or via CLI:

```
python -m scripts.platformkit.analytics_verify.answers attribution --family player_prop
python -m scripts.platformkit.analytics_verify.answers claim_survival
python -m scripts.platformkit.analytics_verify.answers verification --stat mean_clv_pct
python -m scripts.platformkit.analytics_verify.answers contradictions --family player_prop
```

### Fail-closed semantics

Every resolver call gates through three checks, in order, before it will
return a number:

1. **Artifact absent** (producer hasn't run in this clone) -> `status:
   "no_data"`.
2. **Artifact not stamped `edge_claimed: false`** (missing key or any
   truthy value) -> `status: "refused"`. This engine reports calibration and
   verification facts, never a dollar edge -- an artifact that doesn't
   explicitly disclaim edge is not trusted, not displayed.
3. **Artifact older than 48h**, or its `as_of`/`generated_at` is
   unparseable -> `status: "refused"` naming the age.

A `family`/`card_id`/`stat` filter that matches zero rows in an otherwise
valid artifact is also `status: "no_data"` -- refuse rather than guess which
row was meant, exactly as `AI_CONSUMER_CONTRACT.md` rule 4 requires for any
other resolver category. No resolver in this layer ever fabricates a number
that isn't present verbatim in the source JSON.

## 4. Demotion / verification rules

- **`DECAYED`** (from `claim_survival.json`'s `verdict_counts` /
  `decayed_cards`) means: stop trusting that card's original claim. Present
  it as decayed, do not repeat its original verdict as current.
- **`DISCREPANT`** (from `sentinel_report.json`'s `checks[].verdict`) means:
  the served value and the independently recomputed value disagree beyond
  tolerance. Do not display the served stat as-is -- report the discrepancy
  itself (`served_value` vs `recomputed_value` vs `delta`), or refuse.
- **`STALE`** means the sentinel could not re-derive the value fresh enough
  to compare; treat as unverified, not as confirmed.
- **`UNCHECKABLE`** means no independent re-derivation exists for that stat;
  say so rather than implying it passed verification.
- A **conflict row** in `contradiction_report.json` means two claims in the
  same family disagree; cite both sides, do not silently pick one.

## 5. Hard invariants

- **No edge claims.** Nothing in this layer, and nothing said about it, may
  assert a dollar edge, ROI, or beating-the-market result. See
  `.claude/rules/no-edge-claims.md` for the exact retracted-number
  do-not-print list.
- **Append-only ledgers.** Producers append; they never rewrite history in
  place.
- **Never mutate the claims stores.** The analytics-verification layer reads
  and re-derives; demotions/discrepancies it finds are proposals for a human
  or the autoloop to act on, not in-place edits to the underlying claims
  engine files.
- **Per-file tests only.** `python -m pytest tests/platformkit/analytics_verify/test_answers.py -q`
  -- never the full suite (it freezes the box, see
  `.claude/rules/bash-cwd-prefix.md`).
- **Never fabricate a number.** Every field in a resolver's `ok` response
  traces to a literal key in the source JSON artifact.
