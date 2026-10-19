# R2 scorer result, 2026-10-06

BUILT WITH GAPS: public scorer, data-card template and fixed-seed tests built in cxp/R2-vs-close-2026-10-06.
calibration readout, paper only, not a verdict

Built: `scripts/platformkit/eval_gate/score_vs_close.py`, `score_vs_close_card.md`, `test_score_vs_close.py`.
Scorer runtime imports only numpy, stdlib and public `dm_test`; no corpus or private module is required.
JSON stdout and optional file carry paired Brier, log loss, game CI, DM statistic/p, MDE and ten bins.
All input failures refuse the entire CSV (exit 3) with overlapping counted reasons; floor = 500.
`--devig` asserts the existing method, or omission infers it; already devigged probabilities cannot be re-devigged.

Premises (paths below are under `scripts/platformkit/eval_gate/` unless qualified):
- (a) `dm_recompute_pregame.py:62-68`: holdout only; clip to [1e-6,1-1e-6]; mean binary `(p-y)**2`, no factor two.
  Cluster = `cluster_id`; soccer event_id at :125, MLB event_id at :103, NBA date/teams at :144-145.
  Here each unique match_id is one cluster; duplicates refuse. No date clustering is substituted.
- (b) Proportional is inline division, not a named helper (`dm_recompute_pregame.py:98,114,139`).
  Shin helpers are `_shin_one`/:49, `_shin_home`/:56, calling `shin.shin_devig(pi, tol=1e-12, max_iter=200)`/:38.
  `shin_devig` returns probabilities and z; `shin_devig_decimal`/:82 wraps decimal inputs. Scorer imports neither.
- (c) `dm_test.py:108`: `diebold_mariano(d, cluster_ids) -> DMResult`; fields at :86-93 are
  dm_stat, p_value, mean_diff, ci95, n, n_clusters. Student-t interval and p use G-1 at :128-136.
  Its docstring uses the opposite difference sign; the caller controls it. R2 uses model minus close.
- (d) `dm_recompute_pregame.py:38,70,77`: MDE at approximate 80 pct power = 1.429 * CI half-width.
- (e) Existing table `backtest_runner.py:152-158` uses ten equal-width bins, not equal-count.
  Equal-count precedent: `s58_nba_halftime_asof_trial.py:87-89` sorts then array_split(...,10).
  R2 follows requested equal-count convention, with match_id tie-breaks; counts differ by at most one.
- `CANONICAL_FIGURES.json` and `claim_consistency.py:53-108` were read; no new corpus claim is licensed here.
  `public_allowlist.txt:54` allows the eval_gate directory. Existing reference files are unchanged from HEAD.

Validation commands (local Windows, no network; one test file per process):
```text
New-Item -ItemType Directory -Path .r2-test-tmp -Force
python -m pytest scripts/platformkit/eval_gate/test_score_vs_close.py -q -p no:cacheprovider --basetemp=.r2-test-tmp/t
python -m pytest scripts/platformkit/eval_gate/test_eval_core.py -q -p no:cacheprovider --basetemp=.r2-test-tmp/core
python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q -p no:cacheprovider --basetemp=.r2-test-tmp/recompute
```
Results: scorer 35 passed initially and 35 after restoring mutants; existing core 17 passed; existing recompute 4 passed.
Public subset check: copied only scorer, DM and scorer tests into `.r2-test-tmp/public` with an empty pytest config.
From that directory: `python -m pytest scripts/platformkit/eval_gate/test_score_vs_close.py -q -p no:cacheprovider --basetemp=t`.
Result: 35 passed without the private tree. Read-only review found no blockers.
Cleanup gap: automatic approval review rejected recursive and guarded per-file scratch deletion as "blocked by policy".
`.r2-test-tmp` remains untracked; no cleanup permission escalation is available in this session.
Commit gap: explicit-path `git add --` failed creating the worktree's index.lock: Permission denied.
The Git metadata lives outside this writable worktree; files remain uncommitted. No push was attempted.
Requested `test_dm_test*.py` files do not exist (recursive filename search); the two existing files above substitute.
`rg` is unavailable; Python/PowerShell searches were used. No whole-directory test command was run.

Mutation power: each command below used the scorer test path with `-q -p no:cacheprovider --basetemp=.r2-test-tmp/mutation -k NAME`.
| NAME | Temporary production mutation | Observed failure, test file line | Count |
|---|---|---|---|
| test_leak_mutant | disable `if leak.any()` reporting | :72, missing leak_signature count (`None != 1`) | 1 failed, 34 deselected |
| test_duplicate_mutant | disable duplicate guard | :90, status OK instead of REFUSED | 1 failed, 34 deselected |
| test_shuffle_mutant | bypass outcome dependence: use `(pc > 0.5)` as y for losses | :81, gap change 0.0 is not > 0.05 | 1 failed, 34 deselected |
Each mutation was applied separately and restored byte-for-byte in finally. Shuffle is a sensitivity test, not a rejection guard.
The known fixture recovers model 0.1525, close 0.1000, gap 0.0525; DM p/stat/CI exactly match the public function.

Next export commands, for the Claude corpus lane ONLY; not executed here. Run from the full corpus checkout.
These reuse the same harness functions; no model is reimplemented. They write two CSVs and two adjacent cards.
Ledger rows 7/8 read OK, but their scope and actual source provenance require the corpus lane's review before publication.
```powershell
@'
from pathlib import Path
import hashlib, os, subprocess
import numpy as np
import pandas as pd
from scripts.platformkit.eval_gate import dm_recompute_pregame as r
from scripts.platformkit.proof_tennis import beat_the_close_ml as t
assert not os.environ.get('PROOF_CORPUS_ROOT'), 'Use the named default private sources'
out = Path('docs/evidence/pregame_vs_close')
out.mkdir(parents=True, exist_ok=True)
revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
def emit(name, frame, close, source, ledger, inputs, exclusions):
    rows = pd.DataFrame({'date_utc': pd.to_datetime(frame['date'], utc=True).dt.strftime('%Y-%m-%d'),
        'match_id': frame['event_id'].astype(str),
        'p_model': np.clip(frame['p_model'].to_numpy(float), 1e-6, 1-1e-6),
        'p_close_devig': np.clip(frame[close].to_numpy(float), 1e-6, 1-1e-6),
        'devig_method': 'proportional', 'y': frame['y'].to_numpy(int)})
    rows.to_csv(out / (name + '.csv'), index=False, float_format='%.17g', lineterminator='\n')
    hashes = '; '.join(str(p) + ': ' + hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in inputs)
    card = (f'# {name}\n\nSource: {source}\nLicence ledger row: {ledger}\nDevig method: proportional\n'
        f'Exclusions: {exclusions}\nSHA256 of private source file(s): {hashes}\nRow count: {len(rows)}\n'
        f'Generated-by command: export block in R2_score_vs_close_result_2026-10-06.md; revision {revision}; default corpus\n'
        'Date precision only; no intraday timestamp claim. Probabilities clipped at [1e-6,1-1e-6].\n'
        'NOT VERIFIED: licence scope, source chronology, uniqueness and Tier-1 reproduction pending.\n'
        'calibration readout, paper only, not a verdict\n')
    (out / (name + '_card.md')).write_text(card, encoding='ascii')
s = r.rows_soccer()
fit = int(s['split'].eq('fit').sum())
s = s.loc[s['split'].eq('holdout') & s['p_close'].notna()].copy()
emit('soccer_ou25_holdout', s, 'p_close', 'football-data.co.uk; y = over 2.5 goals',
    'docs/evidence/LICENCE_LEDGER.md row 7 (OK)', r.INPUTS['soccer_ou25'],
    f'existing join/valid-close/non-null filters; fit half excluded={fit}; upstream filter counts require census')
matches, odds = pd.read_parquet(t._MATCHES), pd.read_parquet(t._ODDS)
w = t._walk_forward_blend(matches, blend=t.SURFACE_BLEND)
a = t.platt_recalibrate(w, train_year_max=t._TRAIN_YEAR_MAX).copy()
a['p_model'] = np.where(a['win_prob_recal'].isna(), a['win_prob_p1'], a['win_prob_recal'])
a = a.merge(t._devig_market(odds), on='event_id', how='inner').dropna(subset=['p_model','p_market'])
a['y'] = (a['winner'] == 1).astype(int)
emit('atp_holdout', a, 'p_market', 'tennis-data.co.uk close; y = lower-id player wins',
    'docs/evidence/LICENCE_LEDGER.md row 8 (OK; close only)', [t._MATCHES, t._ODDS],
    'years through 2022 used for fit; existing join/valid-close/non-null filters; exclusion counts require census')
'@ | python -
python -m scripts.platformkit.eval_gate.score_vs_close --csv docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv --devig proportional
python -m scripts.platformkit.eval_gate.score_vs_close --csv docs/evidence/pregame_vs_close/atp_holdout.csv --devig proportional
```

Export references: soccer `dm_recompute_pregame.py:108-126`; ATP `proof_tennis/beat_the_close_ml.py:78-97`.
ATP test years are strictly held out (`domains/tennis/elo_tune.py:205-208,242-244`).
NOT VERIFIED: real CSVs, cards, licences for all inputs, timestamps, or reproduction to four decimals (Tier 1).
Tier 1 targets remain soccer n=7,558, Brier 0.2465/0.2390; ATP n=7,374, Brier 0.2177/0.2028.
ATP duplicate IDs are documented in `domains/tennis/event_uid.py:11-16`; current harness joins event_id without dedup.
If any survive holdout, R2 must refuse; never invent suffixes or silently deduplicate to reproduce a row.
The inherited DM implementation returns stat=0/p=1 when SE=0, even for constant nonzero differences (:130-135).
That reference behavior is unchanged; a MATCHES_CLOSE label never establishes equal calibration.

## Export (2026-10-06, R2 export lane)

Tier correction applied: `score_vs_close.py` now counts any row with |p_model - y| <= 1e-3 as
`leak_signature` and refuses (the old `p_model == y` guard was dominated by the open-interval
check, so p=0.999 agreeing with y passed). `gap_sign` now also says dm_stat has the same sign as
gap. New test `test_near_perfect_leak_refused` (0.999/0.001 flagged, 0.998/0.002 not);
`test_reference_clip_and_identical_forecasts` moved its 1e-9 forecasts to y=1 rows only, since
1e-9 on a y=0 row is itself a near-perfect leak. 36 passed.

Soccer: `export_vs_close.py` (read-only call into `dm_recompute_pregame.rows_soccer`, cluster_id
as match_id, holdout split, proportional devig) wrote `docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv`
(7,558 rows, sha256 68084c2d...0105). Input sha256s equal the DM memo's. Scorer: n 7,558, model
Brier 0.24653, close 0.23896, gap +0.007576, CI [+0.005945, +0.009206], DM p 1.08e-19, MDE
0.00233, TRAILS_CLOSE. Reproduces the DM memo row to four decimals (Tier 1 met).

ATP: NOT PUBLISHED. Licence ledger row 8 (tennis-data.co.uk, the close) is OK, but the match
spine, outcomes and every Elo input come from `data/domains/tennis/matches.parquet` = row 10
(Sackmann), verdict UNREAD. Private check only (nothing written to the tree): the harness
reproduces n 7,374, Brier 0.2177 vs 0.2028, gap +0.0149; but 21 event_ids appear twice (each
joined to two different closes), so the scorer refuses the rows (`duplicated_match_id` 21).
Clustered by event_id for information only: 7,353 clusters, CI [+0.0127, +0.0170], TRAILS. The DM
memo publishes no ATP interval, so there is no published interval to match.
