VERDICT: INSUFFICIENT

S324 binding premise close. This memo cites `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.
Machine: LOCAL, conda `basketball_ai`, `C:\\Users\\neelj\\anaconda3\\envs\\basketball_ai\\python.exe` (3.10.20); S324 specifies LOCAL and the scan was batch-bounded.
Wall time: about 00:25:00, premise inspection plus artifact preparation; no scored comparison ran.
Eye check: NONE.

Binding commands (before any score):
`conda run -n basketball_ai python .planning\\s324-execution\\binding_counts.py`
`conda run -n basketball_ai python .planning\\s324-execution\\quote_join_counts_vectorized.py`

Binding output: `p0` is a walk-forward Elo rating: `domains/mlb/ingest_pitch_states.py:343,350-351,376` imports `walk_forward_elo` and writes `p_home_elo` to `p0`.

| Season | Game IDs | Pitch states | p0 non-null | Joinable live ML games | base_out_known |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2022 | 199 | 66,266 | 66,266 | 0 | 41,715 / 41,715 |
| 2023 | 200 | 69,823 | 69,823 | 0 | 41,866 / 41,866 |
| 2024 | 243 | 70,326 | 70,326 | 0 | 41,870 / 41,870 |
| 2025 | 231 | 65,983 | 65,983 | 0 | NOT SUPPLIED |
| 2026 | 100 | 29,319 | 29,319 | 59 | NOT SUPPLIED |

The full quote scan reduced 13,473,591 rows to 972 Kalshi moneyline event keys (2 unparsed, 0 unresolved) with the exact parser and team map in `scripts/platformkit/eval_gate/close_join_mlb.py:52-118`. Join is exact date plus parsed home/away codes; no fuzzy matching.

PREMISE FALSIFIED: every archive corpus has fewer than 300 game IDs, and the Elo `p0` cannot be replaced by market-implied pre-start probability for 300 games in two seasons. Per S324's binding STOP condition, scoring is blocked and no model, comparer, audit, test, preregistration, flag, register, ledger, existing landed file, or production path changed.

Input paths opened (bytes; tabular Parquet, so pixel resolution is N/A):
`data/cache/ingame/mlb_pitch_states__2022.parquet` 503175; `data/cache/ingame/mlb_pitch_states__2023.parquet` 549621; `data/cache/ingame/mlb_pitch_states__2024.parquet` 534664.
`data/cache/ingame/mlb_pitch_states__2025.parquet` 496094; `data/cache/ingame/mlb_pitch_states__2026.parquet` 234626; `data/cache/ingame/mlb_states__2021.parquet` 133332.
`data/cache/ingame/mlb_states__2022.parquet` 139220; `data/cache/ingame/mlb_states__2023.parquet` 138484; `data/cache/ingame/mlb_states__2024.parquet` 133819.
`data/cache/ingame/mlb_atbat_states__2022.parquet` 57411; `data/cache/ingame/mlb_atbat_states__2023.parquet` 55481; `data/cache/inplay_odds/mlb_price_series.parquet` 33852193.

Sign convention for any future score delta: improvement = baseline loss minus candidate loss; positive = candidate better. No delta was computed here.
Proposed ledger line for the lander only: `2026-09-08 | in-game calibration | S324 | Elo p0 and fewer than 300 games in every corpus; ML joins 0/0/0/0/59 | INSUFFICIENT`

LF SHA-256 values (unstaged evidence bytes, CRLF normalized to LF because the sandbox denied `git add`):
`2022_premise.csv` 2cd0c36c5d67198757c56c319f341a06491e6ba0c3191eca24f068231867ef2a; `2023_premise.csv` 36771d6f167c5e1de619088f30ae74f69374cfda450c9f4a03ffa79b328c011b.
`2024_premise.csv` 16dfdf147cde4afc6d5311982a0aad2adb8e38c294ea5f2fd6e092f76011c4e1; `2025_premise.csv` 0e262587c362c80f9d1d3ed6c0ae8bacb6f6627af065c7698d0fb93b3806fb9a.
`2026_premise.csv` 99f7637df4aefe4341e1eefc5973708cdc93965129a1d9d3f37274a06170b309. The orchestrator commits these exact files by explicit pathspec (`lane_commit`).

NOT VERIFIED:
- The required 100-state ordering, availability, polarity, duplicate, prefix-replay, and pitch-delay audit; it is blocked before scoring.
- Walk-forward/CPCV, purge/embargo, Brier, ECE, log score, confidence intervals, shuffle, ablation, family correction, and bar C.
- The S324 test file; no model or comparer may be prepared after the binding STOP condition.
- MLB market coverage beyond the reported supplied archive and quote series; KBO/NPB rules are out of scope.
