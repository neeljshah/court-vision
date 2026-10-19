# PROPOSED (not applied) -- S447 STEP 2: an MLB surface for repricer_router + live_loop wiring

STATUS: PROPOSED DIFF ONLY. Nothing in this file has been applied to any human-gated path
(`scripts/platformkit/ingame/repricer_router.py`, `scripts/platformkit/ingame/live_loop.py`) or
to `domains/mlb/predictor.py`. STEP 1 (this row, S447) is a REPORT ONLY measurement of
predict_live vs the served pregame carry; this document is the STEP-2 sketch a human should
review before any of it is applied. It is gated on STEP 1's forward-cell result: wiring a live
MLB surface ahead of a scored AHEAD verdict would serve an unvalidated number.

## Before-condition this proposal responds to

- `repricer_router.py:34,52` looks for `scripts/platformkit/ingame/surfaces/<sport>.json`;
  `ls scripts/platformkit/ingame/surfaces/` today = `nba.json` only.
- `live_loop.py:237-243`: `rr.reprice("mlb", ...)` returns `available: False` (no surface), so
  every MLB live tick falls through to `_pregame_carry` -- the constant pregame prior, never
  `predict_live`.

## Proposed new file: `scripts/platformkit/ingame/surfaces/mlb.json`

A hand-seeded surface mirroring `nba.json`'s shape (`sport`, `version`, the same boolean
no-claim flag `nba.json` itself carries -- set false here too, since nothing in this sketch is
a validated calibration result -- a freshness grid keyed on innings-elapsed fraction instead of
`regulation_min`/`fraction_elapsed` in minutes), carrying an explicit `"_honest_note"` stating
the weights are unvalidated priors pending S447's forward-cell result, exactly like `nba.json`'s
own note. NOT created by this row; sketch only, so a human reviews the grid shape before any
file lands in a routed surfaces/ directory.

## Proposed router change (repricer_router.py) -- SKETCH, NOT APPLIED

`reprice("mlb", ...)` would need an MLB branch that:
1. loads `surfaces/mlb.json` via the existing `load_surface()` (no change needed there --
   it is already sport-generic);
2. calls `domains.mlb.predictor.MLBPredictor.predict_live(...)` (built from an as-of Elo, per
   S447's `build_predict_live_fn`) instead of the NBA-only `get_repricer` path currently
   composed in this module;
3. blends the live `predict_live` output with the pregame prior through
   `scripts.platformkit.ingame.blend_apply.apply_surface`, exactly as the NBA branch does today
   -- reusing that function unedited, not reimplementing the freshness blend for MLB.
This is a few added lines inside `reprice()`'s existing sport-dispatch, not a rewrite; the
NBA branch is untouched.

## Proposed live_loop.py change -- SKETCH, NOT APPLIED

None needed structurally: `_process_game` already calls `rr.reprice(sport, gs, prior)` and only
falls back to `_pregame_carry` when `available` is False. Once the router change above makes
`reprice("mlb", ...)` return `available: True`, MLB tickets automatically stop falling through --
no edit to `live_loop.py` itself is proposed.

## Gate before applying

Do not apply until S447's forward cell (this memo's sibling,
`docs/evidence/harness/S447_mlb_live_vs_carry_2026-09-24.md`) reports AHEAD with >= 30 forward
games (Q5: a second corpus is still required before any claim leaves SINGLE-WINDOW status). As
of 2026-09-24 that cell is INSUFFICIENT (zero forward games) -- this proposal is not actionable
yet and is recorded here only so the eventual wiring is a small, reviewed diff instead of a
scramble.

## Note (FIX 1c, AMENDMENT 2 item d)

This is the tracked twin of the gitignored `docs/research/organization-sprint/
PROPOSED_S447_mlb_surface.md` (docs/research/** is local-only per this repo's rules). Both
copies carry identical Q6-clean prose (the sketch is a candidate freshness-grid design, not a
proven result); this copy exists so a Q6-vocabulary scan and `contract_preflight` can see it as
a tracked, landable candidate file.
