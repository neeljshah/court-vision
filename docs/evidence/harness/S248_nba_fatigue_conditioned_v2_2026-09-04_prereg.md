# S248 preregistration - NBA fatigue conditioned forms v2

Row: `docs/evidence/tracking/specs/S248_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q1-Q9.

## Fixed inputs and gate

The only inputs are `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv`
and `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_rated.csv`.  The ALL
archive is the scored corpus: 79,554 ticks, 661 game clusters, 194 date folds
(191 scored), with dates 2024-10-25 through 2026-04-06.  The RATED archive is
used only for the required S92 reproduction and row-count check.

Before any candidate probability is calculated, the archived S92 differentials
will be recomputed without refitting.  The required ALL improvements against
`loss_incumbent` are fatigue_min -0.000212, fatigue_share -0.000098, and
unit_onoff -0.000397, each within 1e-9; their clustered DM results and the
archived Brier order will also be remeasured.  A failure is CLOSED AT LIMIT.

## Fixed candidate forms and evaluator

The one new module will be
`scripts/platformkit/eval_gate/s248_fatigue_conditioned_v2.py`.  It will use
`scripts.platformkit.eval_gate.walkforward.walk_forward` with strict
redaction.  Every row for a date shares that date's timestamp; every game uses
one common synthetic home identifier and its game id as the synthetic away
identifier.  Therefore the evaluator's 48-hour same-team purge implements the
S92 one-day nonzero embargo, while the unique away ids prevent any extra
matchup purge.  The callback receives only the evaluator's purged training
states and its redacted test state, fits only on that training state, and
returns every candidate probability.

Each candidate is a one-parameter additive logit adjustment to the archived
incumbent probability: `sigmoid(logit(p_incumbent) + beta * x)`, where beta is
fit separately inside each evaluator training fold by Brier minimization.  The
three fixed x values are:

1. `fatigue_min * period`.
2. `fatigue_min * (2880.0 - elapsed)`.
3. `fatigue_min * absolute_margin`, with absolute_margin taken only from an
   archived CSV column named `absolute_margin` or `margin_s` (absolute value).

No candidate will be substituted, dropped, tuned, or renamed after the
archive schema check.  If the third required archived column is absent, all
candidate scoring stops and the memo will identify that exact unavailable
column rather than manufacture a proxy.  The S92 archive bytes, S92 verdicts,
and the fixed +0.004 calibration-improvement bar must not change.  This is a
single-window screen, not an AHEAD claim.  No ledger or register is read or
written.

## Fixed scoring and artifacts

For each form, the module will report tick-weighted Brier improvement versus
the archived incumbent, game-clustered DM p-value and 95 percent interval, and
effective sample size.  It will write a committed per-tick CSV under
`docs/evidence/` containing cluster id, timestamp, archived incumbent loss,
candidate loss, and paired differential, so the result is reconstructible from
the artifact alone.  The memo will name this preregistration path and seal.
The verdict is DRAFT only if improvement is at least +0.004 and its clustered
interval excludes zero; otherwise it is SCREEN_NULL.

SEAL: ad49226dfc829e90c37cf37ccb7940835a8055ac8216cfc3031c10a0254948bb
