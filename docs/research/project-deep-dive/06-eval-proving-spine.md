# 06 -- Eval-Gate / Calibration / CLV / Paper-Loop Proving Spine (the honesty core)

Area owner doc for the deep project-understanding report. READ-ONLY analysis; no code
was changed. This is the machinery that decides whether a prediction change is allowed
to ship, and whether a "win" is real. The binding stance everywhere: markets are
efficient, the honest win is CALIBRATION not a dollar edge, an honest REJECT is a
SUCCESS, everything is PAPER-only.

All paths are relative to repo root `C:/Users/neelj/nba-ai-system`.

---

## 1. INVENTORY -- what EXISTS and is USED

### Eval-gate reference core (`scripts/platformkit/eval_gate/`)
- `scoring.py` -- proper-scoring metrics: `brier`, `ece`, `log_loss`, `brier_skill_score`,
  `resolution`, `sharpness`, plus distributional `crps_gaussian`, `crps_ensemble`,
  `pinball_loss`. Reuses kernel `brier`/`ece` when the editable install is present, else a
  byte-equivalent numpy fallback (`_KERNEL` flag exposes provenance).
- `walkforward.py` -- the leak-free expanding-window harness (`walk_forward`) with
  purge (48h same-team) + embargo (3d same-matchup) + a `assert_vintage` leak guard.
- `dm_test.py` -- cluster-robust Diebold-Mariano test (`diebold_mariano`) clustered by
  `game_id` with a G/(G-1) finite-cluster correction.
- `shin.py` -- Shin (1992/93) n-outcome devig solver (`shin_devig`, `shin_devig_decimal`)
  that renormalizes to exactly 1 and recovers the insider proportion z.
- `baseline.py` -- pre-registered frozen baselines (`load_baseline`, `freeze_baseline`,
  `register_skip`, `_freeze_from_offline`); writes `baselines/<corpus>.json`.
- `offline_predict.py` -- deterministic within-window ridge-logistic fixture predictor
  (`offline_predict_fn`) + `degraded_predict_fn` factory for the regression test.
- `gen_golden.py` -- deterministic synthetic golden-fixture generator (seed 20260616).
- `golden_loader.py`, `schema.py` -- load + validate the committed fixture (leak +
  regime-coverage guards via `validate_golden`).
- `run_gate.py` -- the CLI contract: `python -m scripts.platformkit.eval_gate.run_gate
  --golden`; orchestrates walk-forward + scoring + DM + verdict + regression rule +
  scoreboard, exits 0/1 (fail-closed).
- `run_all.py` -- runs every reference test module, consolidated scoreboard, exit 0 iff green.
- `ingame_blend.py`, `freshness_schema.py`, `ledger.py` -- adjacent reference modules
  (in-game blend, freshness schema, a minimal ledger) with their own tests.
- `baselines/{nba_2023_24,nba_2024_25,mlb_2024}.json` -- frozen synthetic anchors
  (nba_2023_24: n=51, brier_model 0.2298, brier_close 0.1851, bss -0.2411, MATCHES_CLOSE;
  mlb registered-skip-until-X2).
- Tests: `test_eval_core.py`, `test_gate.py`, `test_walkforward.py`, `test_shin.py`,
  `test_ingame_blend.py`, `test_freshness.py`, `test_ledger.py` (all per-file runnable).

### Calibration / recalibration (`scripts/platformkit/`)
- `recalibration.py` -- sport-agnostic strictly-leak-free expanding-window isotonic
  recalibrator (`walk_forward_recalibrate`, `measure_recal`, `measure_sport_recal`);
  exports `CALIBRATION_NOTE`.
- `props_eval.py` -- soccer prop calibration readout (`score_prop_predictions`,
  `backtest_calibration`, `backtest_pairs`, `write_calibration_cache`) -- leak-free
  walk-forward per match.
- `props_eval_mlb.py` -- MLB analog (sibling).
- `prop_tiering.py` -- the tiered-evidence labeller (`classify`, `apply_tier`,
  `calibration_rank_key`) mapping measured BSS to {proven, marginal, weak, unmeasured}
  and edges to MODEL_VIEW vs CALIBRATION_PROVEN.
- `recal_eval.py` -- HONEST temporal OOS test of the isotonic prop-recalibrator
  (`run_eval`, `_verdict`) with an in-sample-vs-OOS overfit tell.

### CLV ledger + paper loop (`scripts/platformkit/`)
- `clv_ledger.py` -- append-only team-bet ledger (`record_bet`, `compute_clv`,
  `settle_closing_line`, `append_settlement`, `load_ledger`, `clv_summary`).
- `grade_paper.py` -- auto-settle open paper bets from the keyless ESPN scoreboard
  (`grade_open_bets`, `grade_one`, `grade_summary`); CLV via last-price proxy.
- `prop_paper.py` + `prop_paper_store.py` -- paper PROP ledger (`record_board`,
  `grade_open`, `prop_summary`, idempotent append store).
- `prop_settle.py` -- lives at `domains/soccer/prop_settle.py` (`realized_stat`,
  `settle_prop`), consumed by `prop_paper`.
- `prop_line_history.py` -- closing-line capture for props (`log_board_lines`,
  `closing_snapshot`, `clv_vs_close`) -> true prop CLV.
- `prop_loop.py` -- unattended paper-accrual tick/forever loop for props.
- `self_improve.py` -- THE RATCHET: leak-free continuous-calibration cycle per sport
  (`load_settled`, `honest_readout`, `improve_cycle`, `improve_all`) -> verdict
  {SHIP, HOLD, REJECT, INSUFFICIENT_DATA} into `improve_ledger.jsonl`.
- `pm_trading/auto_loop.py` -- the always-on `--forever` cycle wiring
  paper-trade -> grade -> self-improve (`run_once`, `main`).
- `pm_trading/run_paper_today.py`, `paper_autobet.py` -- today's-games paper trader feeding
  the CLV ledger.

### Live data artifacts (gitignored `data/frontend/`, observed 2026-06-18)
- `clv_ledger.jsonl` -- 38 lines (24 open, 14 settled; **0 settled rows carry a real CLV**).
- `paper_predictions.jsonl` -- 1542 lines.
- `improve_ledger.jsonl` -- 48 lines, **all 48 verdict=INSUFFICIENT_DATA**.
- `prop_ledger.jsonl` -- ~1MB.
- `prop_line_history.jsonl` -- **1 line** (closing-line capture essentially unstarted).
- `data/domains/soccer/prop_calibration.json` -- per-stat OOS BSS cache, overall n=6620,
  662/stat (Saves bss +0.34, Fouls +0.034; Cards -0.108, Assists -0.074, etc.).

---

## 2. HOW IT WORKS -- data flow + key algorithms

### 2a. The eval-gate (offline, < 60s, no network)
`run_gate.main()` (run_gate.py:188) picks the predictor: `offline_predict_fn` for
`--golden`, or `_load_model_predictor()` (proof_nba.ml_accuracy) for a real `--corpus`
(which raises offline -> fail-closed). For each corpus in `CORPORA =
["nba_2023_24","nba_2024_25"]`:

1. `evaluate_corpus(name, predict_fn, states)` (run_gate.py:83) calls
   `walk_forward(states, predict_fn, select_inside=True)`.
2. `walk_forward` (walkforward.py:52) sorts by `state_ts`, and for each test state builds
   the train set from strictly-earlier states, dropping same-matchup within
   `EMBARGO_DAYS=3` and same-team within `PURGE_HOURS=48`, then calls `assert_vintage`
   (walkforward.py:36) which asserts every `feature_avail[f] < state_ts` (the LEAK guard),
   then `predict_fn(train, test, select_inside)` with a `0<=p<=1` assertion.
3. Scoring: `bm,bc = brier(pm,y),brier(pc,y)`; `bss = brier_skill_score(pm,pc,y)`
   (scoring.py:93, `1 - Brier_model/Brier_ref`, ref = devigged close).
4. `d = (pc-y)**2 - (pm-y)**2` (close loss - model loss, >0 = model better) ->
   `diebold_mariano(d, gid)` (dm_test.py:32). The DM SE uses a per-cluster deviation
   sum `(gsum @ gsum)/(n*n) * g/(g-1)` -- the cluster-robust fix (a naive i.i.d. SE runs
   ~3x too narrow; `test_dm_cluster_se_wider_than_naive` asserts clustering widens the SE).
5. Verdict `_verdict` (run_gate.py:74): BEATS_CLOSE only if `bss>0 AND dm.p<0.05 AND
   dm.n>=200`; else MATCHES_CLOSE if CI95 on the loss-diff overlaps 0; else BEHIND. All
   three are NON-blocking and honest.
6. Regression rule (THE BLOCKER, run_gate.py:107): `worsened = bm > base.brier_model +
   0.005` AND a DM test of per-game model-vs-baseline losses is significant -> `regressed`.
   `gate_exit_code` (run_gate.py:157) returns 1 on ANY regression, ANY leak, OR an empty
   measured set (fail-closed).

The golden fixture is SYNTHETIC: `gen_golden.py` draws `p_true = sigmoid(BETA.features)`,
BETA=(1.4,0.5,0.25), `outcome ~ Bernoulli(p_true)`, and
`devig_close_prob = p_true + N(0,0.03)` -- a near-oracle close, so the predictor CANNOT
beat it by construction. MATCHES_CLOSE / BSS<=0 is the designed honest verdict; baselines
are frozen from this exact path so the gate is non-regressing by construction on a clean run.

### 2b. Distributional metrics (MASTER_PLAN C7, scoring.py:143-191)
`crps_gaussian` (closed form Gneiting-Raftery), `crps_ensemble` (empirical, O(n log n) via
the sorted-order identity -- the possession sim's native output), `pinball_loss` (single
served interval bound). Tests prove CRPS->MAE as sigma->0, ensemble~=closed-form, pinball
asymmetry. These exist to grade continuous markets (totals/margins) and prop-interval
bounds, but are NOT yet wired into `run_gate` (binary BSS only) -- see gaps.

### 2c. Devig (shin.py)
`shin_devig(pi)` bisects z in [0,0.999999) so `sum_i p_i(z) == 1` with
`p_i(z)=(sqrt(z^2 + 4(1-z)pi_i^2/B)-z)/(2(1-z))`. This is the documented "fixed" Shin
(the older closed-form did not normalize to 1). `clv_ledger` and `prop_line_history`
reuse it via `odds_shop.devig_twoway` -- devig is never re-derived.

### 2d. The self-improvement ratchet (self_improve.py)
`improve_cycle(sport)` (self_improve.py:244):
1. `load_settled` pulls real (model_prob, outcome[, close]) rows from
   `clv_ledger.jsonl` settled twins + `paper_predictions.jsonl`, deduped by
   (matchup, ts, side), chronologically sorted.
2. `honest_readout` -- Brier/ECE/sharpness on real outcomes, + BSS-vs-close and
   %-beat-close where a devigged close exists.
3. If `< MIN_RECAL_GAMES (60)` -> verdict INSUFFICIENT_DATA, logged, no fabricated win.
4. Else build eval-gate states (`_to_states`, synthetic strictly-increasing clock,
   `feature_avail` stamped before `state_ts`), then score TWO predictors via the gate's
   own `walk_forward`: `_baseline_predict` (raw prob passthrough -- frozen today's model)
   and `_recal_predictor` (leak-free expanding isotonic from `walk_forward_recalibrate`).
5. No-regression rule mirrors the gate: `d_vs_base = base_loss - cand_loss`,
   `diebold_mariano(d_vs_base, gid)`, `regressed = worsened AND sig`. Verdict:
   SHIP (`d_brier > 0.005`, no regression/leak), HOLD (no meaningful gain), REJECT
   (regress or leak). Appended to `improve_ledger.jsonl`.

`pm_trading/auto_loop.run_once` (auto_loop.py:36) chains `run_paper_cycle ->
grade_open_bets -> improve_all -> grade_summary`, each guarded; `--forever` sleeps
`max(60, interval)` between cycles. This is the live never-stop loop referenced in MEMORY.

### 2e. CLV math + sign (clv_ledger.py:100)
`compute_clv(side, taken_decimal, close_home, close_away)`: devig the closing two-way ->
`fair_close`; `taken_p = 1/taken_decimal`; `clv_pct = (fair_close - taken_p)/taken_p*100`.
POSITIVE = you locked a price implying LOWER prob than the fair close = a better number.
This is the deliberate, correct sign (the repo has a documented "record_clv backwards"
gotcha that this module explicitly does not repeat).

### 2f. Tiered evidence (prop_tiering.py)
`classify(stat, calibration)` -> "proven" iff `bss >= 0.05 AND n >= 100`; "marginal" iff
`0 <= bss < 0.05`; "weak" iff `bss < 0`; "unmeasured" if absent. `apply_tier` promotes an
edge to `CALIBRATION_PROVEN` only when proven AND reliable AND ev_flag ok; otherwise
`MODEL_VIEW`. `calibration_rank_key` forces proven edges to outrank marginal/weak even if
a weak stat has bigger raw EV -- honesty-first ranking. This is the three-tier evidence
ladder: MODEL_VIEW (just a model number) -> CALIBRATION_PROVEN (OOS-calibrated) ->
[CLV-proven, the unbuilt top tier].

---

## 3. HOW IT IS USED -- callers / consumers

- **`run_gate --golden` / `run_all.py`** are human-run / CI gates. `skills` expose them:
  `eval-gate`, `calibration-report`, `cross-sport-benchmark`, `signal-audit` all front
  this core. The build-platform loop treats the gate as the keystone (per CLAUDE.md /
  MEMORY: "eval-gate keystone").
- **`self_improve.improve_all`** consumed by `pm_trading/auto_loop.py` (the `--forever`
  loop) and `reject_ledger.py`.
- **`clv_ledger`** consumed by `frontend/serve.py:252` (`clv_summary(load_ledger())`
  served as an API stat), `grade_paper.py`, `prop_line_history.py`, `prop_paper.py`,
  `self_improve.py`, `pm_trading/{auto_loop,paper_autobet,run_paper_today}.py`, and
  `scripts/gamenight_e2e_harness.py`.
- **`scoring`/`walkforward`/`dm_test`/`shin`** are reused broadly: `edge_engine/score.py`,
  `forward_capture/clv.py`, `market_coverage/calibrate.py`, `ledger/metrics.py`,
  `odds_shop.py`, `calibration_banner.py`, `calibration_record.py`,
  `pm_trading/edge_signal.py` and `strategies/model_vs_market.py`. The eval-gate math is
  genuinely the shared spine, not a stranded island.
- **`props_eval.write_calibration_cache`** writes `prop_calibration.json`, which
  `prop_tiering.load_calibration` reads to tier the live prop board (served on the front
  end :8098).

---

## 4. STRENGTHS -- what is genuinely solid

1. **Leak-freeness is enforced, not assumed.** `assert_vintage` plus purge+embargo plus
   `select_inside` recording, plus `validate_golden` regime-coverage + leak tests
   (`test_validate_golden_fires_on_leak`, `_on_coverage_gap`). The recalibrator is
   strictly expanding-window (event i uses only 0..i-1). The self-improve cycle re-runs
   the gate's OWN walk_forward over real states, so a future-timestamp injection fires the
   same assert.
2. **The cluster-robust DM test is the right test and is itself unit-tested** to be wider
   than the naive i.i.d. SE. This kills the most common fake-significance failure for
   correlated within-game states.
3. **Fail-closed + frozen-baseline regression gate.** The gate blocks on regression/leak/
   empty-set only -- never on "fails to beat the close", and an empty measured set FAILS.
   Two independent corpora; pre-registered tolerance (0.005 Brier) and a DM significance
   requirement before a regression blocks. This matches the repo's hard-won discipline
   (single-fold lifts are artifacts; >=2 corpora).
4. **The honesty contract is wired into the code, not just docs.** BSS<=0 = honest success;
   `CALIBRATION_NOTE` re-printed everywhere; `executed=False` invariant in every paper row;
   INSUFFICIENT_DATA instead of a fabricated win; the proxy-CLV is explicitly labelled
   `clv_is_proxy`. CRPS-collapse and ECE-collapse guards (sharpness/resolution pairing)
   prevent the "predict 0.5 everywhere and look calibrated" trap.
5. **The ratchet can only improve or hold.** SHIP requires a real, significant, leak-free
   Brier gain; otherwise HOLD. This is a genuinely monotone self-improvement design.
6. **Distributional scoring (CRPS/pinball) is correct and tested** -- ahead of where most
   hobby systems get; it is the right tool for the continuous markets the sim emits.
7. **Append-only + idempotent ledgers** (settle_key / intrinsic identity) make the track
   record tamper-evident and re-runnable.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS -- brutally honest

1. **The gate has NEVER run against real data offline.** `--golden` runs only the SYNTHETIC
   fixture with a deterministic toy ridge predictor; `--corpus` raises FileNotFoundError
   offline and `_load_model_predictor` (proof_nba.ml_accuracy) is "documented, NOT exercised
   offline" (run_gate.py:64). So the production model's calibration is NOT what the gate
   green-lights -- the gate proves the *harness* is non-regressing, not that the real model
   is good. The baselines are explicitly `_synthetic: true`.
2. **The self-improve ratchet has produced ZERO ships -- and literally cannot yet.**
   `improve_ledger.jsonl` is 48/48 INSUFFICIENT_DATA. Real settled team games per sport are
   far below `MIN_RECAL_GAMES=60` (NBA off-season; mlb n=12, soccer/tennis n=0 in the last
   cycle). The ratchet is built and correct but has never engaged on real data. This is
   honest, but it means the "+8% claim measured on paper" is entirely prospective.
3. **CLV is effectively not being captured.** Of 14 settled team bets, **0 carry a real
   CLV** -- no closing line is stored, and the last-price proxy path also has nothing
   (`with any close/proxy price = 0`). `prop_line_history.jsonl` has **1 line**: the
   closing-line time series the true-CLV design depends on is essentially empty. So the
   "honest yardstick" (CLV) currently has no signal. `frontend/serve.py` will report
   `pct_beat_close=None`.
4. **The "CLV-proven" top tier does not exist.** prop_tiering tops out at
   CALIBRATION_PROVEN; there is no code path that promotes an edge once it accumulates
   positive settled CLV. The three-tier ladder is really two tiers in practice.
5. **Calibration "proven" rests on thin / quasi-in-sample data.** `prop_calibration.json`
   reports n=662 per stat (overall 6620) -- but the module docstrings still say "24 World
   Cup matches", and the per-match walk-forward re-scores the SAME small tournament many
   player-rows over (662 player-stat predictions != 662 independent matches). `recal_eval`
   itself warns the TEST set is small and "helps ECE but not Brier" is a valid answer. The
   ONLY stat that clears the proven bar is Saves (bss +0.34) -- plausibly a structural
   artifact (goalkeeper saves track shot volume, near-deterministic given minutes), and
   Fouls/Fouls Drawn (+0.03) are marginal. Treat "proven" as suggestive, not bankable.
6. **DM significance is rarely reachable.** BEATS_CLOSE / SHIP both require `dm.n >= 200`.
   With <60 settled games per sport, the significance test is structurally unsatisfiable in
   the near term; the system can HOLD forever without ever proving a real lift.
7. **`crps_gaussian/crps_ensemble/pinball_loss` are stranded w.r.t. the gate.** They are
   built and tested but `run_gate` only scores binary BSS/Brier. The continuous-market and
   prop-interval calibration is never gated end-to-end. Same for `ingame_blend.py` /
   `freshness_schema.py` -- adjacent, tested, but not in the `run_gate` verdict path.
8. **Settlement matching is fuzzy-string and feed-dependent.** `grade_paper._team_match`
   relies on token-subset matching of ESPN names/abbrs; a mismatch silently leaves a bet
   pending (counted, not errored). One bad/renamed feed entry => a bet never settles and
   never enters the ratchet.
9. **`self_improve` recalibrates a SINGLE scalar prob passthrough.** The "candidate" is just
   isotonic-on-raw-prob; it cannot discover new signal, only re-map an existing one. If the
   raw model is already well-calibrated (the expected case vs an efficient market), the
   ratchet will correctly HOLD forever -- which is honest but means "self-improving" mostly
   means "self-verifying-it-cannot-improve".
10. **Proxy-CLV bias risk.** When a true close is absent, grade uses the last-observed price
    as the close (labelled `clv_is_proxy=True`). The last logged price is often the SAME
    price the bet was taken at -> CLV ~ 0 by construction, neither honest-positive nor
    honest-negative, just uninformative. Currently moot because nothing is logged at all.

---

## 6. PLAN TO GET BETTER -- prioritized

### Quick wins (days)
1. **Actually capture closing lines.** Run `prop_loop`/`pm_trading` cadence up to kickoff so
   `prop_line_history.jsonl` and the team-bet close fields accrue. Without this every CLV
   metric is `None`. Highest leverage, lowest effort -- it is a scheduling/ops fix, the code
   exists. (Approach: a cron/`schedule` agent ticking every ~10-15 min over a live
   tournament/season window; verify `log_board_lines` is reached -- today it has 1 row.)
2. **Fix the stale docstrings vs reality** (props_eval / prop_tiering say "24 matches";
   cache shows n=662/stat). Re-state what n actually counts (player-stat predictions over
   a small match set), so "proven" is not over-read. Documentation-only, prevents a false
   claim.
3. **Distinguish "real CLV" from "proxy CLV" in `clv_summary`/serve output.** Report
   `n_with_real_close` separately so the front end cannot imply CLV evidence it does not
   have. Cheap, removes a foot-gun.
4. **Add a min-N gate to the "proven" tier per independent EVENT, not per player-row.**
   Require `proven` to also clear an independent-match count, not just 662 correlated rows.

### Medium (weeks)
5. **Wire CRPS/pinball into `run_gate` as a second scoreboard block** for continuous markets
   (totals/margins) and served prop intervals, with their own frozen baselines and
   regression rule. The metrics + tests already exist; this just extends `evaluate_corpus`.
6. **Run the gate against a real frozen corpus offline.** Snapshot a real
   `data/domains/<sport>` slice, freeze a REAL (non-`_synthetic`) baseline, and have
   `--corpus` actually execute proof_nba.ml_accuracy in CI on a small sample. This converts
   the gate from "harness is non-regressing" to "the real model is non-regressing".
7. **Build the CLV-proven top tier in prop_tiering.** Once N settled bets with real positive
   CLV (cluster-robust CI > 0) accumulate for a stat/market, promote to CLV_PROVEN above
   CALIBRATION_PROVEN. Reuse `diebold_mariano` on per-bet CLV clustered by match.
8. **Robust settlement matching.** Replace token-subset team matching with the same
   resolver infra used elsewhere (id-based join via a team map) and surface unmatched bets
   as an explicit health metric, not silent pending.

### Bigger bets (months / data-bound)
9. **Reach `dm.n >= 200` per sport by forward-accruing real settled games** across full
   seasons (the only way the ratchet ever leaves HOLD/INSUFFICIENT_DATA). This is
   fundamentally a time + cadence problem, not a code problem.
10. **Give the ratchet more than isotonic-on-scalar.** Allow the candidate to be a small
    set of pre-registered, leak-free recal/blend transforms (e.g. temperature + isotonic +
    a single in-game freshness lever) and let the gate pick the non-regressing winner. Keep
    it strictly gated so it can still only improve-or-hold.
11. **Adversarial / null-control harness in the gate.** Auto-run a shuffled-label and a
    future-shifted control each gate run; a SHIP that survives only because of leakage
    should fail the control. Codifies the repo's "single-fold lifts are artifacts" lesson.

---

## 7. HOW GOOD CAN IT GET -- honest ceiling

**As a proving / honesty machine: very good -- arguably already near-bulletproof in
design, just not in evidence.** The leak guard, cluster-robust DM, fail-closed regression
gate, frozen baselines, and the improve-or-hold ratchet are the correct primitives and are
unit-tested. With closing-line capture + a real-corpus baseline + the CRPS block + a CLV
top tier, this becomes a genuinely rigorous, self-verifying spine: every change must pass a
leak-free, cluster-robust, multi-corpus, distribution-aware, regression-gated check, and
every "win" must survive null controls and accumulate real CLV before it is labelled
proven. That is about as honest as a single-operator system can be.

**What limits it (and always will):**
- **Markets are efficient.** The realistic best on team-strength markets is MATCHES_CLOSE
  (BSS ~ 0, CLV ~ 0). The gate is explicitly designed so that is a SUCCESS, not a target to
  beat. No amount of machinery manufactures an edge that is not there; the honest ceiling on
  pregame is "indistinguishable from the devigged close."
- **The only credible lift is in-game freshness / conditioning**, and that lives in the
  in-game layer (area 05), not here -- this spine can only MEASURE it, gated, as
  calibration.
- **Statistical power is the binding constraint.** SHIP/BEATS need dm.n>=200 of
  *independent* settled outcomes per sport; that is a multi-season accrual problem. Until
  then the honest verdict ceiling is HOLD / INSUFFICIENT_DATA, which is exactly what the
  ledgers show today (48/48 INSUFFICIENT_DATA).
- **"Proven" calibration on thin, correlated samples (the Saves +0.34 case)** can never be
  more than suggestive until independent-event N is large. The system is honest about this;
  the ceiling is "well-calibrated and proven not to be worse than the close," never "edge."

Bottom line: the proving spine is the most rigorous and honest part of the project and the
design ceiling is high, but its *demonstrated* output today is correctly null (no ships, no
real CLV) -- the gap to a "bulletproof, self-improving proving system" is dominated by
**closing-line capture + real-corpus gating + months of forward accrual**, not by missing
algorithms.
