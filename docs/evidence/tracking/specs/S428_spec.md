GAP S428 | sport all captured | worktree harness-h85 (master-based) | log cx_s428_weekly_record
# Weekly record page: the published forward series per family and ISO week, zero weeks included (DIRECTION section 5 item 6, section 7 Session G)
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- self-check A9, B1-B11, Q1-Q9, S1, S2, S4 before reporting; template docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md.
WHERE (S1): local, small -- reads one ledger, one families file and a few KB of markout JSON per week, writes two text files; no pod, no network, no GPU. SINGLE PROBLEM: evidence 6 is the markout series "published weekly from week one, zero weeks included"; nothing renders the landed ledger or a markout summary.
BINDING BEFORE-CONDITION (S2, verified on master 4f66acfb5): (a) scripts/platformkit/execution/family_week_ledger.py:18 `TARGET_WEEKS = 8`; :58 `__init__(self, path, families_path, *,
as_of=None)`; :91-94 row fields (iso_year, iso_week, family, sport, game_ids, qualified_game_ids, fill_bearing_game_ids, qualified_games, fill_bearing_games, exclusions,
capture_gap_seconds, source_artifact_path, source_sha256) plus `declarations_sha256` stamped at :158; :129-130 an absent ledger returns []. COMPLETION IS NOT A FIELD: a week is
completed when its ISO Monday precedes the as_of week's Monday -- :137-138 records() silently SKIPS a later row, :152-153 append raises "only completed ISO weeks may be appended".
:164-173 streak(family) counts consecutive completed weeks with qualified_games >= the DECLARED weekly_floor (:166, from the families file, validated >= 1 at :70) ending at the
week before as_of -- one number per family per as_of, not per row. :175-188 independence(iso_year, iso_week) gives per pair "MISSING EVIDENCE" | "NOT INDEPENDENT" | "DECLARED
INDEPENDENT" with shared_game_ids. :190-203 forecast() prints a completion date -- a projection, NEVER called. (b) forward_replay_qualification.py:21 `WEEK_GAMES, SPORT_GAMES,
FILL_GAMES = 4, 30, 30`. (c) docs/evidence/forward/families_maker_forward.json: five families maker_forward_{mlb,nfl,tennis,nba,soccer}, weekly_floor 4 each. (d) markout_causal.py:7
"Pure constructs: no writes or data access."; :182-266 summary_strict RETURNS {n_intents, n_fills, n_scored, n_float_field_lossy, n_unscored, n_fill_horizon_observations,
n_unscored_by_reason, units "probability_points", cluster_key, horizons{str(h): {n, n_clusters, mean_units, ci_95_units [lo, hi], verdict, leave_one_game_out_range_units,
largest_single_game_share, delay fields}}}; :24 horizons (30.0, 120.0, 300.0); :239-243 zero scored -> INSUFFICIENT with null mean and interval; :246-247 verdict INSUFFICIENT |
POSITIVE | NEGATIVE | INDISTINGUISHABLE; entry_timing/study.py:37-38 fewer than five game clusters -> (None, None) -> INSUFFICIENT (decision 13: no signal, never absence of harm).
(e) webapp/scripts/verify-public-json.mjs:10-14,27-28 checks ONLY browser-parseable JSON with no non-finite number; check-analytics-copy.mjs:5 PROHIBITED_TOKEN_RE and :11
DATA_TARGETS (public/data/forward not scanned today). (f) ZERO WEEKS TODAY: no week ledger file is tracked or under data/ (git ls-files + find, 2026-09-24); the only daily
artifact is docs/evidence/forward/qualification/2026-09-22.json (six MLB games, 0 qualified).
FALSE PREMISES IN THE ASK (binding record): markout_causal writes NO artifact, so no landed summary_strict output file exists; verify-public-json.mjs has no scrubbing or receipt rule.
CHANGE (owned: NEW scripts/platformkit/execution/weekly_record.py <= 300 LOC, NEW tests/platformkit/execution/test_weekly_record.py, the two outputs, the memo; NO landed module
edited): `python -m scripts.platformkit.execution.weekly_record --ledger <path> --families docs/evidence/forward/families_maker_forward.json --markouts <dir> --as-of <UTC instant>
--out-md docs/evidence/forward/WEEKLY_RECORD.md --out-json webapp/public/data/forward/weekly_record.json`.
1. Rows come ONLY from FamilyWeekLedger(ledger, families, as_of).records(); streak() and independence() are the ONLY arithmetic (no parallel implementation).
2. MARKOUT INPUT CONTRACT (new; none is landed): <markouts>/<iso_year>-W<ww>_<family>.json = the summary_strict return dict verbatim, key set and horizons "30.0"/"120.0"/"300.0"
   validated; a file whose (week, family) is not a completed ledger row REFUSES the run (exit 3, nothing written); a completed week without a file renders NULL in every markout cell.
3. Per family one table, one row per completed week ascending: iso week, qualified_games, fill_bearing_games, per horizon mean_units + ci_95_units + verdict (INSUFFICIENT and nulls
   verbatim), largest_single_game_share and leave_one_game_out_range_units where present; then streak() once; then independence() per rendered week (NOT INDEPENDENT, MISSING
   EVIDENCE verbatim); then the bars WEEK_GAMES, SPORT_GAMES, FILL_GAMES, TARGET_WEEKS (imported) and each weekly_floor (read). Zero weeks: header, bars, "0 completed weeks as of <as_of>".
4. PROVENANCE block: full path, byte size and sha256 of every input opened (ledger or "absent", families file, each markout file, the two bar modules) (A9).
5. REFUSE (exit 3, no output) any input label or field (family, sport, exclusion reason, unscored-reason key) matching a currency token ($, USD, cent, the full currency word) or the
   ported check-analytics-copy.mjs:5 PROHIBITED_TOKEN_RE. Never a currency figure, a rate or a projection; no wall clock (as_of only).
6. ASCII, LF, sort_keys, atomic tmp + os.replace; JSON = the same content (null for NULL, finite numbers only) so verify-public-json.mjs and PROHIBITED_TOKEN_RE pass; adding
   public/data/forward to DATA_TARGETS and any page belong to the site lane, not this row.
ACCEPTANCE RULE: metric = enumerated construct cases passing; before = 0 (module absent); bar = all 8 pass; n = 8 (CONSTRUCT): zero weeks; one completed week with a full artifact;
  INSUFFICIENT markout; an incomplete (current-week) row not rendered and its markout file refused; a NOT INDEPENDENT pair surfaced; two renders byte-identical; provenance sha256
  equals the file; a currency token in an input label refused, not rendered. eye check = n/a (S-row); reproduction = rerun the CLI on the fixtures, diff both outputs byte-for-byte.
  must not move = family_week_ledger.py, markout_causal.py, forward_replay_qualification.py, families_maker_forward.json byte-identical to master (B10, Q3).
FIRST REAL RENDER (orchestrator, local, after land): --ledger at the S390 durable path (absent today) -> must print "0 completed weeks as of <as_of>". DO NOT: no words for a betting advantage, gains, return on investment or a currency unit anywhere (Q6); no forecast(); no bar restated as a literal; commit by pathspec only.
MEMO: docs/evidence/harness/S428_weekly_record_2026-09-24.md (inputs with sha256, the 8 cases, the first-render output) ending with NOT VERIFIED.

AMENDMENT 1 (2026-09-24 19:3xZ; binding; round 1 on the codex build (53 tests, 8 of 8 cases): codex gpt-5.6-sol ACCEPT; Opus tier 2 ACCEPT WITH CORRECTIONS): (a) CORRECTION at landing: the rendered outputs committed by the lane carry the worktree's absolute path in their provenance block; the orchestrator re-renders WEEKLY_RECORD.md and webapp/public/data/forward/weekly_record.json from the MAIN tree after the code lands (the FIRST REAL RENDER) and commits those; the lane's renders are not landed. (b) recorded, non-blocking NEW GAPs for later rows: the ported site regex treats underscore as a word character, so labels such as maker_forward_payout would pass both this row and the site check (shared with the site lane); source_artifact_path is excluded from the label check but rendered into the public JSON; a POSITIVE verdict with a negative lower bound is not cross-checked against its interval; stray non-.json files in the markouts directory are ignored silently; the md and JSON are replaced one at a time, so a failure between the two can leave outputs from different renders (disclosed in the memo).
