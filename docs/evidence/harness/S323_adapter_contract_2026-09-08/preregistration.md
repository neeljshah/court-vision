# S323 adapter-contract preregistration

Date: 2026-09-08
Spec: docs/evidence/tracking/specs/S323_spec.md
Verifier: docs/evidence/tracking/VERIFIER_CONTRACT.md, sections B and Q

## Fixed contract fields

Identity: sport, league, rule_version, game_id, home_team_id, away_team_id, season, corpus, venue.
Target: target_id, line, class_order, settlement_rule, void_rule.
Event: event_id, sequence, event_time, received_at, feature_available_at, prediction_at.
State: state, score_home, score_away, status, unknown_flags, provenance.
Market: m0_source, m0_time, m0_probabilities, ml_source, ml_time, ml_probabilities.
Prediction: candidate_probabilities, null_probabilities, outcome, outcome_known_at, state_key.
Evaluation: exclusions, weight, fold_id, input_hash, code_hash, seal_hash.

## Fixed invariant rules

Labels are a separate frame from features. Grain is one oriented target per venue per tick; paired sides are merged; games are whole-game groups. Each adapter declares a nonnegative maximum_feed_delay_seconds for embargo construction. Required times satisfy received_at <= feature_available_at <= prediction_at < outcome_known_at. State keys are unique within a fold and games cannot cross folds. Unknown flags may only accompany declared unavailable or derived fields.

## Five planted cases

1. Reject a next-event feature whose availability is after prediction_at.
2. Reject a final-outcome feature placed among feature columns.
3. Reject one game assigned to more than one fold.
4. Reject a forged early timestamp only when strict-redaction truncation replay makes prefix predictions differ.
5. Accept a clean control and require byte-identical prefix predictions.

## Fixed census rule

For every in-play parquet found at `data/cache/inplay_odds/`, report every fixed contract field as AVAILABLE, DERIVABLE, or UNAVAILABLE with the store row count. AVAILABLE means a source column directly supplies the field; DERIVABLE means a deterministic transformation using only fields in that parquet supplies it; otherwise UNAVAILABLE. Do not fabricate M0, outcomes, team identities, or sport state. Soccer and tennis game-level companion inputs are not assumed. This lane does not execute the census.

## Fixed scoring statement

No scored comparison is authorized in this lane. If a later finisher scores any candidate, it must use the shared evaluator with purging and symmetric nonzero embargo, one evaluator state per tick keyed by state_key, and archive evaluator-record losses only. Improvement sign convention: baseline loss minus candidate loss; positive means candidate better.

SEAL sha256 7262bbfaf65eab3709d864fbac88a972bb72d83de633c0c949494da18c61bd67
