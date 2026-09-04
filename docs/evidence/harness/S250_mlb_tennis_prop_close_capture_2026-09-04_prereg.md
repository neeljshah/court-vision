# S250 MLB and Tennis Prop Close Capture - Attempt 1c Preregistration

## Fixed before any capture metric

S250 will measure, without a predictive-model comparison, whether the historical
The Odds API single-event player-prop tier can provide concrete finite prices for
MLB and tennis. The NBA reference producer is the historical
`scripts/cv_fix_fetch_closing.py` version at
`0f1aff49f4be8fb1d97984d9f60e0425a068d14c`; its `event_odds` call fetched
`/v4/historical/sports/basketball_nba/events/{event_id}/odds` and wrote each
raw payload to `data/cache/cv_fix/closing_props/{gid}.json`.

The attempt will use that tier's single-event route only. It will first list
events, then make at most one player-market request per sport for the LIMIT
probe. Any later capture poll will issue serialized requests at least four
seconds apart, below the provider's documented 30-calls-per-second limit. It
will use an environment-only `ODDS_API_KEY`; no embedded, file-based, or
historical credential is permitted.

## Fixed capture protocol

The capture artifact is
`docs/evidence/harness/S250_mlb_tennis_prop_close_capture_2026-09-04.jsonl`.
Each row is append-only and has `sport`, `event_id`, `market`, `ts`,
`price`, and `attempt_reason`. Its identity is exactly
`(sport, event_id, market, ts)`. A concrete price is finite after numeric
conversion. The denominator retains every attempted event-market cluster,
including empty, unsupported, unavailable, and rate-limited responses, with
their reason. A cluster is an event id when present, otherwise the UTC date of
the attempt; duplicate identity rows are counted across the full JSONL.

The acceptance bar remains exactly: at least 30 real-priced clusters for MLB
or tennis, or a per-sport CLOSED AT LIMIT verdict naming the missing sport or
market. The restart construct is exhaustive: clean stop, mid-poll interrupt,
and process kill while a row write is pending. Each case must resume with zero
duplicate identities and no lost committed snapshot.

No model, calibration, or comparative loss is planned here. If a later task
uses these captures for any calibration score, it must run through the shared
purge plus symmetric-embargo evaluator; this capture census itself is an
exhaustive availability measurement, not an OOS comparison.

Seal SHA-256: 3ac24eae6881a9db2d529a6559a59a5635efe806155f81b80a37d84ace8cc96e
