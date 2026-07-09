# `scripts/platformkit/` — the platform toolkit

`scripts/platformkit/` is a large collection of CLIs and libraries that sits alongside the
sport-blind `kernel/` (see [../kernel/README.md](../kernel/README.md)) and the per-sport
`domains/<sport>/` adapters. Where `kernel/` is (mostly still-reserved) shared *machinery*,
`platformkit` is where that machinery's actual working implementations, gates, ledgers, and
proof harnesses live *today* — much of what `../PLATFORM.md`'s target-state diagram attributes to
`kernel/` is, as of this writing, implemented here instead (cross-referenced in
[../kernel/README.md](../kernel/README.md)).

This page is an orientation map. Every subsystem below was verified by reading the actual code.

---

## The seam contract (documented in depth elsewhere)

Five top-level files implement the three-seam contract a new sport's adapter must satisfy — the
full narrative is in [../PLATFORM.md](../PLATFORM.md); here's the one-line summary of each:

| File | Role |
|---|---|
| `feature_spec_core.py` | `FeatureSpec` / `FeatureField` / `build_base_matrix()` — the frozen train==inference feature contract every domain's `feature_spec.py` implements |
| `ingest_manifest_core.py` | `IngestManifest` + the 4 leak-class constants (`LEAK_PRE_GAME` / `LEAK_IN_GAME` / `LEAK_POST_GAME` / `LEAK_REFERENCE`) + freshness SLA |
| `parity_matrix.py` | The fail-closed green/red grid over `SPORTS x {census, manifest, feature_spec}`; CLI exit 2 on any red cell |
| `new_sport_scaffold.py` | Codegen that stamps the three seam stubs for a new sport (the 9-step playbook) |
| `check_import_contract.py` | AST-only kernel-purity + cross-adapter-import-ban guard |

---

## Major subsystems

Grouped by what they do (each verified against real code):

| Area | Subdirectory / files | One-line purpose |
|---|---|---|
| Cost / economics | `econ/`, `cost_ledger.py` | Per-venue transaction-cost model (fees as probability thresholds) + after-cost scoreboards |
| Edge greenlight gate | `econ/edge_greenlight.py`, `greenlight_criteria.py`, `greenlight_trust_honesty.py` | Read-only nightly report; a channel is GREEN only if 7 pre-registered criteria pass on both halves of a date-parity split. A GREEN pages a human — it never places a bet or flips a flag |
| Paper grading | `grade_paper*.py`, `paper/` | Settles paper bets, resolves closing lines with an honest fallback ladder, computes units-only scoreboards |
| CLV ledger | `clv_ledger.py` + ~15 `clv_ledger_*.py` | Append-only, status-keyed dedup, fail-closed honesty checks, units-only write rail |
| Venue history | `venue_history/` | Historical Kalshi/Polymarket price-series backfill + coverage census |
| Atlas / intelligence | `atlas/` | Builds the Obsidian-vault intelligence artifacts (person-free by default) |
| Autoloop | `autoloop/` | The self-improving loop's zero-LLM cycle scheduler |
| Eval gate | `eval_gate/` | The offline, <60s golden-fixture ship/reject harness every change is judged against (walk-forward, DM-test) |
| Answers / intel query | `answers/`, `intel_query/` | Natural-language query surface; dispatches by question type, answers only from independently-VERIFIED claims, REFUSES edge-language questions |
| Proof modules | `proof_common/`, `proof_<sport>/` | Sport-blind V1-V4 leak-free OOS proof harness + per-sport leaf callables |
| Execution | `execution/` | Order-book replay / fill-quality measurement — **no order path exists**; paper-only |
| Predict matchup CLI | `predict_matchup.py` | The one buyer-facing CLI: pregame + in-game JSON for any sport in one call |
| Health monitors | `sla/`, `selfheal/`, `ops_sentinel/` | Advisory-only; none has restart or money authority |
| Retention | `retention/` | Verified consolidation of daily archives into monthly parquet (never deletes without a row-count + hash check) |
| Signal candidates | `weights/`, `l4/`, `combo/`, `market_coverage/` | Pre-registered, gated signal-discovery experiments — proposal only, never auto-promoted |
| Prediction-market trading | `pm_trading/` | Kalshi/Polymarket paper-trading policy + sizing + a conservative advisory (never self-authorizing) real-money gate |
| Quant | `quant/`, `quant_exec/` | Thin, audited wrappers around already-vetted CLV/sizing/devig primitives — no new math |

---

## How to run the headline CLIs

```bash
# One matchup, pregame + in-game, any sport
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL --elapsed 0 --home-score 0 --away-score 0

# Reproduce the leak-free scoreboards on committed fixtures (<60s, fresh clone)
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
python -m scripts.platformkit.ingame_scoreboard        --corpus tests/fixtures/proof

# The fail-closed cross-sport parity grid
python -m scripts.platformkit.parity_matrix

# The nightly edge-greenlight report (read-only; a GREEN verdict pages a human, never places a bet)
python -m scripts.platformkit.econ.edge_greenlight

# Ask a natural-language question, answered only from VERIFIED claims
python -m scripts.platformkit.intel_query.ask "what kind of shooter is Stephen Curry"
```

---

*See [../PLATFORM.md](../PLATFORM.md) for the seam contract these tools implement. See
[../architecture/system-overview.md](../architecture/system-overview.md) for where platformkit
fits into the whole funnel.*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
