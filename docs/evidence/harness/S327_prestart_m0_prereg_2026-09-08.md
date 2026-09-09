# S327 preregistration: prestart M0 table

Purpose: construct an auditable M0 availability and join census only. No calibration comparison or threshold claim is scored in this lane.

Inputs: the exact stores and state archives named in `docs/evidence/tracking/specs/S327_spec.md`, read locally and one parquet row group at a time. A missing repo-relative store is emitted as `ABSENT-IN-WORKTREE <path>` in the census, not treated as adverse evidence.

Selection: group quotes by normalized sport and state-archive event key. For a known event start, select the latest valid market-implied probability whose quote timestamp is strictly before the start. If none exists, select the earliest valid quote from start through start plus 60 seconds as `AT_TIP`. If none exists, select the earliest later valid in-play quote as `FIRST_INPLAY`. Otherwise emit `NONE`. `sec_before_start = quote_ts - start_ts`; therefore negative values are before start and positive values are after start.

Probability source: only explicit market probability fields (`p_prestart`, `probability`, `implied_probability`, `p_close`, `close_prob`, `price`, `yes_price`) are eligible, after numeric validation in [0, 1]. Rating fields, including `p0`, Elo, ratings, model, prediction, and forecast fields, are never eligible.

Mapping: use only `domains/cross_sport_market/prestart_m0_name_map.json`. Exact normalized identifiers pass unchanged; unmapped team or player identifiers are retained in a per-sport unmapped report with counts and never silently dropped.

State join: use stable event ids when available; otherwise require the mapped participant pair and event date. The implementation writes one M0 row per state event, with source, venue, quote and start timestamps, and a labelled kind.

Scoring declaration: no scored comparison is authorized by this preregistration. If a future comparison is added, it must use `scripts/platformkit/eval_gate/walkforward.py` or CPCV with purge and a symmetric nonzero embargo, one stable evaluator state per scored tick, and evaluator records as its sole loss archive. Delta convention: improvement = baseline loss minus candidate loss; positive means candidate better.

Archive staging: NONE (committed evidence read in place).
SEAL sha256 a7df4a23a11f9a1c70dc0e2324c4875d5dffd8522ea26811113f1787e1e57a5e
