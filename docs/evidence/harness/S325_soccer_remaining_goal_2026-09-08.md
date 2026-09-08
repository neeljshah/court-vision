**VERDICT: INSUFFICIENT**

S325 premise close-out. Spec: docs/evidence/tracking/specs/S325_spec.md. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md (B and Q self-check).
Machine: LOCAL, using conda basketball_ai; the row specifies local execution.
Binding before-condition rerun: p0 is rating-derived in every league, and no market-implied pre-start p0 joins for 300 games in two leagues. Therefore bar C is blocked before scoring.

| league | state input (bytes; resolution) | games | states | p0 nonnull | p0 producer | target | xG coverage | price-joinable games |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | ---: |
| eng1 | C:/Users/neelj/nba-track-a3/data/cache/ingame/soccer_states__eng1.parquet (21717; 7220x11) | 380 | 7220 | 7220 | domains/soccer/ingest_soccer_states.py:245,288; train-history Elo + HFA | 2-way, 0/1 | 6954/7220 (96.3%) | 0 |
| esp1 | C:/Users/neelj/nba-track-a3/data/cache/ingame/soccer_states__esp1.parquet (21537; 7220x11) | 380 | 7220 | 7220 | domains/soccer/ingest_soccer_states.py:245,288; train-history Elo + HFA | 2-way, 0/1 | 7087/7220 (98.2%) | 0 |
| ger1 | C:/Users/neelj/nba-track-a3/data/cache/ingame/soccer_states__ger1.parquet (19048; 5795x11) | 305 | 5795 | 5795 | domains/soccer/ingest_soccer_states.py:245,288; train-history Elo + HFA | 2-way, 0/1 | 5757/5795 (99.3%) | 0 |
| ita1 | C:/Users/neelj/nba-track-a3/data/cache/ingame/soccer_states__ita1.parquet (21502; 7163x11) | 377 | 7163 | 7163 | domains/soccer/ingest_soccer_states.py:245,288; train-history Elo + HFA | 2-way, 0/1 | 7163/7163 (100.0%) | 0 |

| xG input (bytes; resolution) | observed join |
| --- | --- |
| C:/Users/neelj/nba-track-a3/data/cache/ingame/soccer_shotxgstates__eng1.parquet (128904; 6954x6) | 366/380 games, 6954 states |
| C:/Users/neelj/nba-track-a3/data/cache/ingame/soccer_shotxgstates__esp1.parquet (126528; 7087x6) | 373/380 games, 7087 states |
| C:/Users/neelj/nba-track-a3/data/cache/ingame/soccer_shotxgstates__ger1.parquet (107211; 5757x6) | 303/305 games, 5757 states |
| C:/Users/neelj/nba-track-a3/data/cache/ingame/soccer_shotxgstates__ita1.parquet (129774; 7220x6) | 377/377 games, 7163 states |

| price input (bytes; resolution) | date range | join result |
| --- | --- | --- |
| C:/Users/neelj/nba-track-a3/data/cache/inplay_odds/soccer_price_series.parquet (626996; 204435x12) | 2026-05-03..2026-05-24 | no game_id; no overlap with 2024-08..2025-05 state dates; 0 joins |
| C:/Users/neelj/nba-track-a3/data/cache/inplay_odds/soccer_intl_price_series.parquet (5827874; 2261903x12) | 2026-06-11..2026-07-07 | no game_id; no overlap with 2024-08..2025-05 state dates; 0 joins |

The states store p0 once per game. Its sole observed producer builds an Elo map strictly before match date, then calls _p0 from Elo plus home-field adjustment; it is not a market-implied pre-start probability.
The price stores cannot supply the required pre-start p0: their schemas omit game_id and their dates do not overlap any domestic corpus. No data/cache games.parquet was present, and no quoted totals line was available; no totals estimand is made.
Audit/scoring table: BLOCKED BY FALSE PREMISE. No S309 score, model fit, comparison, bootstrap, shuffle, family correction, ablation, fixed-landmark audit, or test ran. No preregistration seal or ledger charge was made because no scored comparison occurred (Q1/Q2); no bar was moved (Q3); no OOS evaluator state was created (Q4); no calibration claim is made (Q6).
Delta convention, not exercised: improvement = baseline loss minus candidate loss; positive means candidate better. Eye check: NONE. Wall time: 00:01:32.
Git index access was sandbox-denied; the orchestrator commits this memo by lane_commit with an explicit pathspec.
Proposed ledger line only (not written): 2026-09-08 | in-game calibration | S325 | rating-derived p0 and 0 domestic price joins across 4 leagues | INSUFFICIENT

NOT VERIFIED:
- A market-implied pre-start p0 for at least 300 games in at least two domestic leagues.
- Any outcome calibration metric, CI, bar C decision, or per-corpus loss series.
- xG revision availability, card-state joins, 100-state prefix replay, and S320 audit checks.
- Combo and World Cup sensitivity corpora; they were not needed after the binding premise failed.
