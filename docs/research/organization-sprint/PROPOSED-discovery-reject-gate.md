# PROPOSED (human-gated) -- wire the reject ledger into the discovery loop

Status: SKIP-half SUPERSEDED / staleness-revisit OPT-IN only (resolved 2026-06-17).

RESOLUTION after reading the real code: the discovery loop ALREADY has institutional
memory + a skip mechanism. `orchestrator.py:315-327` loads `seen_families` via
`load_discovered_families()`, passes them to `discover(... seen_families=...)` so
`enumerate_specs` skips already-tried FAMILIES, and `record_discovered()` persists every
verdict to `_DISCOVERED_LEDGER` (`.planning/loop/discovered_signals.jsonl`). The
`skip_names` edit below is therefore REDUNDANT and was NOT applied.

Built instead (autonomous-safe, no gated edit; shipped + 8 tests green):
`scripts/platformkit/reject_ledger.ingest_discovered_ledger()` -- a BRIDGE that folds the
loop's existing REJECTs into the cross-sport graveyard. Ran live 2026-06-17: folded 10
real NBA rejects, so `signal-audit` + humans + the mlb/soccer/tennis proof streams now
see the NBA discovery rejects in one place.

The ONLY behavior the gated diff below ADDS that the loop lacks is STALENESS-REVISIT:
`seen_families` skips a tried family PERMANENTLY; `is_known_reject(stale_after_days=...)`
would let it be re-rolled once the corpus has grown past the window. Apply the diff below
ONLY if you want that (it costs extra gate compute re-testing old families).

## Design constraint
`discover_from_matrix()` is documented **Pure: no I/O** -- keep it that way. So:
- CONSUME side (skip known rejects) = a pure input `set`, passed in. No I/O added.
- PRODUCE side (persist verdicts) = lives in the I/O caller (`discover()` / orchestrator).

## Diff 1 -- `src/loop/discovery.py` (pure: add an optional skip-set)

```python
 def discover_from_matrix(base: np.ndarray, target: np.ndarray, fc: List[str], dates: List[str],
                          target_name: str, *, top_k: int = 12, device: str = "auto",
-                         seen_families: Optional[set] = None) -> List[DiscoveryResult]:
+                         seen_families: Optional[set] = None,
+                         skip_names: Optional[set] = None) -> List[DiscoveryResult]:
     """Enumerate -> cheap-screen -> run the honest gate on the top-K candidates for one target.

     Returns a DiscoveryResult per gated candidate (verdict in ``.gate.verdict``). Pure: no I/O.
+    ``skip_names`` (optional) is a pre-built set of candidate names already known-rejected;
+    they are skipped BEFORE the expensive gate. Purity preserved: the set is an input.
     """
     cols = {c: base[:, i] for i, c in enumerate(fc)}
     specs = enumerate_specs(fc, base, target, seen_families=seen_families)
     scored: List[Tuple[TransformSpec, float, np.ndarray]] = []
     for s in specs:
+        if skip_names and s.name() in skip_names:
+            continue                                   # known-dead -> don't pay for the gate
         try:
             cand = _apply(s, cols)
         except Exception:
             continue
```

## Diff 2 -- the I/O caller (`discover()` wrapper ~L244, or `src/loop/orchestrator.py`)

```python
from scripts.platformkit import reject_ledger as RL

SPORT = "nba"   # discovery currently runs on the NBA pergame matrix
STALE_AFTER_DAYS = 120

# CONSUME: build the skip-set once from the graveyard (a corpus grown past the
# freshness window makes a reject revisitable, so stale rejects are NOT skipped).
def _skip_names() -> set:
    return {r["signal"] for r in RL.graveyard(SPORT, source="signal_proof")
            if RL.is_known_reject(SPORT, r["signal"], stale_after_days=STALE_AFTER_DAYS)}

# ...inside discover(), pass it through:
results = discover_from_matrix(base, target, fc, dates, target_name,
                               top_k=top_k, device=device, skip_names=_skip_names())

# PRODUCE: persist every gated verdict so next run's skip-set is richer.
RL.record_proof_verdicts(SPORT, [
    {"signal": r.spec.name(), "actual": r.gate.verdict.value, "reason": r.gate.reason,
     "p_value": getattr(r.gate, "p_value", None),
     "wf_all_improve": getattr(r.gate, "wf_all_improve", None),
     "ablation_delta": getattr(r.gate, "ablation_delta", None)}
    for r in results
], corpus="data/domains/basketball_nba")
```

## Why this is honest + safe
- The gate stays the SOLE decider; the ledger only avoids re-paying for verdicts already
  rendered. A stale reject is revisited (corpus may have grown) -- remembers, not forbids.
- No `data/registry/` write, no flag flip, no $ claim. Ledger lives in gitignored
  `data/frontend/`. A REJECT is market-efficiency evidence, not a failure.
- LOC delta is tiny and additive; `discover_from_matrix` stays pure.
