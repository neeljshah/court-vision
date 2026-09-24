# S417 FIX 1m - AMENDMENT 12
Status: FIX 1m candidate, uncommitted, for orchestrator review.
Local: C:/Users/neelj/nba-harness-h72; Python 3.10.0.
Attempt-g HEAD: 5a1d8ed0039b69290290f99b176f34afc0d4c742; attempt-i HEAD/master: 231eef303b00485ac083748b1e710010c6492789.
## Binding before-condition quotations
Quoted from starting HEAD. Master advanced during the run; final master is b66352c696402b14a44a1fc3a8d9852c0541ec98. Final HEAD/master source equality fails for nba_four_arm_trial.py; this upstream change is not the lane's diff. scripts/platformkit/ingame/baseline_four_arm_period.py:38,123-139,149-161,163,190-196,198-203,217-221
> def _losses(row: dict, arms: str = "ABCD") -> dict:
> def _primary(values: dict, periods: tuple) -> dict:
>     games = sorted(values)
>     ng, npers = len(games), len(periods)
>     matrix = np.array([[values[g].get(p, np.nan) for p in periods]
>                        for g in games], dtype=float).reshape(ng, npers)
>     support = np.isfinite(matrix).sum(axis=0)
>     point = _period_point(matrix)
>     samples, discarded = [], 0
>     for pick in _bootstrap_draws(ng) if ng else ():
>         sample = _period_point(matrix[pick])
>         if sample is None:
>             discarded += 1
>         else:
>             samples.append(sample)
>     interval = [float(v) for v in np.percentile(samples, [2.5, 97.5])] if samples else None
>     insufficient = point is None or discarded > 20
>     status = verdict(*interval, ng) if interval and not insufficient else "UNDERPOWERED"
>     return dict(point=point, ci95=interval,
>                 verdict="SINGLE-WINDOW" if status == "AHEAD" else status,
>                 reason="period_support_insufficient" if insufficient else None,
>                 n_boot_retained=len(samples), n_boot_discarded=discarded,
>                 per_period={p: dict(point=float(np.nanmean(matrix[:, i])) if support[i] else None,
>                                     n_games=int(support[i]), n_missing_games=ng - int(support[i]))
>                             for i, p in enumerate(periods)},
>                 leave_one_game_out_range=[min(retained), max(retained)] if retained else None,
>                 n_leave_one_out_discarded=len(leave) - len(retained),
>                 largest_absolute_share={"game_id": share},
>                 concentration_pass=share is not None and share <= 0.5,
>                 game_statistics=contributions, game_period_means=values,
>                 game_first=dict(secondary, label="SECONDARY"))
> def _stratified_cells(rows: list[dict], periods: tuple = PERIODS, arms: str = "ABCD") -> dict:
>         for arm in arms[1:]:
>             values = {}
>             for game in sorted(grouped):
>                 values[game] = {p: math.fsum(r[arm][metric] - r["A"][metric] for r in ticks)
>                                 / len(ticks) for p, ticks in sorted(grouped[game].items())}
>             result["comparisons"][f"{arm}_{metric}"] = _primary(values, periods)
>     return result
> def stratified_cells(rows: list[dict], periods: tuple = PERIODS) -> dict:
>     """Keep full A/B/C cells and recompute all four arms on the saved D subset."""
>     if not isinstance(rows, list) or not any(isinstance(r, dict) and "d_subset" in r for r in rows):
>         return _stratified_cells(rows, periods)
>     result = _stratified_cells(rows, periods, "ABC")
>     paired, reasons = [], Counter()
>             paired.append(subset)
>     if reasons:
>         raise Refused({"n_input": len(rows), "n_refused": sum(reasons.values())}, reasons)
>     result["d_subset"] = _stratified_cells(paired, periods)
>     return result
scripts/platformkit/ingame/nba_four_arm_trial.py:21-33,41-51
> def _label(value: object, descriptive: bool = False) -> object:
>     if isinstance(value, list):
>         return [_label(v, descriptive) for v in value]
>     if not isinstance(value, dict):
>         return value
>     result = {k: _label(v, descriptive or k == "d_subset" or k.startswith("D_"))
>               for k, v in value.items()}
>     if any(k in result for k in ("verdict", "comparisons", "populations", "d_subset")):
>         result["label"] = "SECONDARY DESCRIPTIVE" if descriptive else "SECONDARY"
>     if descriptive and "verdict" in result:
>         result["interval_verdict"] = result["verdict"]
>         result["verdict"] = "DESCRIPTIVE"
>     return result
> def _primary(cells: dict) -> dict:
>     comparisons = cells["comparisons"]
>     brier = _cell(comparisons["C_brier"])
>     return dict(label="PRIMARY", comparison="period-first C-minus-A",
>                 verdict=brier["verdict"], brier=brier,
>                 logloss=_cell(comparisons["C_logloss"], label="SECONDARY"),
>                 **{k: v for k, v in cells.items() if k not in ("comparisons", "d_subset")},
>                 secondaries=_label(dict(comparisons={
>                     k: v for k, v in comparisons.items() if k != "C_brier"},
>                     game_first={k: v["game_first"] for k, v in comparisons.items()},
>                     d_subset=cells.get("d_subset", {}))))
scripts/platformkit/ingame/baseline_four_arm.py:110-126,141-144
>         record['A'] = test['features']['raw_mid']
>         record['warmup'] = not train
>         for arm, names in [('B', ['mid']), ('C', ['mid', *FEATURES[sport]])]:
>             record[arm] = logistic(train, test, names) if train else record['A']
>         paired = record.get('d_subset', record)
>         if paired is not None:
>             d_train = [s for s in train if s['features']['model'] is not None]
>             paired.update(A=record['A'], warmup=not d_train,
>                           train_games=sorted({s['game_id'] for s in d_train}),
>                           train_n_games=len({s['game_id'] for s in d_train}),
>                           train_n_ticks=len(d_train))
>             for arm, names in [('B', ['mid']), ('C', ['mid', *FEATURES[sport]]),
>                                ('D', ['mid', *FEATURES[sport], 'model'])]:
>                 paired[arm] = (record[arm] if arm != 'D' and len(d_train) == len(train)
>                                else logistic(d_train, test, names) if d_train else record['A'])
>         record['d_eligible'] = paired is not None
>         record['D'] = paired['D'] if paired is not None else None
>             target['paired_losses'] = {arm: ({
>                 'brier': float(gate.brier(target[arm], row['outcome'])),
>                 'logloss': float(gate.logloss(target[arm], row['outcome']))}
>                 if target[arm] is not None else None) for arm in 'ABCD'}
scripts/platformkit/ingame/baseline_four_arm_features.py:12-18
> FEATURES = {
>     'mlb': ('score_diff', 'inning', 'half', 'outs',
>             *(f'base_{value}' for value in range(1, 8))),
>     'soccer': ('score_diff', 'minute', 'home_red_cards', 'away_red_cards',
>                'home_red_present', 'away_red_present'),
>     'nba': ('score_diff', 'quarter', 'seconds_remaining'),
> }
scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:24,84-87
> N_MIN_GAMES = 30
> def verdict(lo, hi, n_games, n_min=N_MIN_GAMES):
>     if n_games < n_min or (lo <= 0 <= hi):
>         return 'UNDERPOWERED'
>     return 'BEHIND' if lo > 0 else 'AHEAD'
docs/evidence/tracking/specs/S405_spec.md:36-49
> AMENDMENT 1 (2026-09-22 19:0xZ; binding; from the codex sol round-1 verdict and the astra round-1 critique on the terra build). (a) THE CONTRAST MATCHES THE REPORTED CELLS: the build computed D_minus_C through the tick-weighted helper while the reported D_* and C_* subset cells use period weighting over the SAVED paired_losses, so the contrast point (0.07285714285714283) did not equal reported D minus reported subset-C (0.07999999999999996) and its interval differed. RULING: D_minus_C_<metric> is computed with EXACTLY the machinery, weighting and saved paired_losses the reported D_* and C_* subset cells use, so that D_minus_C.point equals D.point minus C.point on the subset to 1e-12 and the interval is the paired-delta interval under the same bootstrap; a test asserts that equality on the fixture. (b) ORDER INDEPENDENCE: the scored rows are canonically sorted by (game_id, phase, key) before any cell is computed; reversing the fixture yields byte-identical diagnostics (leave_one_game_out_range, largest_absolute_share). (c) FINITENESS: a non-numeric, boolean, non-finite or out-of-range C or D probability in the subset refuses (exit 3, reason) before any cell; test with D = inf. (d) LOSS CONSISTENCY: a saved paired_loss that does not equal the loss recomputed from the row's probability and outcome (to 1e-12) refuses inconsistent_paired_loss -- the contrast never silently uses one while the reported cell uses the other. (e) ONE-GAME AND EMPTY SUBSETS: scored_keys lists exactly the rows scored (never emptied by an underpowered verdict); the contrast cell carries verdict UNDERPOWERED with finite or null estimates and no exception; a repeat serialization of the same input is byte-identical (a permanent assertion).
docs/evidence/tracking/specs/S395_spec.md:71-77
> AMENDMENT 3 (2026-09-22 19:0xZ; binding; from fix 1d against the LANDED S394 runner shape). MEASURED by the fix agent on a fixture built through trial._primary(stratified_cells(primary_rows)): the landed S394 runner emits NO D_minus_C_<metric> contrast and NO d_subset.scored_keys, both named in this row's CHANGE clause. RULING: the auditor audits each when present and never invents either; requiring them would fail every real S394 output. Their absence is recorded in the audit report as a producer gap (check status NOT_AUDITABLE with reason producer_field_absent, never PASS) and in the memo's NOT VERIFIED list; closing it is an additive S394 follow-up row (allocated by the orchestrator, not this row). The auditor's release verdict on the landed shape is therefore reached with C.means NOT_AUDITABLE and those two checks NOT_AUDITABLE, and the seal / trial memo must say so in words.
docs/direction/nba_prereg_amendments_2026-09-22.md:66-128
> ### (a) C-minus-B as the PRIMARY period-stratified contrast
> 
> Replace draft lines 14-15 with:
> 
>     PRIMARY: period-stratified C-minus-B Brier on the declared primary population. B is the recalibrated mid (intercept + logit(mid)); C is the market anchor plus the declared state vector; C-minus-B is therefore the state residual on top of a recalibrated price, and it is the only quantity this trial claims. C-minus-A confounds recalibration with state and is DEMOTED TO SECONDARY, reported beside B-minus-A, D-minus-A and D-minus-C. No secondary can replace the primary and no direction is selected after outcomes.
> 
> Replace draft line 119 (keeping :120-126 unchanged) with:
> 
>     PRIMARY METRIC: PERIOD-STRATIFIED C-minus-B Brier, equal 1/4 weights over Q1-Q4. The contrast is computed with EXACTLY the machinery, weighting and saved paired_losses the reported C and B period cells use, over the same scored rows, folds and periods, so that the primary point equals the reported C point minus the reported B point to 1e-12; the interval is the paired-delta interval under the same whole-game bootstrap (2,000 draws, seed 13, 95 percent), never a difference of two separately drawn intervals. Scored rows are canonically sorted by (game_id, phase, key) before any cell is computed, so every diagnostic is order-independent. A non-numeric, boolean, non-finite or out-of-(0,1) B or C probability refuses the batch with a counted reason before any cell; a saved paired loss that does not equal the loss recomputed from the row's probability and outcome to 1e-12 refuses as inconsistent_paired_loss. C-minus-A is computed the same way and labelled SECONDARY.
> 
> Verdict rule for the primary (append after draft line 170):
> 
>     The primary verdict applies the landed rule to the primary interval and the primary game count: fewer than 30 scored games, or an interval containing zero, is UNDERPOWERED; a lower bound above zero is BEHIND; an interval wholly below zero is printed SINGLE-WINDOW. AHEAD is never printed by this trial: it requires a second independent corpus, which this archive is not. Concentration ratio <= 0.5 and the period-support rule below also bind the primary; failing either leaves the cell UNDERPOWERED with its named reason.
> 
> ### (b) B_lag -- the lagged-mid control arm (standing secondary)
> 
> Append to the arms section (after draft line 26):
> 
>     B_lag: logistic regression with intercept and logit(mid_lag) only, where mid_lag is the market probability of the PREVIOUS eligible tick of the same game in the same population, strictly earlier in timestamp order, under the identical eligibility and duplicate-key policy. A tick with no previous eligible tick in its game (the game's first eligible tick) is ineligible for B_lag ONLY, counted as no_prior_tick_for_b_lag; mid_lag is never imputed, never back-filled with the contemporaneous mid and never carried across games. B_lag is fitted with the same fixed ridge, step and tolerance as the other arms and on training rows only.
> 
> Append to the reporting section (after draft line 131):
> 
>     STANDING CONTROL (SECONDARY, never promoted): C-minus-B_lag and B-minus-B_lag, period-stratified on the B_lag paired subset, with A, B and C RECOMPUTED on that subset using identical keys, folds, training populations and weights -- the same paired-subset discipline arm D receives. Interpretation, declared before any read: a primary C-minus-B interval wholly below zero that does not also hold as a C-minus-B_lag interval wholly below zero on the B_lag subset is labelled LATENCY-EXPLAINED and carries no calibration claim; the residual must exceed what a one-receipt-stale price already explains. The control is reported whatever the primary shows, including when the primary is UNDERPOWERED, and its own bars are the primary's bars.
> 
## Candidate and construct measurements
baseline_four_arm_features.py:217,230 adds prior eligible mid and training-only lag subset; FEATURES unchanged. baseline_four_arm.py:50,194 adds mid_lag, B_lag, b_lag_subset, paired_losses.B_lag and no_prior_tick_for_b_lag. baseline_four_arm_period.py:30,158,191 adds validation and reference-arm cells through the unchanged seed-13 machinery. nba_four_arm_trial.py:41 changes the comparison string and which cells fill brier/logloss; these are the two intended runner changes. C_minus_A aliases and original C cells remain SECONDARY; B_lag remains SECONDARY; D keeps DESCRIPTIVE plus interval_verdict. Blank-line removal in scorer/period keeps the size rail without changing existing computations. test_nba_four_arm_primary_contrast.py:1 checks frozen HEAD values, paired draws, reversal, refusals, lag and one-game cases. Supported construct: 19 input ticks, 14 scored ticks, 2 scored games; lag subset 12 scored ticks; 3 first ticks counted. First mid_lag and paired_losses.B_lag are null; next mid_lag=0.5 within each game. No cross-game carry. Worked new comparison keys below are point [interval], Brier then logloss; all UNDERPOWERED. C_minus_B: 0.044117795464649744 [0,0.08823559092929949]; 0.33336508372190177 [0,0.6667301674438035]. D-subset D_minus_B and C_minus_B: 0.040255317336949994 [0.040255317336949994,0.09263376782335418]; 0.33366586158939926 [0.33366586158939926,0.6916606598478059]. B_lag versus A: 0.3989661140681192 [0.05839508746743732,0.739537140668801]; 2.3372902869858967 [0.11728311274107106,4.557297461230722]. Lag-subset C_minus_B and C_minus_Blag: 0.038125239058035824 [0,0.07625047811607165]; 0.36073555306388533 [0,0.7214711061277707]. B_minus_Blag: 0 [0,0] for both metrics. C_minus_A aliases: 0.4375476642258845; 2.6594691960394674. Full and lag cells retain 2000 draws, discard 0; D subset retains 1489, discards 511. Both metric point equalities pass at absolute tolerance 1e-12; independent paired-delta intervals pass. Reversal is byte-identical; invalid B and inconsistent losses refuse before cells; a one-game cell is UNDERPOWERED.
## Landed test edit inventory, enumerated before editing
Exact-set scan covered test_baseline_four_arm*.py and test_nba_four_arm_trial*.py for == set( and == {. Starting-line matches: baseline:250,269,292; eligibility:77,80,125,126,130,137,167,205,248,264,267; nba:90,184,278,294; period:29,30,31,97,143,175,178,210,268,277; trial:67,252,272,273. test_baseline_four_arm_nba.py:90 before `set(r['paired_losses']) == set('ABCD')`; after `set(r['paired_losses']) >= set('ABCD')`. test_baseline_four_arm_period.py:277 before `set(result['comparisons']) == {f'{a}_{m}' for a in 'BC' for m in period.METRICS}`; after same expression with >=.
Other exact-set matches unchanged; new names are checked separately in the new test file.
Trial fixture constants inventoried: lines 63,65,66,67,68,75,78,79,80,83,85,86,94,272,273,274,299.
Only trial edits below occur; all other assertions, including the period/tick inequality, remain unchanged.
trial:37 before `for t in range(1, 8 if i == 2 else 5)]`; after `for t in range(1, 8 if i == 2 else 6 if i == 1 else 5)]`.
Added row: game_id=g1, ts=2026-01-06T12:05:00+00:00, close_ts=2026-01-06T20:00:00+00:00, outcome=1, market_prob=0.5, model_prob=0.6,
state_summary=home_score=5,away_score=1,quarter=4,seconds_remaining=60.
trial:63 before `len(paired) == 15 ... d_eligible ... == 14`; after `len(paired) == 16 ... d_eligible ... == 15`; warmup stays 4.
trial:65 before `primary["n_ticks"] == 11`; after `primary["n_ticks"] == 12`; games stays 2.
trial:66 before `primary["n_input"] == 15`; after `primary["n_input"] == 16`; warmup stays 4.
trial:75 before `r["paired_losses"]["C"][metric] - r["paired_losses"]["A"][metric]`; after reference ["B"]; :78 equality to own arithmetic stays.
trial:new79 asserts C_minus_A secondary equals original C secondary; the new frozen-source test proves its original value.
trial:83 (now84) before `d["n_ticks"] == 10`; after `d["n_ticks"] == 11`; warmup stays 4.
trial:274 (now275) before `result["primary"]["n_warmup"] == 4`; after `result["primary"]["n_warmup"] == 5` for g1/g2-only population.
Original C-minus-B period/tick means: Brier 7.632783294297951e-17 / 2.220446049250313e-16; logloss 1.5265566588595902e-16 / 4.440892098500626e-16.
Extended means: Brier 0.038125239058035824 / 0.14415557365271622; logloss 0.36073555306388533 / 1.047306514317645.
No golden fixture regenerated. Guards, eligibility, gate and other landed tests remain byte-identical.
## ATTEMPT i
Local files only; interpreter Python 3.10.0. HEAD/master merge supplied by orchestrator. Before: S405 8 failed, 46 passed in 40.06s; powered construct refuses 150/150. Defect: period.py:51 checked the internally aliased A loss against A probability. S405 runner:97-99 aliases C losses as A for its AD projection after _checked_rows. Fix: skip redundant probability/consistency checks only for that AD projection; period.py:181 additionally requires B before adding a B-referenced comparison. Original rows still receive S405's all-arm/both-metric check unchanged; lag losses were checked only on rows carrying the lag subset (superseded by AMENDMENT 8). No B_lag assumption caused this refusal.
S405 assertion inventory BEFORE editing (test_nba_four_arm_trial_contrast.py):
- :119 before `assert _bytes(old) == _bytes(landed_output)`; after
  `assert _bytes(s417_golden(old, landed_output)) == _bytes(landed_output)`.
- :184 before `assert _bytes(after["brier"]) == _bytes(landed_output["brier"])`; after
  `assert _bytes(after["brier"]) == _bytes(before["brier"])` and
  `assert _bytes(trial._cell(after["secondaries"]["comparisons"]["C_minus_A_brier"])) == _bytes(dict(landed_output["brier"], label="SECONDARY"))`.
- :269 before `assert payload.encode("ascii") == expected[name].encode("ascii"), name`; after
  `assert (payload if name not in ("primary.json", "trial_summary.json", "return") else`
  `json.dumps(s417_golden(json.loads(payload), json.loads(expected[name])), **({"separators": (",", ":")} if name == "return" else {"indent": 2})) + ("" if name == "return" else "\n")).encode("ascii") == expected[name].encode("ascii"), name`.
The helper verifies C-minus-B identity and both C-minus-A aliases before restoring the golden primary for byte comparison; explicit additive key sets only are removed. The frozen golden predates S405 and S417: its comparisons contain B_brier, B_logloss, C_logloss only, so S417's C_brier / C_minus_B_* / D_minus_B_* keys also require explicit projection as authorized by CHANGE 1 and AMENDMENTS 1-3. No golden bytes or remaining S405 assertions will be changed.
Implementation detail for the inventory: the two golden assertions invoke s417_golden via `__import__("tests.platformkit.ingame.test_nba_four_arm_primary_contrast", fromlist=["s417_golden"]).s417_golden`; :184 appends the alias assertion on the same line. No imports or other S405 lines change.
AMENDMENT 6 before: auditor :68 required `set(row['paired_losses']) == set('ABCD')`; after: `set('ABCD') <= set(row['paired_losses']) <= set('ABCD') | {'B_lag'}`.
The probability range loop covers present B_lag; its saved loss must be null iff the probability is null, otherwise both metrics reconstruct via losses()/same(). All other auditor checks preserve behaviour; compacted imports/statements hold 300 LOC. The landed auditor test had no exact-key assertion to replace; a superset assertion was added at :53. New constructs cover present/absent and stale/null/invalid B_lag.
S402's real audit ran before B_lag existed; orchestrator MUST re-run after S417 lands.
Attempt-i construct stdout: S405 n=150 games=30; both D-minus-C cells DESCRIPTIVE, interval_verdict BEHIND.
AUDIT before B_lag FAIL; before without B_lag PASS; after B_lag PASS; after without B_lag PASS, all_verdicts_identical=True; stale B_lag FAIL.
S405 checked_rows unchanged=True; S405 contrast block unchanged=True; changed test lines=[119,184,269].
## FIX 1j - AMENDMENT 8
Local files only, Python 3.10.0 (repo default Python 3.10); retained staged AND unstaged candidate is the base. Implemented exactly: CHANGE 1 reference-arm cells; CHANGE 2 previous eligible mid; CHANGE 3 lag model/subset/count; CHANGE 4 C-minus-B primary and C-minus-A aliases, standing lag secondary, descriptive D; CHANGE 5 construct checks. Implemented allowances: AMENDMENT 1(a)-(d), AMENDMENTS 2-5 test/fixture changes, AMENDMENT 6 auditor extension and S405 preservation, AMENDMENT 7(a)-(b), and AMENDMENT 8(a)-(c). CHANGE 6 memo completion claims are narrowed here.
AMENDMENT 1(e), primary-auditor reconstruction, remains a follow-up; no claim that all draft amendments or seal blockers are closed.
AMENDMENT 8(a): inclusive A-D endpoints restored in period._losses; both-metric consistency retained. Pinned against git show 32c9915f9 period AND runner: all four arms x both endpoints x g1:1/g2:1 (both outcomes). The first row's probability and both losses change in the full row AND D subset; no B_lag is added. Existing strict B_lag bounds remain; A-D accept zero and one. Internal AD loss projection remains unchanged.
AMENDMENT 8(b): _lag_rows validates carried probability/loss before subset checks or any cell computation. Invalid probabilities use invalid_probability:B_lag; missing/inconsistent losses use inconsistent_paired_loss arm=B_lag. Missing required subset metadata uses missing_b_lag_subset; n_refused counts unique rows even with multiple reasons. Tests pin NaN, both infinities, outside range, booleans, strings, missing/null/empty losses, both metrics, whole invalid loss mappings, null/valid carried probabilities without metadata, and absent D metadata. Invalid periods retain their counted refusal. Existing valid lag values and subset pairing remain unchanged.
AMENDMENT 8(c): LATENCY-EXPLAINED NOT implemented; follow-up row for orchestrator. nba_four_arm_trial.py:80 selects the primary independently; :87 only copies the lag control into secondaries. findstr /n /c:LATENCY-EXPLAINED across the five owned producer files: zero matches, exit 1, empty stdout. A pinned test checks both producer source and serialized construct output; the label is never emitted.
Before/after Python one-liner stdout (construct helpers only; before = retained attempt i):
A=0.0 Refused {'invalid_probability:A': 1}
A=0.0 accepted n_ticks=9
B_lag=NaN accepted n_ticks=12 lag_report_present False
B_lag=NaN Refused {'invalid_probability:B_lag': 1, 'missing_b_lag_subset': 12} n_refused=12
B_lag missing loss Refused {'inconsistent_paired_loss arm=B_lag': 1, 'missing_b_lag_subset': 12}
B_lag inconsistent loss Refused {'inconsistent_paired_loss arm=B_lag': 1, 'missing_b_lag_subset': 12}
memo_before: Draft amendments (a)-(b) implemented in constructs; items 9-10 ready for verifier, item 11 still needs primary-auditor reconstruction.
memo_after: LATENCY-EXPLAINED NOT implemented; follow-up row for orchestrator.
Reproduction A body (python -B -c exec(bytes.fromhex(<hex encoding of this body>))):
"from tests.platformkit.ingame.test_nba_four_arm_trial_contrast import primary_rows\nfrom scripts.platformkit.ingame import nba_four_arm_trial as t\nrows=primary_rows(); r=next(r for r in rows if not r['warmup'])\nfor target in (r,r['d_subset']):\n target['A']=0.0; target['paired_losses']['A']={m:float(getattr(t.scorer.gate,m)(0.0,target['outcome'])) for m in t.period.METRICS}\ntry:\n c=t.stratified_cells(rows); print('A=0.0 accepted n_ticks='+str(c['n_ticks']))\nexcept t.period.Refused as e: print('A=0.0 Refused '+str(e.reasons))\n"
Reproduction B body (same one-liner transport; every b_lag_subset removed, saved loss kept):
"from tests.platformkit.ingame.test_nba_four_arm_primary_contrast import source_rows\nfrom scripts.platformkit.ingame import nba_four_arm_trial as t\nrows=t.scorer.predict_rows(source_rows(),'nba_checkpoints_r1')\nfor r in rows: r.pop('b_lag_subset')\nnext(r for r in rows if not r['warmup'] and r['B_lag'] is not None)['B_lag']=float('nan')\ntry:\n c=t.stratified_cells(rows); print('B_lag=NaN accepted n_ticks='+str(c['n_ticks'])+' lag_report_present '+str('b_lag_subset' in c))\nexcept t.period.Refused as e: print('B_lag=NaN Refused '+str(e.reasons)+' n_refused='+str(e.counts['n_refused']))\n"
Fresh unchanged construct: S417 input=19 scored=14 lag=12 first=3.
brier C_minus_B=0.044117795464649744 equality_1e-12=True
logloss C_minus_B=0.33336508372190177 equality_1e-12=True
reversal_byte_identical=True primary=period-first C-minus-B B_lag=SECONDARY D=DESCRIPTIVE
Only period module, new primary contrast tests and this memo changed in FIX 1j; nine other owned file hashes unchanged.
Guards and all unowned landed files have no HEAD diff; S405 test edits remain exactly at original lines 119/184/269.
FIX 1j historical verification: eight single-file runs passed; three CLI helps exited 0; contract preflight FAIL=0.
## FIX 1k - AMENDMENTS 9 AND 10
Local file-only continuation of FIX 1j; Python 3.10.0 at C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe.
AMENDMENT 9: validated lag cells attach independently before the no-D return; the entire lag block stays byte-identical, including both contrasts, both metrics and subset counts. First-tick exclusions remain three.
AMENDMENT 10: invalid_b_lag_membership refuses a present subset with null B_lag probability/loss before _population can exclude warm-up rows. The existing invalid_absent_b_lag refuses the reverse contradiction.
Both-order regressions cover probability, loss, both nulls, and absent subset with scored, subset-warmup and full-warmup rows; _population and _primary are forbidden during refusal.
Existing primary test statements were compacted with AST equivalence asserted before adding the regressions; all existing checks remain.
Before (retained FIX 1j), exact Python one-liner stdout:
A9 n_ticks=12 b_lag_subset=False byte_identical=False
A10 reverse=False accepted lag_ticks=12->11 brier=0.038125239058035824->0.029399408745696944 full_ticks=14 train=4
A10 reverse=True accepted lag_ticks=12->11 brier=0.038125239058035824->0.029399408745696944 full_ticks=14 train=4
After, same one-liner stdout:
A9 n_ticks=12 b_lag_subset=True byte_identical=True
A10 reverse=False Refused {'invalid_b_lag_membership': 1} n_refused=1 unchanged=True
A10 reverse=True Refused {'invalid_b_lag_membership': 1} n_refused=1 unchanged=True
One-liner transport: cd C:\Users\neelj\nba-harness-h72 && python -B -c exec(bytes.fromhex('<ASCII hex of the following JSON-decoded body>'))
"from tests.platformkit.ingame.test_nba_four_arm_primary_contrast import source_rows,supported_lag_rows,serialized\nfrom scripts.platformkit.ingame import baseline_four_arm as scorer,baseline_four_arm_period as p\nimport copy\nrows=scorer.predict_rows([dict(r,model_prob=.6) for r in source_rows()],'nba_checkpoints_r1')\nbefore=p.stratified_cells(rows)\nfor r in rows: r.pop('d_subset')\nafter=p.stratified_cells(rows)\nprint('A9 n_ticks='+str(after['n_ticks'])+' b_lag_subset='+str('b_lag_subset' in after)+' byte_identical='+str(serialized(before['b_lag_subset'])==serialized(after.get('b_lag_subset'))))\nrows=supported_lag_rows(); baseline=p.stratified_cells(rows)\nfor reverse in (False,True):\n changed=copy.deepcopy(rows); r=next(r for r in changed if r['game_id']=='g1' and '12:01:' in r['ts'])\n for target in (r,r['b_lag_subset']): target['B_lag']=None; target['paired_losses']['B_lag']=None\n r['b_lag_subset']['warmup']=True\n try:\n  result=p.stratified_cells(changed[::-1] if reverse else changed)\n  print('A10 reverse='+str(reverse)+' accepted lag_ticks='+str(baseline['b_lag_subset']['n_ticks'])+'->'+str(result['b_lag_subset']['n_ticks'])+' brier='+str(baseline['b_lag_subset']['comparisons']['C_minus_Blag_brier']['point'])+'->'+str(result['b_lag_subset']['comparisons']['C_minus_Blag_brier']['point'])+' full_ticks='+str(result['n_ticks'])+' train='+str(r['b_lag_subset']['train_n_ticks']))\n except p.Refused as e:\n  print('A10 reverse='+str(reverse)+' Refused '+str(e.reasons)+' n_refused='+str(e.counts['n_refused'])+' unchanged='+str(serialized(baseline)==serialized(p.stratified_cells(rows))))\n"
Execution correction: a premature process poll overlapped two initial file runs; the second was interrupted. Both files were rerun serially, followed by the remaining single-file runs.
Development checkpoint: 42 failed, 102 passed in 115.80s (0:01:55); broadening the absent-metadata branch counted three extra warm-up rows. Restored the FIX 1j missing-metadata scope; explicit membership contradictions still validate on every row.
FIX 1k historical verification: all eight single-file runs passed; three CLI helps exited 0; preflight FAIL=0. Current FIX 1l results follow.
## FIX 1l - AMENDMENT 11
Local file-only continuation of retained FIX 1k (staged and unstaged); Python 3.10.0, C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe.
period.py:56-57 checks carried arm probabilities/losses before warm-up or OT exclusion; the landed internal AD projection remains exempt, with its existing runner validation unchanged. Rows carrying no probabilities retain their exclusion behaviour.
period.py:184-193 moves carried B_lag validation outside warm-up/period conditions; only missing_b_lag_subset remains conditional. No population/cell computation can precede this validation.
Primary-contrast regressions pin both orders for warm-up infinity/NaN/out-of-range, both wrong losses, OT and absent metadata, every A-D endpoint with either inconsistent metric (warm-up and scored), and warm-up subset losses. Existing test AST preserved while compacting statements to meet 300 LOC.
Focused development run: 4 failed, 118 passed, 144 deselected in 4.59s. The four new subset-only tests exposed shared B_lag loss dictionaries in the fixture; copying the subset before mutation corrected isolation. Production refusal was already correct.
Exact before stdout, retained FIX 1k:
```
probability=inf reverse=False ACCEPTED lag_ticks=12
probability=inf reverse=True ACCEPTED lag_ticks=12
probability=-0.1 reverse=False ACCEPTED lag_ticks=12
probability=-0.1 reverse=True ACCEPTED lag_ticks=12
probability=1.1 reverse=False ACCEPTED lag_ticks=12
probability=1.1 reverse=True ACCEPTED lag_ticks=12
brier=0.123 reverse=False ACCEPTED lag_ticks=12
brier=0.123 reverse=True ACCEPTED lag_ticks=12
logloss=0.123 reverse=False ACCEPTED lag_ticks=12
logloss=0.123 reverse=True ACCEPTED lag_ticks=12
```
Exact after stdout, FIX 1l:
```
probability=inf reverse=False Refused {'invalid_probability:B_lag': 1} n_refused=1
probability=inf reverse=True Refused {'invalid_probability:B_lag': 1} n_refused=1
probability=-0.1 reverse=False Refused {'invalid_probability:B_lag': 1} n_refused=1
probability=-0.1 reverse=True Refused {'invalid_probability:B_lag': 1} n_refused=1
probability=1.1 reverse=False Refused {'invalid_probability:B_lag': 1} n_refused=1
probability=1.1 reverse=True Refused {'invalid_probability:B_lag': 1} n_refused=1
brier=0.123 reverse=False Refused {'inconsistent_paired_loss arm=B_lag': 1} n_refused=1
brier=0.123 reverse=True Refused {'inconsistent_paired_loss arm=B_lag': 1} n_refused=1
logloss=0.123 reverse=False Refused {'inconsistent_paired_loss arm=B_lag': 1} n_refused=1
logloss=0.123 reverse=True Refused {'inconsistent_paired_loss arm=B_lag': 1} n_refused=1
```
Executed Python one-liner (same before and after; construct only):
`cd C:\Users\neelj\nba-harness-h72 && python -B -c exec(bytes.fromhex('66726f6d2074657374732e706c6174666f726d6b69742e696e67616d652e746573745f6e62615f666f75725f61726d5f7072696d6172795f636f6e747261737420696d706f727420737570706f727465645f6c61675f726f77730a66726f6d20736372697074732e706c6174666f726d6b69742e696e67616d6520696d706f727420626173656c696e655f666f75725f61726d5f706572696f6420617320700a666f72206b696e642c62616420696e205b282770726f626162696c697479272c666c6f61742827696e662729292c282770726f626162696c697479272c2d2e31292c282770726f626162696c697479272c312e31292c28276272696572272c2e313233292c28276c6f676c6f7373272c2e313233295d3a0a20666f72207265766572736520696e202846616c73652c54727565293a0a2020726f77733d737570706f727465645f6c61675f726f777328293b20723d6e657874287220666f72207220696e20726f777320696620725b277761726d7570275d206973205472756520616e64206973696e7374616e636528722e6765742827625f6c61675f73756273657427292c6469637429290a2020666f722074617267657420696e2028722c725b27625f6c61675f737562736574275d293a0a2020206966206b696e643d3d2770726f626162696c697479273a207461726765745b27425f6c6167275d3d6261640a202020656c73653a207461726765745b277061697265645f6c6f73736573275d5b27425f6c6167275d5b6b696e645d3d6261640a20207472793a0a202020633d702e737472617469666965645f63656c6c7328726f77735b3a3a2d315d206966207265766572736520656c736520726f7773293b20726573756c743d274143434550544544206c61675f7469636b733d272b73747228635b27625f6c61675f737562736574275d5b276e5f7469636b73275d290a202065786365707420702e5265667573656420617320653a20726573756c743d275265667573656420272b73747228652e726561736f6e73292b27206e5f726566757365643d272b73747228652e636f756e74735b276e5f72656675736564275d290a20207072696e74286b696e642b273d272b73747228626164292b2720726576657273653d272b7374722872657665727365292b2720272b726573756c74290a'))`
FIX 1l historical single-file results: test_nba_four_arm_trial_contrast.py: fifty-four passed in 40.92s; test_nba_four_arm_primary_contrast.py: 266 passed in 116.86s (0:01:56); test_nba_four_arm_trial.py: 78 passed in 22.91s; test_baseline_four_arm_period.py: 72 passed in 17.03s; test_baseline_four_arm_nba.py: 134 passed in 17.19s; test_four_arm_output_audit_nba.py: 30 passed in 36.18s; test_baseline_four_arm.py: 53 passed in 2.25s; test_baseline_four_arm_eligibility.py: 45 passed in 1.02s
Earlier selection before test insertion: 144 deselected in 1.51s, exit 5; the focused development failure is recorded above. Every requested full file now exits 0.
CLI helps: baseline_four_arm, baseline_four_arm_period, nba_four_arm_trial: exit 0 each.
Preservation: exactly period.py, primary-contrast tests and this memo changed from FIX 1k; nine other owned SHA-256 hashes match. Reversing only the two production edits reconstructs FIX 1k period.py at its original SHA-256.
Guards and every unowned tracked file have no HEAD diff; S405 assertion edits remain confined to :119/:184/:269. New pinned tests: primary_contrast.py:141/:159/:172. No authorized check was skipped; git metadata untouched.
LOC per owned file: {"scripts/platformkit/ingame/baseline_four_arm.py":296,"scripts/platformkit/ingame/baseline_four_arm_features.py":242,"scripts/platformkit/ingame/baseline_four_arm_period.py":299,"scripts/platformkit/ingame/nba_four_arm_trial.py":223,"scripts/platformkit/ingame/four_arm_output_audit_checks.py":300,"tests/platformkit/ingame/test_baseline_four_arm_nba.py":297,"tests/platformkit/ingame/test_baseline_four_arm_period.py":299,"tests/platformkit/ingame/test_nba_four_arm_trial.py":300,"tests/platformkit/ingame/test_nba_four_arm_primary_contrast.py":300,"tests/platformkit/ingame/test_four_arm_output_audit_nba.py":138,"tests/platformkit/ingame/test_nba_four_arm_trial_contrast.py":300,"docs/evidence/harness/S417_c_minus_b_primary_2026-09-22.md":295}
git status --porcelain (JSON lines preserve index/worktree columns): ["M  scripts/platformkit/ingame/baseline_four_arm.py","M  scripts/platformkit/ingame/baseline_four_arm_features.py","MM scripts/platformkit/ingame/baseline_four_arm_period.py"," M scripts/platformkit/ingame/four_arm_output_audit_checks.py","M  scripts/platformkit/ingame/nba_four_arm_trial.py","M  tests/platformkit/ingame/test_baseline_four_arm_nba.py","M  tests/platformkit/ingame/test_baseline_four_arm_period.py"," M tests/platformkit/ingame/test_four_arm_output_audit_nba.py","M  tests/platformkit/ingame/test_nba_four_arm_trial.py"," M tests/platformkit/ingame/test_nba_four_arm_trial_contrast.py","?? docs/evidence/harness/S417_c_minus_b_primary_2026-09-22.md","?? tests/platformkit/ingame/test_nba_four_arm_primary_contrast.py"]
Preflight command: `cd C:\Users\neelj\nba-harness-h72 && python -B -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/baseline_four_arm.py scripts/platformkit/ingame/baseline_four_arm_features.py scripts/platformkit/ingame/baseline_four_arm_period.py scripts/platformkit/ingame/nba_four_arm_trial.py scripts/platformkit/ingame/four_arm_output_audit_checks.py tests/platformkit/ingame/test_baseline_four_arm_nba.py tests/platformkit/ingame/test_baseline_four_arm_period.py tests/platformkit/ingame/test_nba_four_arm_trial.py tests/platformkit/ingame/test_nba_four_arm_primary_contrast.py tests/platformkit/ingame/test_four_arm_output_audit_nba.py tests/platformkit/ingame/test_nba_four_arm_trial_contrast.py docs/evidence/harness/S417_c_minus_b_primary_2026-09-22.md --base master --spec docs/evidence/tracking/specs/S417_spec.md`
FIX 1l historical preflight: PASS vocab clean over 12 files; PASS crlf no index-side CRLF over 12 file(s); 2 untracked, core.autocrlf normalizes on add; PASS loc all .py <= 300 LOC; PASS schema additive over checked artifacts; PASS head_slice no head slices; PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec; PASS proposed no --proposed given; PASS removed_artifact no removed/renamed artifacts under 4 dir(s); PASS row_duplication no row duplication over checked artifacts
FAIL=0; exit 0.
## FIX 1m - AMENDMENT 12
Tier 1 BLOCKING 1 and Tier 2 P1 BLOCKER are the same missing-key defect; both are fixed in baseline_four_arm_period.py:194 by checking key presence before membership validation. Carried-value validation remains unconditional; scored missing_b_lag_subset and explicit-None contradictions still refuse.
Reproduction: supported_lag_rows(); select first warmup row with a dictionary b_lag_subset, retain B_lag=0.5 and losses brier=0.25/logloss=0.6931471805599453, then pop that key; call stratified_cells on [row], rows and rows[::-1].
Exact before output:
```
absent alone ACCEPTED n_ticks=0
absent forward Refused {'invalid_absent_b_lag': 1} n_refused=1
absent reverse Refused {'invalid_absent_b_lag': 1} n_refused=1
```
Exact after output:
```
absent alone ACCEPTED n_ticks=0
absent forward ACCEPTED n_ticks=14
absent reverse ACCEPTED n_ticks=14
```
Setting the key explicitly to None instead refuses {'invalid_absent_b_lag': 1}, n_refused=1, alone/forward/reverse both before and after.
Regression: test_warmup_absent_metadata_is_not_exclusion enumerates 12 CONSTRUCT cases: absent/explicit None x alone/two-row mix/full batch x forward/reverse; accepted comparisons retain their values. Existing test AST is unchanged after statement compaction for the 300-line cap.
Tier 1 NOTE 4 required action: rerun all eight test files serially using writable TEMP/TMP inside this worktree; current results follow. All other verifier notes require preservation, with no production changes beyond the single condition.
FIX 1m serial runs, each python -m pytest tests/platformkit/ingame/<file> -q -p no:cacheprovider: test_nba_four_arm_primary_contrast.py 278 passed; test_nba_four_arm_trial_contrast.py fifty-four passed; test_nba_four_arm_trial.py 78 passed; test_baseline_four_arm_period.py 72 passed; test_baseline_four_arm_nba.py 134 passed; test_four_arm_output_audit_nba.py 30 passed; test_baseline_four_arm.py 53 passed; test_baseline_four_arm_eligibility.py 45 passed. Total 744 passed, zero failures/setup errors.
Three --help commands (baseline_four_arm, baseline_four_arm_period, nba_four_arm_trial) and baseline_four_arm --self-check exited 0. Hashes confirm all other checked sources/tests unchanged; reversing the single production condition reconstructs its starting hash. Only period.py, primary-contrast tests and this memo changed in FIX 1m; ASCII, lines 299/300/300 respectively.
FIX 1m contract_preflight: nine PASS checks over all 12 row files with --base master --spec docs/evidence/tracking/specs/S417_spec.md; zero FAIL, exit 0. The verdict file was excluded. No commit created.
## NOT VERIFIED
- LATENCY-EXPLAINED interpretation rule is NOT implemented; follow-up row for the orchestrator, with no row id allocated by this lane.
- S402 real audit after B_lag; orchestrator must run it after landing.
- Real corpus execution, primary auditor reconstruction for C-minus-B, charged trial, production seal, and production ledger.
- Master-side independent verification and landing; this lane made no commit and used no network.
