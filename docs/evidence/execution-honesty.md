# Paper-Execution Discipline -- I built a full execution layer with no path to a real order

> A complete paper-trading execution stack -- entry-timing study, order-lifecycle state
> machine, settlement join, and a paper ledger -- with a *deliberate* boundary: no code path
> reaches a real order or a real dollar. The single truth-source for any figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) section G. Paper-only; no edge,
> ROI, or dollar result is claimed anywhere, per the repo's no-edge rail.

---

## The claim

The execution layer is fully built and tested, and there is intentionally **no code path**
from it to a live order -- not an unfinished feature, the design. And where the layer cannot
honestly measure a number, its own audit **publishes the null**: realized CLV is unmeasurable
here because no independent closing-price feed was captured, so the artifact records
`realized_clv_pct: null` and says why. The hire signal is a person who builds execution plumbing to the last mile,
refuses to let it trade until a human wires that mile, and whose audit reports what it does
not know rather than dressing a gap as a result.

---

## The discipline mechanics

**Entry timing is efficient, and the policy encodes that.** The entry-timing study
(`scripts/platformkit/execution/entry_timing/`) tested whether entering a paper position
earlier than the closing tick captures value, on real drift-event data across NBA/MLB
moneyline, spread, and total (900-1,645 drift events per market). No pre-close horizon shows
an information edge over the contemporaneous price, so the policy is
`last_pregame_tick` on every market -- the market is efficient on *entry timing*, not just
price level.

**The order lifecycle cannot place a real order.** `executor/lifecycle.py` is a full
submit -> ack -> fill -> cancel/replace -> settle state machine, and its module header states
the boundary: *"DOUBLE-GATED LIVE PATH -- no
real order is placeable from this module."* Gate (a) is an env flag that intentionally does
not exist anywhere in the repo and is never created by an agent; gate (b) is an explicit
per-run `live=True` argument. Both are absent by default, and even with both present,
`resolve_exchange()` hard-refuses with `NotImplementedError` -- the live HTTP client is
deliberately unwired, and wiring it is a human go-live step. Every test uses
`MockKalshiExchange`: the plumbing is proven, the trigger removed.

**Settlement truth is hardened, forward-only.** Three integrity gaps in the paper ledger were
root-caused and fixed without rewriting settled history. (1) A third props settle path never
stamped `close_source` on 96/96 recent rows -- forward-fixed (`c1417777`). (2) The dedup
wrappers checked-then-appended *outside* the lock -- a TOCTOU race -- closed with a shared
`ledger_lock()` + `append_row_if_new`, proven by a race test that spawns two real OS
subprocesses racing the same ledger (`099476ac`,
`scripts/platformkit/test_clv_ledger_io.py`). (3) A forward-only snapshot-then-diff score-drift
audit found 76/436 settled MLB rows drifting from the resolver read; those rows are
quarantine-flagged, not silently re-settled (`0d01a0e7`).

**The audit publishes its own nulls.** `paper_execution_audit.json` reports execution-quality
analytics only: 83 logged paper bets, **all `executed=False`** (zero real fills),
`edge_claimed=false`, units in probability points -- not dollars. Of the 37 settled rows,
`realized_clv_pct` is null for **all 37**, the reason recorded (no independent close feed).
The one quantity the ledger *can* speak to -- placement-time divergence between the model's
number and the taken price -- is labeled as what it is: a pre-trade sizing input, not
realized CLV.

---

## Receipts -- each discipline traced to the artifact that proves it

| Discipline | What it enforces | Proof artifact | Honest result |
|---|---|---|---|
| Entry-timing study | No pre-close horizon beats the contemporaneous price | `scripts/platformkit/execution/entry_timing/` (900-1,645 drift events/market, NBA/MLB ML/spread/total); policy `last_pregame_tick` in `data/frontend/ops/timing_policy.json` (gitignored) | "Efficient on entry timing; enter at the close" |
| Double-gated executor | No real order is placeable from the module | `executor/lifecycle.py` header + `mock_exchange.py`, `dryrun.py`, `test_lifecycle.py`; env-flag gate + `live=True` gate + `resolve_exchange()` `NotImplementedError` backstop | "Plumbing proven end-to-end; trigger deliberately removed" |
| TOCTOU write race closed | Concurrent settle can't double-write or lose a row | `099476ac`; `test_clv_ledger_io.py` (two real OS subprocesses racing the same ledger) | "Race closed and proven, not just asserted" |
| `close_source` write-path bypass | Every settled row must stamp its close source | `c1417777` (96/96 recent props rows forward-fixed) | "Silent bypass caught; historical rows left honest, not rewritten" |
| Score-drift audit | Post-settlement drift is flagged, not re-settled | `0d01a0e7` (76/436 settled MLB rows quarantine-flagged) | "Drift surfaced and quarantined; settled history preserved" |
| Self-published nulls | Unmeasurable metrics are recorded as null | `paper_execution_audit.json` (83 rows, 0 fills, `edge_claimed=false`; `realized_clv_pct` null for all 37 settled) | "No close feed = no CLV; the audit says so instead of fabricating" |

---

## Reproduce on a fresh clone

These two tests are hermetic (mock exchange + temp ledger) and run on a bare clone:

```
# Proves the executor has no live path (every test uses MockKalshiExchange)
python -m pytest scripts/platformkit/execution/executor/test_lifecycle.py -q

# Proves the settle race is actually closed (two real OS subprocesses)
python -m pytest scripts/platformkit/test_clv_ledger_io.py -q
```

The audit artifact (`scripts/platformkit/analytics_showcase/out/paper_execution_audit.{json,md}`)
ships committed. Regenerating it, or recomputing the entry-timing policy, reads corpora under
`data/` (gitignored) -- so on a fresh clone the committed artifact is the source of record and
the recompute degrades honestly rather than fabricating:

```
# Regenerate the paper-execution audit from the rescued ledger (needs data/)
python -m scripts.platformkit.analytics_showcase.paper_execution_audit

# Recompute the entry-timing policy, writing nothing (needs the drift corpus under data/)
python -m scripts.platformkit.execution.entry_timing.cli --sport all --market all --dry-run
```

---

## Why this matters to a trading desk

On a desk, the dangerous engineer ships an execution path that *can* fire before its controls
are proven. The discipline here is the opposite: a complete, tested lifecycle with the live
trigger absent behind two gates and a hard-refuse backstop; settlement integrity fixed
forward-only with a real concurrency test, not a hopeful comment; and an audit that prints
`null` and `edge_claimed=false` where the honest answer is "not measurable yet." No-edge
discipline is not a shortfall -- it is the feature. I build execution systems to institutional
completeness and keep the safety on until a human decides.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
