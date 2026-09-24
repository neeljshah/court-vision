# S423 NBA pregame intelligence prior preregistration -- DRAFT, UNSEALED 2026-09-23

Document only. This draft freezes nothing and authorizes no scoring, fitting or ledger
charge. The orchestrator alone seals it. Binding spec: docs/evidence/tracking/specs/S423_spec.md.
Instrument: scripts/platformkit/ingame/intel_prior_arm.py (on intel_prior_join.py and
intel_prior_snapshot.py). Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, Q1-Q6.
S423 never enters E2: the S382 draft admits only the three state features.

## Preregistration text (verbatim from the spec)

Arms A, B, B_lag, C, C_intel and C_intx, all ridge logistic, fitted on past games only.
PRIMARY cell: C_intel minus B, Brier, period-first (Q1..Q4 and OT per phase()), whole-game
bootstrap with seed 13, on the prior-eligible subset. SECOND cell: C_intx minus B, Brier,
phase Q4 only (the interaction: a strong team behind late). Standing controls: C_intel minus
B_lag and C_intx minus B_lag on the B_lag subset; a below-zero primary not also below zero
against B_lag is LAG-ABSORBED. Descriptive: C_intel minus C (the prior's increment), logloss
beside every Brier cell. Floors: >= 30 scored games per cell or UNDERPOWERED; exclusions
counted per refusal; no imputation. Corpora: r1 is touched (S392) and reconstructed, so any r1
result is SINGLE-WINDOW at best; the 2026-27 forward corpus with LIVE receipt snapshots is the
only route to a second corpus and to AHEAD. Charge: one FWER-ledger row at launch, reading K at
launch, AFTER the sealed E2 trial has run, inside the family's K budget. EXPECTED: NULL on the
primary (the venue already prices team strength); weak-to-NULL on the Q4 interaction cell, the
only place a venue lag could show. A NULL is a completed result and closes the row.

## Scored periods (sealer-visible; FIX 1b, AMENDMENT 2 (e))

The landed period machinery scores Q1-Q4 only (scripts/platformkit/ingame/
baseline_four_arm_period.py:9, PERIODS = Q1..Q4). The text above says 'Q1..Q4 and OT per
phase()'; phase() does emit 'OT', but OT ticks are counted (n_ot) and NOT scored by the landed
machinery. Scoring OT would need a landed change (a NEXT-ROW item). As built, the primary cell
is Q1-Q4, and the second cell and its B_lag control are Q4. This statement is unsealed; the
sealer decides.

## Declared blocks (frozen before any read)

- INTEL_PRIOR_NBA = ('prior_net_diff', 'prior_pace_mean'); prior_net_diff = (home off_rtg_mean
  - home def_rtg_mean) - (away off_rtg_mean - away def_rtg_mean); prior_pace_mean = mean of the
  two teams' pace_mean.
- INTEL_PRIOR_NBA_X adds 'prior_x_score' = prior_net_diff * score_diff and 'prior_x_score_late'
  = prior_x_score * (quarter >= 4).
- C_intel names: ['mid', 'score_diff', 'quarter', 'seconds_remaining', 'prior_net_diff',
  'prior_pace_mean']; C_intx names: C_intel names plus the two interaction names.
- Snapshot: team_advanced_stats rows with game_date STRICTLY BEFORE the league-local
  (America/New_York) date of as_of, same season, last N = 10 games per team, fewer than 5
  refuses prior_thin, none refuses prior_absent. The tip-off instant is the attested ESPN
  summary's header.competitions[0].date (parsed through parse_venue_time); as_of = 00:00
  America/New_York on that instant's LOCAL date, rendered as the UTC instant it is (04:00Z or
  05:00Z); as_of must be strictly before tip-off (as_of_not_before_tipoff otherwise). The
  checkpoint game_date is a cross-check only (checkpoint_date_disagrees).
- Alias table (frozen): WSH -> WAS, PHO -> PHX. Home side attested by the cached ESPN summary;
  slug order is a cross-check only (slug_order_disagrees).

## Builder notes for the sealer (not preregistration text)

- The C_intx control against B_lag is computed on phase Q4 to pair with the SECOND cell; the
  C_intel control uses the primary's Q1..Q4. The sealer may change either before sealing.
- LAG-ABSORBED is computed as: the Brier cell's verdict is SINGLE-WINDOW (interval wholly
  below zero) and the matching B_lag control's verdict is not SINGLE-WINDOW.
- Every r1 prior is RECONSTRUCTED (asof_kind = reconstructed): the source carries no receipt
  timestamp and later stat revisions are not excluded. It is never receipt-causal.
