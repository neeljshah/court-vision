# S229 Attempt 2 Preregistration

Scope: local, offline calibration measurement in `C:\Users\neelj\nba-track-a17`. The read-only inputs are the three S229 sidecars, archived PTS decomposition OOF target surface, and schedule bridge named in the S229 memo. One store is opened at a time; no store above 300 MB is opened. The matchup atlas is BLOCKED-ON-S223 and is never opened or joined. No data, ledger, register, feature flag, or production route changes.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. This preregistration is written and sealed before this attempt's fresh scoring process starts.

Arms: the baseline columns are exactly `player_pts_vs_HELP_DEF_diff` and `player_opp_pts_diff_vs_overall`. The real candidate appends exactly `scheme_x_opponent`, the product of those values. The planted-null candidate holds the same baseline fixed and appends exactly `null_interaction`, the product of the prebuilt null-twin scheme value and the same opponent value. An assertion requires the real candidate prefix to equal the baseline columns. All three arms use identical joined, finite, game-clustered rows in each fold.

Coverage: first report the direct DEF-OPP key join before any target merge, over the fixed 99,498 defender-sidecar rows. Then separately report the target-readable DEF-OPP join and all subsequent named losses. The baseline RMSE and MAE are reported before interaction deltas. The joined subset must report its PTS base rate and residual spread beside the full target-readable surface.

OOS fold scheme: split sorted distinct `game_date` values into five chronological blocks; the first is seed-only and blocks 1 through 4 are scored once. For every scored block, training dates must be strictly earlier than its first date. The S229 date-fold helper must purge every training game cluster that appears in the scored block and apply a symmetric, nonzero one-calendar-day embargo around every scored date. It asserts no retained training row lies within one day on either side of any scored row. This local helper is used because `eval_gate.walkforward.walk_forward` accepts game-state dictionaries and has no symmetric date-fold embargo, while `eval_gate.cpcv_engine.cpcv_evaluate` has a symmetric route but requires incompatible game-state/vintage inputs.

Frozen bar and verdict: retain the spec's minimum of 30 game clusters. Compute game-equal-weighted RMSE and MAE from the paired per-game archive, with deterministic 2,000-draw game-cluster bootstrap confidence intervals and n_eff. Verdict is `SCREEN NULL` unless the cluster count is below 30, when it is `CLOSED AT LIMIT`; no outcome is served, promoted, enabled, charged, or entered in a ledger or register. NULL or BEHIND is the expected valid calibration outcome. This attempt does not alter the S229 acceptance bar.

Artifacts: the fresh memo and paired per-game CSV embed this preregistration path and the seal below. The CSV carries the preregistration path and seal as constant columns so its differential is independently attributable.

Seal SHA-256 of the pre-seal content above: `6ca56099a0bac5067f68740ae7d9ac2bdbf1d2c6fa71e75728ace6e1210ef1e7`.
