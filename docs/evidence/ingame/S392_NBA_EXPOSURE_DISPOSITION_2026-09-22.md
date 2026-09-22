# S392 NBA exposure and provenance disposition

Disposition: REJECT an untouched-validation claim for every historical NBA
population considered here, for arms A/B/C. Recommend option (iii), none.
Arm D remains DESCRIPTIVE ONLY. This is a documentary decision before sealing,
not a scored result, a census, a preregistration seal or authorization to run.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, especially Q6.

## 1. Exposure inventory by identity

A game is EXPOSED if any decision the current program relies on used its outcome.
Exposure concerns design and selection as well as coefficient fitting. A later
chronological split cannot undo an earlier outcome-informed program decision.
The inventory distinguishes documented reliance from outcome reads whose effect
on the current design is NOT TRACED. Unknown influence is not evidence of no influence.

Identity sets, attributed to prior records rather than reconstructed here:

- U: every distinct game_id in data/cache/inplay_odds/nba_checkpoints_full.parquet;
  historically 1,593 games / 465,249 ticks, 2024-10-22 through 2026-06-13.
- S: S86's alternating sorted whole-game partition, seed 0, basis corpus_unit;
  historically 797 games / 232,951 ticks. Its recorded screen digest is
  f105c609d2d4e56018a108a4154a81b2074115b533fec8b7e18150999fac8ca3.
- V: U minus S, historically 796 games; recorded partition digest
  0683cbeab12a48f2bcb146821eaa857160356fe393b31c770c0cf61735ced402.
  This means outside S86, not outside prior outcome use.
- H: last traded tick with elapsed <= 24.0 per game in U, S58 trial B's
  1,593 checkpoints. H covers every identity in both S and V.
- W: S86 screen games remaining after the train-only seed fold, historically
  673 games / 192,635 ticks. J: S98's bridged subset after warm-up,
  historically 571 games / 162,171 ticks. J and W are subsets of S, not new games.

The following quotes are exact contiguous excerpts of ledger lines, not new
measurements. L refers to docs/evidence/RESULTS_LEDGER_SYSTEM.md at this read.
Game membership recipes identify populations; no archive or per-game manifest
was opened, and exact membership/census reconciliation remains unverified.

| Row and ledger excerpt | Games / ticks, fit or selection | Decision used by this program |
|---|---|---|
| S247 L462: "rates coverage 0/661 game clusters; no three-arm score" | S92 `_all`: 661 games / 79,554 ticks; `_rated`: 284 / 33,713. Memo premise recomputed market/null/ladder Brier on both; no new fit or simulator score. Exact overlap with U NOT TRACED. | Rates availability stopped simulator evaluation; zero qualifying games does not erase the premise's outcome reads. Direct S382 reliance NOT TRACED. |
| S261 L511: "full CPCV archive reproduced exactly at NBA n_eff 1,313 and MLB n_eff 23,279" | S211 NBA game paths, all 1,313 admitted; first attempt also scored 120 evenly spaced paths with all their checkpoints. Train-only team-rate prior, score-only and conditional arms scored through CPCV. Unique tick count and overlap with U NOT TRACED; CPCV repetitions are not new identities. | Public figures NOT REPRODUCED under the frozen bar; archive/schema correction, no public-page change. Direct S382 reliance NOT TRACED. |
| S308 L613: "nested ALL coverage 1.0 at 0.90 and 0.80 (n=465,249 ticks / 1,593 games)"; L616: "no third rerun" | U; six outer blocks x five calibration blocks, nested training/calibration with outer labels excluded; grouped coverage and interval-loss scoring, S294 replay. Later CLOSED AT LIMIT adjudication makes these screening records, not accepted confirmation. | Corrected S294 interval-score accounting and stopped reruns; direct S382 reliance NOT TRACED. Full-U outcome reading remains despite rejection. |
| S317 L584: "additive v2 series reproduces 3-arm Brier/ECE from 2,130 S287 ticks at max difference 0.0" | S287's 355 games / 2,130 unique selected ticks; archived market/null/simulator probabilities and outcomes, no refit or new selection. Exact overlap with U NOT TRACED. | V2 series feeds S322's premise and ablation; direct S382 reliance NOT TRACED. Schema repair does not create independent observations. |
| S322 L611: "n=2130/355"; "decision STOP SIMULATOR EXPANSION" | S287/S317's same 355 games / 2,130 ticks; CPCV fits temperature/intercept with and without tick-market substitution for missing pregame prior; loss/ECE ablation against null. Thirty traced states are a diagnostic subset, not the scored denominator. | Outcome-based stop decision until transition diagnostics are fixed; direct S382 reliance NOT TRACED. No new identities beyond S287/S317 are established. |
| S328 L625: "313 sealed states (273 active), 2184 unique replay rows"; "CPCV sign unchanged at all 4 delays" | S320 sealed states from 63 strata; 40 terminal exclusions, 273 active states / 230 games per delay, two arms x four delays. Frozen S310/S309 null versus raw-market substitute, no refit; CPCV Brier/log-loss survival and bootstrap seed selected after sealing. Exact U membership NOT TRACED. | Ordering-only conclusion without receipt timestamps; no historical-availability clearance. Direct S382 reliance NOT TRACED. |
| S58 trial 2, L174: "halftime n 1,593"; "NOT RECONSTRUCTIBLE" | Earlier runtime-Elo halftime result on U; missing prior vintage and per-game losses. No fit established. | Replaced by reconstructible as-of trial B (S63); informs archive/provenance requirements. |
| S58 trial B / S63, L193: "on 1,593/1,593 games (LAST tick <= 24.0 elapsed; 0 dropped)"; "BEHIND (replicated on 0/2 units)" | H, all U. Fixed repricer plus prior updated only from earlier games; no outcome-fit in this trial. Compared model/state references to market and inspected season/stale-prior slices. | S86 explicitly uses this sealed checkpoint result as its incumbent reproduction target and extends that model/market question to all screen ticks. The current program retains that baseline lineage and its exposure/provenance diagnosis. |
| S86, L236: "INDEPENDENT REPRODUCTION: re-deriving S58 trial B's own checkpoint selection matches its archived per-game CSV on 797/797 screen games"; "TARGET FOR THE NEXT ARM: P1-P2, \|margin\| <= 5, > 12 min remaining" | All ticks in S; no fit, but outcome-scored cells and market reliability select a follow-up region. | S94 evaluates the selected region; later screens use its recalibration null. S382 uses S86 coverage to define D's paired subset and the proposed exposure split. |
| S98, L255: "571 games / 162,171 ticks actually SCORED after the train-only seed fold"; "21 of the 127 fitted cell-folds PIN AT THE GRID MAXIMUM 24.0" | J; alternative as-of prior, train-fold recalibration, phase-cell sigma grid and blend selection. The bridge matched 668 of S's games before warm-up; additional pregame comparison used 664 games. | The observed grid limit prompted S103; failed alternative prior prompted removing its coverage restriction. S385 relies on this history to distinguish later fitted sigmas from the unexplained fixed constant. |
| S103, L258: "scoring the one incumbent prior p0_asof lifts coverage 571 -> 673 games and 162,171 -> 192,635 ticks"; "cells_clearing_bar = [], prereg_draft_warranted = False" | J and W; wider cell sigma grid, parametric sigma and global blend fitted on training folds; held-out comparisons inspected. | No prior draft promoted; S385 uses this fitting history in its provenance conclusion. Neither S98 nor S103 authored the original 13.5 constant. |
| July reliability map, reported in S86 L236: "already carries a per-bucket MARKET Brier over all 465,249 ticks" | U market outcomes; model side sampled twelve ticks per bucket on a different simulation path. Original authoring/selection history unknown. | S86 treated it as prior art when deciding a paired model series was missing. It further defeats a literal never-scored description of V. |
| S148, L354: "LIVE iff game_clock_s > 0 OR period < 4, DEAD iff period >= 4 AND game_clock_s == 0"; "0 of 15 headlines and 0 of 10 sweep hypotheses, 2 of 27 S86 cells" | Requotes S and descendant paired-loss archives after live/dead filtering; S86 live subset has 110,886 ticks. No refit. Whole-source dead-row census also reported. | Astra section 1 cites S148's final-state defect; S382 requires the corresponding live exclusion. This is an explicit current-design dependency. |

Additional outcome-reading rows found by the ledger search are recorded below.
Rows with no documented current-design adoption are not represented as proven
causes of the four-arm choice. Their historical access still rules out calling
the archive literally never scored, and prevents certifying an untouched subset.

| Additional row identity and exact ledger excerpt | Outcome population and fit/selection | Current-program decision or limit |
|---|---|---|
| S94 L245: "any future arm on this defect must be scored on Brier with ECE as a diagnostic only." | W; cell shrinkage and global/cell logistic nulls fitted on train. | Brier-first follow-up rule documented; S382 is Brier-primary. |
| S96 L252: "153,941 per-tick rows over the six arms" | Reads S; event arm 665 games / 39,168 ticks; phase-lambda fits across thresholds/horizons, logistic null. | No candidate advancement; direct S382 reliance NOT TRACED. |
| S97 L249: "the noise fit reads no outcome"; "192,635 ticks / 673 games scored on the S86 SCREEN side." | W; noise fit outcome-blind, but loss/coverage diagnostics and fitted null/blend use outcomes. | Interval failures prompted S101; direct S382 reliance NOT TRACED. |
| S101 L257: "192,635 ticks / 673 games scored, 40,316-tick seed never scored." | W; train conformal bands, outcome-updated adaptive coverage. | Feeds conformal follow-ups; direct S382 reliance NOT TRACED. |
| S102 L266: "0 of 564 scored hypotheses clear the +0.004 bar" | W; 564 of 576 grammar hypotheses fitted/scored. | Ranking fed S114 and expansion S144; no advancement. |
| S114 L303: "NESTED-SELECTION ENSEMBLE OF IN-GAME HYPOTHESES IS A SCREEN NULL"; S126/S124 L335: "THE LADDER on 192,635 ticks / 673 game clusters" | W; nested top-k fits and corrected matched-training comparison. | No ensemble advancement; direct S382 reliance NOT TRACED. |
| S115 L289: "THREE NON-LINEAR IN-GAME ARMS OVER THE MARKET OFFSET ARE ALL BEHIND THE RAW LINE AND ALL BEHIND THE RECALIBRATION NULL." | Reads S, comparison W per S148; three residual learners fitted. | Direct S382 reliance NOT TRACED. |
| S116 L294: "lambda on an inner TRAIN split"; S152 L363: "S116 RE-RUN END TO END; NBA INFORMATIVE COUNT NOW ASSERTED" | S-derived NBA plus MLB; residual logistic pooling fits, inner lambda selection. Exact NBA scored count unresolved. | Direct S382 reliance NOT TRACED. |
| S144 L357: "1,076 SCREENED / 16 UNSCORED" | W; pairwise grammar fitted against matched logistic null. | Direct S382 reliance NOT TRACED. |
| S224 L465: "465249 ticks/1593 games; ECE 0.001167; 0/20 scorable" | U; no fit; tail diagnostics on 1,590 games / 308,756 ticks, middle remainder accounted. | Motivated S272; direct S382 reliance NOT TRACED. |
| S227 L472: "1593 games/465249 ticks; fixed CRPS 2.831222, fitted CRPS 2.827759" | U; train-cell CRPS sigma selection, grid 3..60 by 0.5, five groups. | Direct S382 reliance NOT TRACED. |
| S272 L505: "all-ticks Brier 0.073354 vs 0.073317, delta -0.000037" | U; logistic baseline and tail isotonic fits; middle unchanged. | Replayed by S293/S309; direct S382 reliance NOT TRACED. |
| S276 L509: "full-source incumbent conformal coverage replayed on the pod: 465,249 / 1,593" | U; STATIC conformal coverage; wrong block design rejected. | Replaced by S294; rejection does not erase exposure. |
| S279 L517: "465249 ticks/1593 clusters; 49 zero weights" | U; no joinable candidate columns, zero-weight identity fallback; intended finite shrinkage selection not exercised. | Direct S382 reliance NOT TRACED. |
| S294 L521: "465249 ticks/1593 games; 12/12 grouped cells and S101 24/24 exact" | U; six-block train-calibrated STATIC conformal bands. | Corrects S276; direct S382 reliance NOT TRACED. |
| S283 L526: "465249 ticks/1593 games; Brier improvement -0.140383703" | U; empirical time-score table, training-selected k and logistic null; CPCV can train on later blocks. | Direct S382 reliance NOT TRACED. |
| S293 L543: "465249 ticks/1593 games; replay max delta 2.602085e-18" | U; replay S272 fitting, additional tail diagnostics. | Precondition for S309; direct S382 reliance NOT TRACED. |
| S309 L548: "on 465249 ticks/1593 games; CPCV -0.000031583336663" | U; forward and CPCV logistic/tail-isotonic fits; fitted knots and memberships archived. | Direct S382 reliance NOT TRACED. |
| S84 L233: "577 games / 68,632 priced live-clock ticks at a full 5v5"; S92 L306; S123 L314: "ALL corpus (79,554 ticks / 661 games)" | Lineup-derived store: S84 scored 284 games / 33,713 ticks; later dynamic lineup/fatigue terms. Available and scored populations differ; overlap with U unresolved. | Baseline ordering examined; direct S382 reliance NOT TRACED. |
| S137 L339: "all 20 landed headlines", "VERDICTS CHANGED 0"; S143 L345; S142 L346 | Prior outcome archives replayed/requoted; no new independent population. Exact per-row keys not reconstructed. | Archive corrections; direct S382 reliance NOT TRACED. |
| S208/S216/S209/S218/S228/S211/S235/S238/S210/S244/S250/S257/S258/S259 at L441/457/458/459/468/471/478/480/482/486/490/491/494/501: "per-phase recalibration: nine buckets all >= 30 clusters, BH survivors none" | Recalibration outcome reads; individual identities/ticks unresolved, not separate independent populations. | Direct S382 reliance NOT TRACED for each named row. |
| S219 L460: "306735 ticks/1056 games"; S237 L477: "key present in 5/5 period and 15/15 period-margin cells; OT q90 0.787" | Composite Brier screen and outcome diagnostic reread respectively; precise fit/selection and S237 denominator unresolved. | Direct S382 reliance NOT TRACED for either. |
| S256 L495 / S266 L499 / S287 L566: "355 games/2,130 targets" (S287) | Simulator family; earlier constructs use 30 games / 180 ticks and are NOT real exposure. S287 real scored targets have unresolved overlap with U. | Repeatability defect documented; direct S382 reliance NOT TRACED. |
| S265 L500: "79919 ticks / 269 games"; S277 L510: "461947 per-tick CPCV records" | Conformal sample and staleness/interaction fits respectively; S277 unique games unresolved. | Direct S382 reliance NOT TRACED for either. |
| S280 L515: "40 clusters"; S281 L520: "n=460365/1582"; S285 L519 | Cross-venue calibration, momentum, static-band coverage respectively; S285 exact population unresolved. | Direct S382 reliance NOT TRACED for each. |
| S310 L556: "117964 evaluator states from 465249 source rows"; "1267 tail game clusters of 1593" | U-derived tail beta-offset; "one fitted fold (48349 train ticks)". | Direct S382 reliance NOT TRACED. |
| S320 L619: "313 states across 63 strata" | Replay audit; outcome availability/polarity and identity overlap unresolved. | No verified fresh outcome evaluation inferred; direct S382 reliance NOT TRACED. |
| S05 L44/94, S42 L83, S50 L179, S200 L434, S212 L443; L83: "n = 1,814 of 1,814 rows, 0 dropped" | NBA pregame gate calibration, isotonic/regime fits and repaired replay. | Checkpoint overlap and direct S382 reliance NOT TRACED for each. |
| S64 L198, S58c L209, S75 L225-226, S79 L231, S85 L275, S108 L272, S111 L285, S112 L282, S113 L292, S167 L397, S204 L433, S230 L473; L397: "NBA n=4,846"; L473: "1,814 paired rows" | Factory/pregame outcome fits, screens and recalibration; populations vary, no identity join made. S58c uses last 800 screen-side rows by ISO-week partition. | Checkpoint overlap and direct S382 reliance NOT TRACED for each; do not reuse their counts as U membership. |
| S229 L466, S242 L483, S271 L514, S296 L545, S298 L552-553, S331 L649, S332 L632, S335 L636/639/641/651, S340 L652; L545: "78767 player-games/3645 games"; L649: "2025-26 test 265 games" | Margin/prop/pregame outcome evaluations; exact per-row fitting histories and checkpoint overlaps unresolved in these ledger excerpts. | Direct S382 reliance NOT TRACED for each. |

| Further census identity and exact ledger excerpt | Outcome population and fit/selection | Current-program decision or limit |
|---|---|---|
| S128/S129 L331: "nba_player_value_features 0 of 32 moved" | Shared NBA screen population, 800 screen rows; before/after real-predictor T1 screens, 32 comparisons and best-member selection against Elo. Exact fit internals, game/tick membership and U overlap NOT TRACED. | As-of supply corrections retained, NBA screen ordering unchanged; direct S382 reliance NOT TRACED. Shared row identities do not create two populations. |
| S130 L316: "s58_trialB_nba_halftime 1593 -> 1593"; "published_ci_reproduced_from_series True on all three" | H, all 1,593 U games; archived paired-loss CI reproduction and informative-tick re-quote, no refit. Combined ledger also names S134/S135 controls, not additional scored populations. | Re-quote retained NBA denominator and CI; direct S382 reliance NOT TRACED. Reproduction does not supply fresh observations. |
| S132 L322: "nba close coverage 952 -> 563 of 1,814"; "30 clusters, n 351 -> 171" | NBA gate games; S112 close/Elo re-score on 171 rows, plus S113 close-arm screens on 313 served rows after contamination filtering. Same S112 functions, NBA k raised 6 to 8; S113 screens 945 candidates. Tick-store premise examined 1,591 first traded Q1 ticks; exact overlap with U NOT TRACED. | Corrected close reference and published comparisons; screen rejection retained. Direct S382 reliance NOT TRACED. |
| S202 L436: "4/4 archived one-way/two-way stand-in+paired n_eff pairs reproduced at seed 20260904; n=1814/39162/25834/41886" | NBA 1,814 gate game rows; S05 walk-forward recalibrated probabilities reconstructed, paired Brier losses and stand-in losses re-read for crossed team bootstrap. No new calibrator selected; exact U overlap NOT TRACED. | Dependence diagnostic and archived reproduction; direct S382 reliance NOT TRACED. |
| S205 L452: "12 cells refit exactly; CPCV isotonic differs from sealed S05 by 0.020533142" | NBA 1,814 gate game rows; isotonic/temperature/beta fits and ECE, Murphy and log-loss scoring, legacy replay then eight-group purged CPCV. Exact U overlap NOT TRACED. | CLOSED AT LIMIT on S05 reproduction; no calibrator served/promoted. Direct S382 reliance NOT TRACED. |
| S245 L488: "state-minus-naive CRPS +0.910973/+0.112388/+0.052133 at Q1/Q2/Q3" | 1,231 exact-bridged games with Q1-Q4 player stats, 208,887 player-stat loss rows at end Q1/Q2/Q3. Eight-group CPCV; time-scaled observed rate plus train-only residuals versus naive remaining distribution. Exact U overlap NOT TRACED. | BEHIND retained as calibration result; flag-routing test absent. Direct S382 reliance NOT TRACED. |
| S248 L485: "S92 archive reproduced at max abs diff 5.827586677109586e-17; required margin columns absent and no conditioned form scored" | S92 ALL 79,554 ticks / 661 games; RATED 33,713 / 284 counted. ALL baseline Brier and three archived fatigue/unit-onoff loss differentials replayed; no new fit. Exact U overlap NOT TRACED. | Missing margin inputs stopped all three conditioned forms; premise outcome access remains. Direct S382 reliance NOT TRACED. |
| S275 L512: "8/8 within S50 1e-6 and second-run 1e-9; flip diff 0.0" | NBA 1,814 gate game rows in positional/per-unit calibration, four-sport expanding walk-forward report recomputed twice; ECE against S50, explicit-basis consumer checks. Exact U overlap NOT TRACED. | Explicit per-unit reader repair accepted with legacy fallback; direct S382 reliance NOT TRACED. |
| S284 L518: "35 clusters; calibration improvement -0.0161008389" | U-derived 6,272 joined ticks / 40 games; first OOF block excluded, 5,486 scored states / 35 games. Eight-group CPCV fits baseline logit plus two native trade-occurrence inputs; seven evaluator repeats per state are not new identities. | Candidate rejected and not retained under frozen bar; direct S382 reliance NOT TRACED. |
| S297 L557: "preregistration sealed"; L558: "on 78,767 rows/3,645 games" | Recorded NBA player-games, 2023-10-24 through 2026-06-05; five-block CPCV, strictly earlier empirical minutes/DNP histories, pooled DNP and 70/30 positive-minute mixture. Minutes CRPS, DNP Brier/log-loss and coverage scored; positive-only quantile pooling gap remains. Exact U overlap NOT TRACED. | SINGLE-WINDOW comparison accepted with corrected row-weighted game-bootstrap CI; no second-corpus promotion. Direct S382 reliance NOT TRACED. |
| S44 L104: "The four artifacts were regenerated on the dated corpora" | NBA gate's 1,814 game rows, 2024-10-22 through 2026-04-12; S05 positional walk-forward recalibration replay, metrics unchanged. Exact overlap with U NOT TRACED. | Date metadata repaired; direct S382 reliance NOT TRACED. |
| S87 L234: "S58 trial B NBA halftime 1,593 -> 1,593" | H, all U; archived paired-loss CI replay and informative-tick filtering, no refit. NBA keeps every game. | Verdict unchanged; direct S382 reliance NOT TRACED. Re-reading H adds no independent games. |
| S225 L469: "187,203 ticks / 635 games" | Checkpoint/bridge intersection; earlier-game hot-night win-rate and scheme-fit score-differential histories, two real arms plus planted nulls; six-group CPCV with strict prior-date fits against S123/market. Exact U overlap NOT TRACED. | No candidate cleared the fixed bar; direct S382 reliance NOT TRACED. |
| S267 L502: "fixed 1e-9 match missed on 4/4 per-unit ECE targets" | NBA positional/per-unit calibration replay; exact game/tick identities, count and fitting details unresolved in memo. | Consumer repair stopped; CLOSED AT LIMIT does not erase outcome access. Direct S382 reliance NOT TRACED. |
| S305 L535: "legacy and current routines both return 0.024842541854003943 on 1814 rows" | NBA gate games; historical per-regime OOF and S212 fitting replay, identical predictions. Exact U overlap NOT TRACED. | No repair retained; direct S382 reliance NOT TRACED. |
| S71 L216: "Brier from the artifact's stored Murphy decomposition" | S05's NBA 1,814-game reliability summary read for answer-serving; no new fit or tick-level score. Exact U overlap NOT TRACED. | Tracked calibration artifact selected for answers; direct S382 reliance NOT TRACED. Documentary reuse, not independent outcomes. |
| S120 L307: "every number transcribed from a memo or its register row (none recomputed)" | Prior NBA screen/pregame populations inventoried above; documentary outcome reread, no fit or new score. Exact row-level keys NOT TRACED. | Signal inventory compilation; direct S382 reliance NOT TRACED. |
| S56 L140: "the 60 REJECT verdicts were READ from the two reports, never re-derived" | Publication census includes 16 NBA signal classes; game/tick identities unavailable, no new fitting/scoring. | Public verdict documentation; direct S382 reliance NOT TRACED. |

FIX 1c adds the eight omissions plus S128/S129 and S130; search commands/counts are in the memo.
lexical hits do not prove exhaustive outcome or reliance tracing. S323/S338/S348/S377
are schema/count censuses; S383 reports no NBA cell computed. S317-to-S322 documents
a simulator stop decision with direct S382 adoption NOT TRACED. S308 reads full U;
S328 establishes ordering only. No added row supplies an unexposed population or
removes S58-to-S86-to-current-design reliance; option (iii) remains. Sources: memo.

## 2. Disposition for A / B / C

A is the market reference; B is recalibrated market; C is market plus declared
state. An untouched claim attaches to their paired evaluation population and
design, including the unfitted reference A, not just to whether an arm fits.

| Proposed historical population | A | B | C | Reason |
|---|---|---|---|---|
| (i) All 1,593 games, U | No | No | No | S58 scored every game; S86 and later rows informed design, exposure handling and live eligibility. |
| (ii) The 796 outside S86, V | No | No | No | H already contains every V outcome. S86's partition is local to S86; later whole-source analyses also read U. |
| (iii) None of U as untouched validation | Recommend | Recommend | Recommend | Use U only as disclosed historical development/descriptive evaluation; obtain independently unexposed observations for confirmation. |

Did S58 exposure feed a decision? YES: its outcome-scored baseline was retained
as S86's sealed incumbent and reproduction target; S86's expansion then selected
state regions, followed by fitted screens. The present design consumes that
lineage, including S86 coverage and the S385/Astra diagnosis. This is documented
program reliance, not proof that S58 directly selected S382's ridge or features.
No such direct parameter-selection record was found. Even if that narrower
causal link were disputed, the record does not establish V as independent of
historical decisions, so it cannot support the requested untouched claim.

In docs/evidence/harness/S86_nba_every_tick_2026-09-03.md section 1:
"S58 trial B used NO screen/verdict partition." Its phrase "untouched here"
qualifies only S86's operation, not the full research history.
In docs/evidence/harness/ASTRA_NBA_SECOND_CORPUS_AUDIT_2026-09-21.md section 1:
"Prior exposure prevents calling this untouched validation" and
"Conversion creates no new independent observations."
S385's ledger suggestion that V is an untouched candidate is therefore refused
as a final disposition. S382 itself already says:
"Thus these 796 games are NOT asserted to be untouched validation."
This document resolves that open question; it does not edit S382 or add a seal.

Historical chronological evaluation can still describe performance under its
stated design, but cannot acquire an untouched label by deleting S, changing
ticks, reweighting periods, converting files or splitting the same seasons.
Any future untouched population needs a frozen identity manifest and a recorded
absence of prior outcome-dependent design use; its size is TO-FREEZE-FROM-CENSUS.

## 3. Arm D and the missing authoring evidence

D is DESCRIPTIVE ONLY, even on a separately authorized historical evaluation.
docs/evidence/harness/S385_S86_MODEL_PROVENANCE_SCOUT_2026-09-21.md states:
"Every constant is UNKNOWN; arm D is not untouched out-of-sample on the NBA corpus."
The as-of replay guard protects a game's immediate input calculation; it cannot
establish how the parameters were originally chosen.

Evidence required to reconsider parameter provenance:

1. The original dated authoring transcript, notebook, tuning-run record or design
   artifact for commit ee7087200, explicitly linking ELO_K=20, ELO_MEAN=1500,
   ELO_HFA=76 and SEASON_REGRESS=0.25 to their selection process. It must identify
   every input file/version, game ID/date population, outcomes inspected, search
   alternatives and selection criterion, or document their independently fixed
   origin. A comment or the commit date alone does not supply this evidence.
2. The corresponding origin record for margin sigma=13.5 at 0f1aff49f/20b51ae5f,
   including the source behind "NBA ~13-14 pts." and its game population; trace
   the later copies through cab70ccb1 and ef7775966. The ee7087200 record alone
   cannot clear a separately authored constant.
3. Reconcile those named identities to the candidate manifest. S385 proposes
   a named disjoint pre-2024-10 source as CLEAN; overlap means historical exposure.
   The 4,846-game build reported alongside ee7087200 includes the evaluated
   seasons and does not prove either tuning or disjointness. Record any later
   revisions, source-vintage evidence and the actual model-generation version.

Custodian: project owner Neel Shah and the original authoring session history
for those commits, including any local session transcript or saved design notes.
S385 says the ee7087200 authoring record is not held in this tree; its actual
filename/location is UNKNOWN. These are records to recover, not invented files
asserted to exist. The owner supplies them and the independent provenance review
adjudicates them before a revised prereg is sealed. Clearing provenance would
permit reconsidering D on a separately unexposed population; it would NOT undo
S58 or later exposure on U. Archive vintage/receipt and paired-key eligibility
would still need clearance. Until then D cannot become the primary by selection.

## 4. Two replacement prereg paragraphs for S382

Exposure paragraph (paste over the exposure-decision paragraph): The NBA archive is historically exposed and supports no untouched-validation claim for A, B or C. S58 scored one checkpoint for every archive game; S86 used that baseline and inspected its screen half, and later rows examined the full source. Removing S86 games therefore does not restore independence. Treat all historical results as development/descriptive, including results on the complement of S86. Full historical games/ticks, S86-exposed games/ticks, complement games/ticks and any newly unexposed population sizes are each TO-FREEZE-FROM-CENSUS. Arm D remains DESCRIPTIVE ONLY pending original parameter-authoring records and independent provenance review. Any confirmatory population requires separately unexposed observations and a frozen identity/exposure manifest before a seal; this historical disposition alone authorizes no confirmatory claim.

Populations paragraph (paste into populations and replace the old proposed-validation designation): Preserve period-stratified C-minus-A Brier as the declared primary estimand, equal weights across Q1-Q4, with the existing whole-game uncertainty procedure and unchanged bars; on this historical archive its interpretation is descriptive only. Compare A/B/C on identical full live-eligible keys regardless of model availability, and compare D only with A/B/C recomputed using its identical eligible paired keys, training populations, folds and weights. Full, S86 and complement game/tick counts; training and warm-up counts; post-warm-up counts; D-paired counts; per-period, transition and cohort support; and any future untouched-validation game/tick counts are all TO-FREEZE-FROM-CENSUS. Do not transfer denominators between subsets or promote a favorable subset, arm or secondary cell. Empty eligible populations are reported honestly. The current candidate archive supplies no untouched primary validation population; amendment of the old primary-population wording throughout S382 is required before sealing. Seasonal or exposure partitions do not create independent corpora.

These paragraphs come from S382's own constraints, including:
"unresolved exposure blocks a confirmatory interpretation" and
"Within each declared reporting population, compare A/B/C on its FULL eligible
keys regardless of model availability." They replace the candidate designation,
not the eligibility rules, estimand, thresholds or pre-seal implementation work.

## 5. What the MLB result licenses for this design

docs/evidence/ingame/S347_FOUR_ARM_RESULT_2026-09-21.md states "EVERY comparison is UNDERPOWERED: UNDERPOWERED = 96." Its model arm has higher point loss than the market in every overall cell, while the intervals span zero; that is not a statistically established directional result. It fixes the corrected MLB baseline and licenses no AHEAD statement or change to the bars. For NBA, preserve the declared arm definitions, paired populations, whole-game uncertainty, concentration diagnostics and period-stratified design; resolve exposure and model provenance before sealing. Do not select favorable periods, discard D based on its MLB point estimate, or treat a larger tick count as demonstrated power. MLB and a genuinely independent NBA evaluation must support the same comparison before any joint directional conclusion. This is a design constraint, not a prediction of an NBA result.

## Documentary sources and limitations

All evidence paths below are relative to C:/Users/neelj/nba-harness-h51/.
Byte sizes are of the read documents; resolution is not applicable to text.

| Evidence input | Bytes |
|---|---:|
| docs/evidence/tracking/specs/S392_spec.md | 2820 |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 12532 |
| docs/evidence/RESULTS_LEDGER_SYSTEM.md | 793873 |
| docs/evidence/harness/S385_S86_MODEL_PROVENANCE_SCOUT_2026-09-21.md | 3976 |
| docs/evidence/harness/S86_nba_every_tick_2026-09-03.md | 15655 |
| docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md | 16975 |
| docs/evidence/harness/ASTRA_NBA_SECOND_CORPUS_AUDIT_2026-09-21.md | 10048 |
| docs/evidence/ingame/S347_FOUR_ARM_RESULT_2026-09-21.md | 16910 |
| docs/evidence/harness/S58_trialB_nba_halftime_asof_2026-09-03.md | 7272 |
| docs/evidence/harness/S58_promotion_list_2026-09-03.md | 38568 |

Additional fitting-detail documents followed by the read-only inventory reviewer:

| Evidence input | Bytes |
|---|---:|
| docs/evidence/harness/S224_ingame_tail_calibration_2026-09-04.md | 5814 |
| docs/evidence/harness/S227_margin_tail_crps_2026-09-04.md | 6087 |
| docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04.md | 2161 |
| docs/evidence/harness/S279_ingame_signal_stacker_2026-09-04.md | 4439 |
| docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_2026-09-04.md | 4611 |
| docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04_fix1b.md | 5176 |
| docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07.md | 16936 |
| docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c.md | 32570 |

## NOT VERIFIED

- Exact per-game exposure manifests, archive bytes, identity overlaps of pregame
  stores, corpus hashes and every proposed population denominator; no archive opened.
- Original parameter-authoring sessions, unseen historical decisions and archive
  vintage/receipt; documentary absence does not prove independence.
- No scoring/fitting CLI, test, network or pod run; historical numerical claims
  are attributed to source documents and were not reproduced by this lane.
- No seal, charge, fresh performance measurement or independent acceptance here.
