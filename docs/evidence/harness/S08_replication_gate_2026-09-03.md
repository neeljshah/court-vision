# S08 -- replication floor becomes a GATE, not a convention

**Verdict: ACCEPT WITH CORRECTIONS. Bar 2/2 met** (two constructed verdicts at the
SAME K=14, only `n_corpora` differs). Correction: the register's premise is
PARTIALLY FALSIFIED -- one AHEAD writer the spec did not enumerate,
`scripts/platformkit/eval_gate/stacker.py`, already IMPORTS `min_corpora_eff`, but
only to EMIT it as a field; it still does not downgrade the verdict string. The gap
("replication is a convention, not a gate") therefore stands. Detail below.

Artifacts this lane owns:
`scripts/platformkit/eval_gate/replication_gate.py` (new),
`scripts/platformkit/eval_gate/test_replication_gate.py` (new),
the additive edit in `scripts/platformkit/hedge_trial_runner.py`, this memo.

## Step 0 -- the premise, re-measured on disk (Q8)

Command (run in master, 2026-09-03):

    grep -rln '"AHEAD"' scripts/ domains/ kernel/ src/ api/
    # then, per hit: grep -c min_corpora_eff <file>

| module that writes the literal verdict "AHEAD" | `min_corpora_eff` hits | gates the verdict on it? |
|---|---|---|
| `scripts/platformkit/hedge_trial_runner.py` (:103) | 0 | no |
| `scripts/platformkit/ingame/mlb_winprob_v6.py` (:105, :186-187) | 0 | no |
| `scripts/platformkit/ingame/mlb_winprob_v7.py` (:179) | 0 | no |
| `scripts/platformkit/frontend/slate.py` (:80) | 0 | no |
| `scripts/platformkit/pm_trading/clv_daily_readout.py` (:117) -- NOT in the spec's list | 0 | no |
| `scripts/platformkit/eval_gate/stacker.py` (:224) -- NOT in the spec's list | 2 (:22 import, :244) | **no** -- emit only |

`before` as the ACCEPTANCE RULE defines it (the AHEAD writers the spec names): **0 of
5 consult `min_corpora_eff`**; the module `replication_gate.py` was absent. The
premise HOLDS for the named set.

`stacker.py:244` writes `"min_corpora_eff_at_launch_k": int(min_corpora_eff(1, k)),
"single_window": True` alongside a verdict computed at :224 as
`"AHEAD" if (improvement >= BAR and dm.ci95[0] > 0.0 and p_defl < 0.05) else "BEHIND"`.
It reports the floor and hard-codes `single_window`; it never changes the verdict
string, and its `n_corpora` argument is the literal `1`. So the register's wording
("no call site consults it") is imprecise, but its substance ("a single-window AHEAD
is downgraded only by memo") is TRUE of all six AHEAD writers. Filed as
`NEW GAP: stacker.py emits min_corpora_eff + single_window=True but does not apply
replication_verdict to its own AHEAD, and hard-codes n_corpora=1 rather than counting
disjoint corpus_units.`

The eight existing floor consumers named in the spec (combo_gate.py L5 reject,
stack_gate_pregame.py, selfimprove_stage.py, domains/soccer/home_sot_replication_gate.py,
domains/soccer/interaction_gate.py, domains/basketball_nba/pregame_stack_gate.py) were
NOT touched; none of them writes the literal "AHEAD".

## Step 1 -- the floor in force today

`data/cache/eval_gate/backtest_fwer.jsonl` has **14 rows** (the spec said 13; a 14th
was appended 2026-09-02T05:42:37Z by `stacker:mlb_stack_v1`). Its last
`k_cumulative` is **14** -- READ only, nothing appended by this lane (Q2: this row
is a CONSTRUCT, it charges no trial).

    min_corpora_eff(1, 14) = 2
    min_corpora_eff(2, 14) = 2

(the cap and the `max(2, n_corpora)` clamp both bind: a 1-corpus trial faces a floor
of 2 and cannot clear it; a 2-corpus trial clears at exactly 2.)

## Step 2 -- the change

`replication_verdict(verdict, n_corpora, k) -> str`: `floor =
min_corpora_eff(max(1, n_corpora), k)`; returns `"SINGLE-WINDOW"` iff the verdict is
`"AHEAD"` or `"<prefix>_AHEAD"` AND `n_corpora < floor`; every other verdict is
returned byte-identical. `replication_fields(...)` returns the four auditable keys
`verdict_replicated / min_corpora_eff / n_corpora / k_cumulative`.

One call site, additive: `hedge_trial_runner.verdict_of_replicated(stats, n_corpora)`
plus `stats.update(replication_fields(...))` and a `replication_label` key written
BESIDE `"verdict"` in `run_sport`'s block. `verdict_of` is unchanged -- same name,
same two return values, same BAR. `N_CORPORA_PER_SPORT = 1` because one `run_sport`
call scores one disjoint corpus_unit (mlb and soccer_intl are scored separately).

`scripts/platformkit/combo/fwer_budget.py` is a SHARED MODULE and was imported
READ-ONLY; no constant, threshold or bar in it moved (B10 / Q3).

## The four-case table (bar = the first two, at the SAME K=14)

| case | verdict in | n_corpora | K | floor | out | role |
|---|---|---|---|---|---|---|
| (a) | AHEAD | 1 | 14 | 2 | **SINGLE-WINDOW** | BAR 1/2 |
| (b) | AHEAD | 2 | 14 | 2 | **AHEAD** (unchanged) | BAR 2/2 |
| (c) | BEHIND / MATCH / NULL / INSUFFICIENT / REJECT / PAR | 1 | 14 | 2 | unchanged, byte-identical | invariance |
| (d) | `verdict_of(stats)` on master's own four fixtures | -- | 14 | -- | AHEAD, BEHIND, BEHIND, BEHIND | invariance |

**Bar met: 2/2.** Non-tautology: (a) and (b) run at the SAME K, so only `n_corpora`
differs and the downgrade cannot be an artifact of a moved K.

## Commands and results (reproduction, A2; S-row has no eye check, Q7)

    python -m pytest scripts/platformkit/eval_gate/test_replication_gate.py -q -p no:cacheprovider
    5 passed in 2.88s

    python -m pytest scripts/platformkit/test_hedge_trial_arms.py -q -p no:cacheprovider
    6 passed in 2.23s          # unchanged from master: still 6 passed

## NOT VERIFIED

- **No real AHEAD exists to downgrade today.** The MLB hedge trial's standing verdict
  is BEHIND (single-window, K=14); the gate has never fired on live data, only on the
  two constructed cases. This is a CONSTRUCT row (n = 2 (CONSTRUCT), Q7).
- **AHEAD writers left unwired** (follow-up rows, not edited here):
  `scripts/platformkit/ingame/mlb_winprob_v6.py` (:105, :186-187),
  `scripts/platformkit/ingame/mlb_winprob_v7.py` (:179),
  `scripts/platformkit/frontend/slate.py` (:80),
  `scripts/platformkit/pm_trading/clv_daily_readout.py` (:117, not in the spec's list),
  `scripts/platformkit/eval_gate/stacker.py` (:224, emit-only -- see the NEW GAP above).
- `N_CORPORA_PER_SPORT = 1` is asserted from the runner's structure, not derived from a
  `corpus_unit` column; nothing in the tick store labels corpus_units, so a future
  multi-corpus trial must pass its own count rather than inherit this constant.
- The four new stats keys and `replication_label` are additive; every reader of
  `hedge_trial_2026-09-01.json` was grepped and none consumes a fixed key set, but the
  artifact itself was NOT regenerated (that would charge the ledger).
- Calibration language only (Q6): no dollar, ROI, profit or edge wording; a
  SINGLE-WINDOW downgrade is an honest result, not a failure.
