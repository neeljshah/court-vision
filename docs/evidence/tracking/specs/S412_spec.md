GAP S412 | sport all (maker channel) | worktree harness-h71 (master-based) | log cx_s412_microstructure_licence | ADJUDICATED 2026-09-22 21:15Z: ADOPTED (decision 13; Fable ruling under the build-platform rule that Fable makes the decisions the user would make; reversible until sealed)
# Microstructure licence: a sealed MATCH class beside S400's AHEAD licence, one contract, graded on markout (workstream E)

SINGLE PROBLEM: CalibrationEvidence.licensed() licenses a nonzero size only for verdict "AHEAD" with corpus_count >= 2 and one sealed digest per corpus (paper_sizing_inputs.py:86-89), so a maker book whose thesis is microstructure -- spread
capture with adverse-selection control -- may never hold an AHEAD model and would size zero forever. Under S347 every cell is UNDERPOWERED and the honest size is zero everywhere (docs/evidence/harness/S400_paper_sizing_2026-09-22.md).
Nothing can license a minimum size on the statement a maker book actually has: the residual is indistinguishable from zero. Without a second licence class the series never produces a measurement; with one, a null result is still a result.

BINDING BEFORE-CONDITION: quote from master (a) `VERDICTS = ("AHEAD", "BEHIND", "UNDERPOWERED", "SINGLE-WINDOW")` (paper_sizing_inputs.py:28) and `raise PaperSizingInputError("unknown_verdict", "verdict")` (:56-58), so a "MATCH" string
cannot enter the landed type; (b) licensed() (:86-89) and width(), "the point never enters the size" (:82-84); (c) `def verdict(lo, hi, n_games, n_min=N_MIN_GAMES): if n_games < n_min or (lo <= 0 <= hi): return 'UNDERPOWERED'; return
'BEHIND' if lo > 0 else 'AHEAD'` (gate_a0_ingame_vs_market.py:84-87) with N_MIN_GAMES = 30 (:24) -- one name over two facts, too few games and a well-powered interval covering zero; (d) `WIDTH_REFERENCE_DEFAULT = Decimal("0.02")`, "DECLARED
policy constant, never a measured number" (paper_sizing_policy.py:29-31), and _permitted's prospective check_caps call (:125-140); (e) FeeEvidence.certified, "BOUNDED is not certified" (:117-120), fed by require_certified, returning
`CERTIFIED fee_module_sha256=<sha>` and raising in refuse mode otherwise (fee_certification_gate.py:204-217); (f) TARGET_WEEKS = 8 (family_week_ledger.py:18), streak(), "Count qualifying weeks ending at the latest completed UTC ISO week",
walking back to the first week below weekly_floor (:164-173), and independence()'s shape, status "NOT INDEPENDENT" when two sets share a game id (:175-188); (g) quote_engine's "A caller must not substitute a standalone model value as the
default anchor", that default being the contemporaneous observed mid (:3-5), `_ADVERSE_CENTS = INGAME_MAX_DRIFT_PCT` (:35), the per-side adverse_selection_cents mapping (:141-144), `center = mid - k_inv * inv` (:164) and the reduce-only
flatten path (:134-160), reached through quote_reservation.make_quotes_reserved (:196); (h) position_caps' "Units are contracts ... Every logged open unfilled quantity counts ... max_permitted_qty is bounded by the submitted qty" (:1-9);
(i) markout_causal.summary_strict (:182-268) and its verdict line (:246-247) over entry_timing/study.py cluster_boot_ci, "95% CI for the mean, bootstrap resampling whole game clusters" (:30-32), returning (None, None) below five clusters
(:37-38); (j) `WEEK_GAMES, SPORT_GAMES, FILL_GAMES = 4, 30, 30` (forward_replay_qualification.py:15-24).

CHANGE (owned files: NEW scripts/platformkit/execution/microstructure_licence.py, NEW microstructure_licence_inputs.py, NEW tests/platformkit/execution/test_microstructure_licence.py, NEW test_microstructure_licence_inputs.py, memo.
ADDITIVE ONLY: paper_sizing_inputs.py, paper_sizing_policy.py, gate_a0_ingame_vs_market.py, forward_replay_qualification.py, quote_engine.py and venue_fees.py stay byte-identical to master; size_paper is never called and S400's types are
never mutated):
1. MATCH, a strict sub-class of the landed UNDERPOWERED, never a new return value of that function. microstructure_licence_inputs.py declares two constants -- `MATCH_N_MIN = N_MIN_GAMES` (imported, 30) and `MATCH_HALF_WIDTH_MAX =
   Decimal("0.01")` in Brier units, half the landed WIDTH_REFERENCE_DEFAULT scale and DECLARED, not measured -- and every other module imports both from here and re-declares neither. MATCH(cell) is true when ALL of: the landed
   verdict(ci_lo, ci_hi, n_games, 30) is "UNDERPOWERED"; n_games >= MATCH_N_MIN (not the n < n_min branch); ci_lo <= 0 <= ci_hi; (ci_hi - ci_lo) / 2 <= MATCH_HALF_WIDTH_MAX; and concentration_pass is True. The S347 all_tick overall B_brier
   cell quoted in S400_spec.md (point -0.003363, ci95 [-0.010776, +0.004000], n_games 135) is MATCH at half-width 0.007388 -- one corpus on a spent window, so unusable here.
2. microstructure_licence.py (<= 300 LOC), pure, no I/O and no clock; its LicenceDecision carries every intermediate Decimal as a string with a closed reason vocabulary. R1 CLASS: exactly one class per quote, named in the decision record --
   AHEAD routes to size_paper unchanged, MATCH here. R2 CALIBRATION: two corpora, each with a distinct well-formed 64-hex sealed prereg digest, every sealed cell MATCH, and NEVER BEHIND -- one sealed cell with ci_lo > 0, primary or
   secondary, refuses the licence; independence is asserted, not assumed, so the corpora's game-id sets must be disjoint, checked against the landed independence() shape (a shared id is NOT INDEPENDENT). R3 FEES: require_certified("refuse")
   through FeeEvidence.from_status; BOUNDED licenses zero; Polymarket stays out until the 37 S399 mismatches close. R4 STREAK: FamilyWeekLedger.streak(family) >= TARGET_WEEKS, re-read at EVERY decision, never cached; it takes the ledger,
   never an int. R5 SEAL FIRST: the S412 preregistration carries its own SHA-256 line as a committed file whose commit timestamp precedes the Monday 00:00 UTC of the earliest ISO week the streak reads; a licence sealed mid-series licenses
   nothing already counted. R6 SIZE: exactly ONE contract, then min(1, rooms.room_for(side), check_caps(...)["max_permitted_qty"]) in whole contracts, prospectively as size_paper does; zero is valid and never rounded up; no Kelly step and
   no expectation arithmetic, because MATCH says the residual is indistinguishable from zero. R7: this row neither reads nor reasons about the frozen S362 constants -- which games qualify is unchanged.
3. THE MODEL IS USED ONLY FOR SIGN-ONLY SKEW AND INVENTORY. Every licensed call passes anchor=None, so the anchor stays the observed mid. With r = p_model - p_market_mid: r > 0 adds exactly 1 cent to the ask side of the
   adverse_selection_cents pad with the bid unchanged, r < 0 the mirror, r == 0 or an absent p_model no skew; |r| never enters anything, so the skew only WIDENS the side the residual argues against and can reduce fill probability, never
   increase it. Inventory stays the landed model-free center = mid - k_inv * inv and the reduce-only flatten path; k_inv, k_sd and flatten_deadline_s are sealed constants, nothing more.
4. PRIMARY GRADE AND STOPPING. The grade is the fee-netted causal markout in probability points at 30 / 120 / 300 s from the landed summary_strict, the fee charged at the fill price inside the simulator, clustered on game_id, using the
   LANDED MEAN estimator (the direction file's "bootstrap median" is not the landed estimator; a median would be new code and a different sealed quantity), publishing largest_single_game_share and leave_one_game_out_range_units beside every
   interval; ONE primary cell (family x one horizon) is sealed with its multiplicity rule, every other cell descriptive. STOPPING: on the sealed cell, an interval whose upper bound is below zero for one ISO week that met the family floor
   (landed verdict NEGATIVE) stops quoting that family; INSUFFICIENT (under five clusters) counts as no signal and no evidence, never as absence of harm; a streak below TARGET_WEEKS stops quoting the moment the ledger says so and the family
   restarts from zero, weeks never stitched; three consecutive weeks below the floor break it; after four completed weeks a projected N that cannot reach the sealed requirement by week 8 declares UNDERPOWERED and stops, never extends; and
   no interim look happens before the 30 qualified / 30 fill-bearing floors.
5. WHAT EACH OUTCOME HONESTLY LICENSES, in the memo in these words. POSITIVE (the sealed cell's interval excludes zero from above, fee-netted, surviving the WORST queue multiplier of the S411 grid, concentration diagnostics published, on >=
   2 independent families): on this venue, in this family, over N qualified games, the fee-netted maker markout distribution had a positive clustered mean of X probability points with interval [a, b] under the declared fill model -- and,
   MATCH being true by construction, that the result did not come from calibration. It licenses no currency figure, no rate, no projection and no real-money path, only a larger paper series and an owner decision. NEGATIVE (the interval
   contains or sits below zero): an honest REJECT and a success, licensing closure of the maker channel for that family and a statement of the measured upper bound; the channel stays RED and is never massaged.
6. One test closes each false-PASS risk: an underpowered cell read as MATCH (n_games 29 with a zero-covering interval refuses; half-width 0.0101 refuses; the licence is non-increasing over a width grid); one spent window counted twice (a
   shared game id refuses with a counted reason, distinct digests being insufficient); a seal written after the first counted week (a commit timestamp at or after that Monday refuses, both printed); the fee gate downgraded (BOUNDED gives
   certified False and size zero); a streak cached (two decisions across a ledger append that drops the streak differ); skew magnitude reaching the price (over a grid of same-sign residual magnitudes the prices are identical and the skewed
   pad is never below the default); the model becoming the anchor (r == 0 reproduces the unskewed make_quotes output exactly); a BEHIND cell hidden among secondary cells; INSUFFICIENT read as "not negative" (a 4-cluster week is counted and
   never satisfies the weekly stop); a zero rounded up (a room or max_permitted_qty of 0 yields exactly 0, reason room_exhausted); and a byte-identity test over the six files named above, asserting CalibrationEvidence(verdict="MATCH", ...)
   still raises.
7. Memo docs/evidence/harness/S412_microstructure_licence_2026-09-22.md: the two declared constants, the worked S347 cell, the sealed primary cell and its multiplicity rule, the sentence that the licence is a DECLARATION (digests are
   checked for 64-hex format and distinctness only; resolving a seal to its artifact is the S395 auditor's job), and a NOT VERIFIED list naming the unmeasured across-game dispersion, zero qualified games and zero paper fills to date, the
   unvalidated half-width constant, the S411 fill-model dependence of every number here, and the pending adjudication.

CONTROLS: PREPARE only and PENDING ADJUDICATION -- nothing here is sealed, landed or wired into a runtime until the owner adjudicates decision 13; pure functions; construct tests only; no real ledger, no real result file and no archive read
by the builder (the S347 cell is quoted as literals); no network; no flag flipped; no path under data/ touched; the frozen S362 constants and S400's AHEAD rule untouched in both directions. ACCEPTANCE: per-file tests pass one at a time; <=
300 LOC per new module; ASCII; contract Q6 vocabulary (a size is a unit count; a markout is a measurement in probability points with an interval; no words for a betting advantage, gains, return on investment or the currency unit anywhere);
memo ends with NOT VERIFIED.

ADJUDICATION NOTE (2026-09-22 21:15Z, orchestrator): decision 13 is ADOPTED as this spec states it. Reasoning: without a
licence class that a MATCH verdict can satisfy, the maker paper book sizes zero forever and the program can never measure its
execution thesis; with it, a null or negative markout result is still a result, published either way. Rails that make the
adoption safe: the licence is sealed before any week counts; size is exactly one contract; the model is used only for sign-only
skew and inventory; the PRIMARY grade is fee-netted markout with the landed game-clustered mean interval; fees must be certified;
S400's AHEAD rule and the S362 bars are byte-identical. The owner may reverse this before the seal by editing this note.
