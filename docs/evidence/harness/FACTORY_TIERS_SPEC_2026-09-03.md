# FACTORY TIERS SPEC -- frozen cost tiers + promotion rule (2026-09-03)

Versioned, TRACKED prereg for `scripts/platformkit/foundry/tiers.py`. It lives under
`docs/evidence/harness/` and NOT under `docs/research/` because `docs/research/*` is gitignored
(`.gitignore:476`), so a commit-timestamp proof is impossible there (REDTEAM SF-3).

This file is committed BEFORE the module it governs. It is pinned by content, not by a clock:
`PromotionRule.from_spec` computes this file's git blob id (identical to `git hash-object <path>`)
and every `TierResult` and every charged ledger row carries it as `prereg_sha256` (SF-4).
Editing this file changes the blob id and every stored row then fails the equality check.

Calibration language only. A SCREEN is never a finding. REJECT / BEHIND / SINGLE-WINDOW are successes.

## Frozen parameters (parsed by `PromotionRule.from_spec`)

    spec_version: v1
    top_n: 20
    group_by: family,iso_week
    rank_by: t1_brier_improvement
    partition_seed: 20260903
    alpha: 0.05

`top_n` is FROZEN HERE and is NEVER a function argument. `promote(t1_results, rule)` reads it off
the rule object only; a caller cannot pass a different width without editing this file, which
changes `prereg_sha256`.

## The four tiers

| tier | question | exact existing call | charged | reportable |
|---|---|---|---|---|
| T0 | does the corpus exist, cover, and pass vintage | `corpus_cache.load_gate_corpus(sport)` (raises `StaleCorpusError`) + `walkforward.assert_vintage` on an EVENLY SPACED 100-row sample + non-null features `>= 0.8 * rows` | no | NEVER |
| T1 | does it move Brier on one corpus | `walkforward.walk_forward` + `scoring.brier(p_model, y)` vs `scoring.brier(p_close, y)` | no | NEVER -- verdict is `SCREEN`, a NON-FINDING |
| T2 | is it real after purging and selection | `cpcv_engine.cpcv_evaluate` + `pbo.cscv_pbo(matrix, y, s_blocks=16)` + `dm_test.diebold_mariano` + `deflated_metrics.deflated_p(p, k)`, k read from `_charge_ledger` AT LAUNCH | YES | MATCH / BEHIND / AHEAD |
| T3 | does it replicate | the T2 call on a second corpus or `corpus_unit`; floor from `fwer_budget.min_corpora_eff(n_corpora, k)` | YES | AHEAD only if the floor is met, else SINGLE-WINDOW |

THE REFUSAL: `charge_tier` raises `TierNotChargeable` for T0 and T1. There is no other path to the
FWER ledger from this module, so a cheap screen cannot consume K and cannot reach the results DB as
anything but `verdict="SCREEN"`.

## Verdict rule (frozen)

Let `d = brier_model - brier_close` and `p = deflated_p(raw_p, k_global)` at the K read at launch.

    p >= alpha            -> MATCH            (indistinguishable from the reference close)
    p <  alpha and d > 0  -> BEHIND
    p <  alpha and d < 0  -> AHEAD            (T2)
    T3: AHEAD is downgraded to SINGLE-WINDOW unless n_corpora >= min_corpora_eff(n_corpora, k_global)

No bar in this table may be lowered. A bar found unmeetable is reported CLOSED AT LIMIT (Q3).

## SF-1 screen/verdict partition

Every family fixes ONE partition of its corpus before any tier runs. Basis: `corpus_unit` when the
corpus carries at least two distinct units, else ISO-week blocks of `state_ts`. Blocks are sorted
and assigned by `(rank + partition_seed) % 2`, which is deterministic, seeded, and balanced by
construction. Both sides' sha256 (over the sorted `event_id` list) are fields on every `TierResult`.

    T0, T1  read the SCREEN side only.
    T2, T3  read the VERDICT side only.

A T2 or T3 run whose rows intersect its family's SCREEN partition is an automatic self-REJECT:
`run_tier` raises `ScreenPartitionLeak` and nothing is charged. Purging inside one evaluation cannot
undo a hypothesis that was CHOSEN on the rows being scored.

SF-11 caveat, stated not fixed: NBA and MLB and tennis each have 2 `corpus_unit`s, so a corpus_unit
partition leaves T3 with no independent unit. Partition those by ISO-week block and expect
SINGLE-WINDOW in the register row. The replication floor is never lowered to buy an AHEAD.

## SF-2 screen width priced

Every T2 and T3 artifact prints `screened_n` -- the number of hypotheses screened in that family in
that ISO week -- beside `deflated_p`. `run_tier` REFUSES a T2/T3 call with `screened_n=None`.
`screened_n` is recorded per family per ISO week in the run artifact, not here; this file only fixes
that it must be recorded and printed. NOT DONE in v1: `screened_n` is printed, it does not yet
enter K (SF-2's charge-the-screen fix is a separate row).

## SF-10 cluster keys (DM clustering)

`event_id` clustering is a NO-OP on the pregame corpora (one row per event). Declared keys:

| sport | key | state field read | ICC on the base squared-error loss |
|---|---|---|---|
| nba | team | `away`, else `home` | 0.0238 |
| mlb | team | `away`, else `home` | 0.0022 |
| soccer | div | `div` | 0.0004 |
| tennis | player | `p1_id`, else `home` | 0.0041 |

The key name is a `TierResult` field. ICCs are one-way and are a LOWER bound on the correction
(team is a crossed factor); `n_eff = n / (1 + ICC * (mbar - 1))`.

## Must not move

`deflated_p`, `min_corpora_eff`, `cscv_pbo(s_blocks=16)`, every threshold under
`scripts/platformkit/eval_gate/`, `data/registry/**` (never written), and
`data/cache/eval_gate/backtest_fwer.jsonl` (the tiers test writes a TMP ledger ONLY).
