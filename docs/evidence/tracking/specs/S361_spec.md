GAP S361 | sport tennis | worktree harness-h19 (master-based) | log cx_s361_tennis_inplay_model
# Tennis in-play win probability by exact score recursion (the largest modelling gap with data already on disk)

SINGLE PROBLEM: the coverage census (docs/evidence/ingame/S348_coverage_tennis_2026-09-21.json) shows tennis has a price series
(1,854,100 rows / 986 matches, 2026-05-22..2026-07-08) and 6.9M state rows, but NO in-play model and NO joined scoring corpus.
inplay_capture_loop.py lists tennis as capture-only (no_model_prob). Astra round 8 named the right object: tennis = EXACT RECURSION.

BINDING BEFORE-CONDITION (re-run, quote): `ls scripts/platformkit/ingame/tennis_point_recursion.py` fails;
`grep -n "_MODEL_SPORTS" scripts/platformkit/ingame/inplay_capture_loop.py` shows tennis absent.

CHANGE (NEW files only; pure math + parsing, no network, no data writes):
1. scripts/platformkit/ingame/tennis_point_recursion.py (<= 300 LOC, stdlib only, exact rational or float arithmetic with
   memoization; deterministic):
   - `p_game(p_serve_point, server_points, returner_points)` incl. deuce closed form;
   - `p_tiebreak(p_a_serve, p_b_serve, a_pts, b_pts, a_serving_next, first_to=7)` with the ABBA serve rotation, and a match
     tiebreak (first_to=10) variant;
   - `p_set(...)` from any game score incl. 6-6 tiebreak or advantage-set flag; `p_match(...)` for best-of-3 and best-of-5 from
     any (sets, games, points, server) state, with a final-set rule parameter (tiebreak at 6-6 / match tiebreak / advantage);
   - `match_win_prob(state, p_a_serve, p_b_serve, rules)` = the public entry point; state = sets_a, sets_b, games_a, games_b,
     points_a, points_b, server ("a" | "b"), in_tiebreak.
   - `serve_probs_from_prematch(p_match_prior, rules, base_hold=0.64)` inverts the recursion: the pair (p_a_serve, p_b_serve)
     symmetric around base_hold whose START-OF-MATCH win probability equals a pre-match prior (monotone bisection; state the
     identifiability assumption: only the DIFFERENCE is identified by one prior, the level base_hold is a declared constant whose
     source is cited in the memo as a public tour-level average and flagged ASSUMPTION).
2. scripts/platformkit/ingame/tennis_state_parse.py (<= 200 LOC): parse the state shapes actually present in the repo's tennis
   ingestion (read domains/tennis/ingest_espn.py and any tennis live-state module for the field names; per-set game scores only
   is the COARSE shape -- when point scores and server are absent, return a state with points 0-0 and server unknown, and the
   model averages over the two possible servers; say so) into the recursion state; unknown or inconsistent -> None with a reason.
3. tests/platformkit/ingame/test_tennis_point_recursion.py: closed-form checks (p_game at p = 0.5 is 0.5; deuce formula; symmetry
   p(state for a) + p(mirrored state for b) = 1; monotone in p_serve; a won match returns 1 / 0 exactly; tiebreak serve rotation;
   best-of-5 vs best-of-3; final-set rules), the prior inversion round-trips to 1e-9, server-unknown averaging, parser fixtures.
4. Memo docs/evidence/harness/S361_tennis_inplay_model_2026-09-21.md: the model, its assumptions (i.i.d. points on serve, fixed
   serve probabilities within a match), what a later scored row must do (join to the price series, walk-forward by match date,
   four arms vs the contemporaneous mid, sealed prereg first), and a NOT VERIFIED list.

CONTROLS: PREPARE only; no probability is compared with any price or outcome in this row. ACCEPTANCE: per-file test passes;
`python -m scripts.platformkit.ingame.tennis_point_recursion` prints a self-check line; diff = NEW files only. Vocabulary follows
contract Q6; automated scan required; assemble retracted-figure literals from single digits. The pod is OFF.
