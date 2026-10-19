# S764 PROPOSED prereg (quote-parameter grid), UNSEALED

PAPER ONLY. The block below is the draft payload; sealing = a dated .json copy committed ALONE before the first qualified night it applies to (the harness .gitignore keeps loose .json files out, so the sealed copy goes under docs/evidence/forward/exec_policy/ like PREREG_S551.json).

```json
{
  "row": "S764",
  "status": "PROPOSED - NOT SEALED. Sealing = a dated copy committed ALONE (commit A) before the first qualified night it applies to; never edited after.",
  "scope": "PAPER ONLY. Report-only replay of declared quote parameters side by side on the SAME qualified tape. Execution-quality measures only; no live parameter changes without a new dated seal.",
  "population": "games whose qualification receipt verdict is PASS (families_maker_forward.json, S390 gates), first hour after scheduled start, every sport its own stratum (never pooled)",
  "engine": "scripts/platformkit/execution/core/paper_exec_model.py + queue_model.py + latency.py (S693), venue_rules.py; the code identity is hashed into the sealed copy",
  "fixed": {"submit_latency_s": "6.0", "cancel_latency_s": "6.0", "qty": 1, "cooldown_s": "30.0", "stale_s": "60.0", "queue_scenario_primary": "displayed_depletion", "fee_schedule_version": "venue_fees:kalshi-maker:2026-09-01:0.0175"},
  "cells": [
    {"id": "ttl30_book", "ttl_s": "30", "cancel_trigger": "book_move"},
    {"id": "ttl60_book", "ttl_s": "60", "cancel_trigger": "book_move"},
    {"id": "ttl120_book", "ttl_s": "120", "cancel_trigger": "book_move"},
    {"id": "ttl30_state", "ttl_s": "30", "cancel_trigger": "state_receipt"},
    {"id": "ttl60_state", "ttl_s": "60", "cancel_trigger": "state_receipt"},
    {"id": "ttl120_state", "ttl_s": "120", "cancel_trigger": "state_receipt"}
  ],
  "reference_cell": "ttl60_book (the S551 parameter set)",
  "primary_measure": "fee-inclusive 60 s markout per filled contract, in cents, game-cluster mean of per-game means; a mark missing at 60 s is unavailable, never zero; more than 20 pct missing in a cell = MARKS_INCOMPLETE",
  "reported_beside": ["fill share (filled / quoted orders)", "partial-fill share", "5 s, 30 s and 300 s markouts", "through_only queue scenario", "unknown-depth quote count"],
  "floor": {"paired_qualified_games_per_cell": 30, "clusters": "game"},
  "estimator": {"bootstrap": "game cluster", "draws": 5000, "seed": 764, "interval": "90 pct, sorted draws [250] and [4749]"},
  "multiplicity": {"method": "holm", "family": 5, "alpha_one_sided": 0.05, "comparisons": "each non-reference cell minus the reference cell"},
  "stopping_rule": "exactly one confirmatory look: the first receipt at which every non-reference cell has >= 30 paired qualified games; every later receipt is DESCRIPTIVE; no cell is added, dropped or chosen after any result is read",
  "verdict_vocabulary": ["AHEAD", "BEHIND", "UNDERPOWERED", "INSUFFICIENT"],
  "runner": "paper-desk-morning task, once per week, after the first qualified game; RAM < 400 MB; never inside a focus hour",
  "first_eligible_date_rule": "UTC date of the seal commit's committer instant + 1 day"
}
```
