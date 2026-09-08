# S320 timestamp artifact audit preregistration

Row: S320. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.

Scope: preparation only. No parquet audit, replay, comparison, metric, or model fit has run in this lane.

Input: data/cache/inplay_odds/nba_checkpoints_full.parquet. The finisher records its byte size and SHA-256 before use.

Seed: 32020260908.

Population and strata: all input ticks, partitioned by exact period x absolute-margin bucket (0-3, 4-9, 10+) x clock bucket (>300 s, 60-300 s, <60 s, ==0 s). A state is identified by (game_id, state_ts), where state_ts is the integer ts rendered as UTC ISO-8601.

100-state rule: before any audit or replay, sort each stratum by SHA-256(seed + game_id + state_ts), take five unique pairs from every non-empty stratum, then allocate remaining positions round-robin over the same ordered strata. Deduplicate pairs globally and write exactly 100 pairs plus the SHA-256 digest of the CSV. If more than 20 strata are non-empty, this binding requirement cannot produce both exactly 100 pairs and five per non-empty stratum; stop as PARTIAL and report the non-empty-stratum count without auditing or scoring.

Checks for every sealed pair: availability of each null feature (market_prob and game_date) at or before prediction time; status using the S309 terminal mask; target polarity using side and venue evidence with paired sides merged; duplicate (game_id, state_ts) keys; and settlement only after the final tick. If received_at is absent, record tick-order-only availability. Missing evidence is NOT VERIFIED, not accepted.

Replay arms: frozen recalibrated null N and market prior M0. For each sealed state, compare full history a with prefix history b (all records after the state deleted), and delayed history c (only records at least 60 seconds old). The bar is max absolute(b-a) == 0 for both arms. Every nonzero c-a must name a record in the 60-second delay window; otherwise it is a violation. The evaluator is scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate with chronological groups, whole-game grouping, purge, and a symmetric nonzero 24-hour embargo; one evaluator state exists for each scored tick.

Sign convention: improvement equals baseline loss minus candidate loss; positive means candidate better. This preparation makes no comparison claim.

SEAL sha256 af660453ef6c9c12822b32b812d4e96aeb985c2f8d56114b9042acdd7106ae95
