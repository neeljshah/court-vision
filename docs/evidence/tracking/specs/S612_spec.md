GAP S612 | mlb nfl (D1 writer team-code link) | worktree nba-harness-h302 | builder: readiness lead (Opus; codex down)
# The D1 writer resolves venue team codes per sport so TB/KC/WSH/SF/SD/AZ (MLB) and WAS/JAC (NFL) games can be served, with the home ticker oriented by the SAME resolved code

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md A, B1-B11, Q1-Q9 (S-row). PAPER ONLY.

BEFORE (MEASURED 2026-09-30 01:3xZ from the 7 tracked D1 census files, docs/evidence/forward/schedules/*_full_selection.json.census.json):
- 16 MLB games were refused missing_directional_team_evidence. In each one, our codes {alias(mlb, x)} differ from the Kalshi ticker-suffix code set ONLY by the live_board._MLB_ABBR alias (live_board.py:55): ours TAM/KAN/WAS/SFG/SDG/ARI against Kalshi TB/KC/WSH/SF/SD/AZ. The raw statsapi abbreviation equals the Kalshi code in every case.
- One further refusal (CHC@BOS 09-26) has no Kalshi set at all and is out of scope.
- 0 of 33 served-candidate MLB rows involve those six clubs.
- The R3 rehearsal D1(2026-10-01) refused CHC@SD G2 (02:00Z 10-01) for this reason.
- NFL: ALIASES['nfl'] is empty (game_market_link.py:27) while ESPN WSH/JAX meet Kalshi WAS/JAC (open events KXNFLGAME-26OCT04INDWAS, -26OCT04JACCIN).
- Mechanism, forward_schedule_writer._choose (:129-165):
  - Kalshi book rows carry no directional abbreviations, so link_game returns missing_directional_team_evidence.
  - The team_set fallback needs `entry["team_codes"] == {alias(home), alias(away)}`, which fails.
  - The home ticker is chosen by `team_code_from_ticker(t) == alias(sport, home)` with a LEXICAL fallback. Resolving only the set would therefore orient the served ticker to the wrong team (e.g. -CHC for an SD home game). The home match must use the same resolved code.

CHANGE (owned):
- NEW scripts/platformkit/execution/forward_schedule_codes.py (<= 80 lines) exposing `resolve(sport, home, away, index, local_day) -> tuple[set[str], str]` (pure: it never calls parse_ticker_date and never touches metrics or counts, so every census counter stays byte-identical; _choose's existing team_sets comprehension keeps its own parse_ticker_date filter).
  - The candidate codes for a team abbr are {alias(sport, abbr), abbr.upper(), EXTRA[sport].get(abbr.upper())} minus None, with EXTRA = {"nfl": {"WSH": "WAS", "JAX": "JAC"}}.
  - The DEFAULT pair is (alias(home), alias(away)).
  - If some index entry with entry["date"] == local_day has team_codes == the default set, return (default set, alias(home)). This leaves every currently-linking game byte-identical.
  - Otherwise, collect every (h, a) with h != a from the candidate products that equals some such event's team_codes.
    - Exactly one distinct pair: return ({h, a}, h).
    - More than one distinct pair: raise ValueError("ambiguous_team_codes").
    - None: return the default (so the landed refusal reasons are unchanged).
- MODIFIED scripts/platformkit/execution/forward_schedule_writer.py:
  - `_choose` takes `codes, home_code = resolve(...)` in place of `codes = {alias(sport, home), alias(sport, away)}`.
  - The home-ticker match uses `home_code` in place of `alias(sport, home)`.
  - No other line changes. The file stays <= 300 lines. Soccer (soccer_choose) is untouched.
- NEW tests/platformkit/execution/test_s612_team_codes.py (<= 300 lines):
  - (a) REAL-ROW FIXTURES built from the committed census refusal evidence: the Kalshi team-code sets, plus tickers built as <event>-<code>. For each of TB, KC, WSH, SF, SD and AZ as home and as away, _choose links the event AND returns the home-code ticker (never the lexical fallback).
  - (b) NFL IND@WSH and JAX@CIN link to KXNFLGAME-26OCT04INDWAS (home -WAS) and KXNFLGAME-26OCT04JACCIN (home -CIN).
  - (c) Unchanged: a game whose aliased codes already match (e.g. BOS@NYY, CWS@HOU with alias CHW->CWS) returns the identical tuple to the landed _choose, loaded from the pinned base sha via git show.
  - (d) The NYY-TB doubleheader (two events with one set) still refuses ambiguous_doubleheader.
  - (e) A constructed case where the aliased and raw pairs both match different events refuses ambiguous_team_codes.
  - (f) Test power: reverting the home-code line to alias(sport, home) makes (a) fail on the SD/TB home cases.

INVARIANTS:
- game_market_link.py and live_board.py are NOT edited. game_market_link.py is an S490 dependency file under the IDENTITY FREEZE, and live_board is shared.
- Every game that links today links identically.
- No new link is made without a unique exact team-code-set match on the same local date.

REAL-ROW PROBE before verify: schedule_d1 --sports mlb,nfl with the tick argv into a scratch out-dir (no pointer), under a 512 MB guard, on both the base code and the candidate.
- The candidate D1(2026-10-01) must equal the base plus CHC@SD G2 with ticker KXMLBGAME-26SEP302200CHCSD-SD. Every other row must be byte-equal once selected_at is excluded.

LANDING: before 11:30Z 2026-09-30 if possible, so D1(10-01) at 12:00Z serves CHC@SD G2; hard deadline before 12:00Z 10-02 (D1(10-03), the Rays-hosted ALDS G1). Stay outside the RAM windows.

AMENDMENT 1 (PRE-BUILD, 2026-09-30 ~01:5xZ; Opus critic in the astra role, VERDICT REVISE; binding). Folded:
(A) BEFORE COUNT CORRECTED. The tracked census files hold 19 MLB refused_team_evidence rows: 09-22 4, 09-23 4, 09-24 2, 09-25 3, 09-26 5, 09-30 1. That is 18 alias refusals plus CHC@BOS 09-26, which has no Kalshi set. The files are the 7 non-superseded docs/evidence/forward/schedules/2026-09-2x*census.json (the 09-22 one is named _maker_forward). The premise is confirmed: MLB abbreviations come from statsapi teams.*.team.abbreviation (forward_schedule_sources.py:18, :59-60), and the raw code equals the Kalshi suffix in every alias refusal.
(C) NFL DESCOPED. Downstream NFL orientation keeps ALIASES['nfl'] empty, so ESPN WSH meets ticker WAS and every WSH/JAX row would raise orientation_unresolved (ingame_scoreboard_rules _mid / ticker_outcome / is_home_ticker; settlement_witness_orient._codes:17). Serving such rows would spend capture capacity on NFL Sunday on games that can never be scored or settled. S612 is therefore MLB ONLY: EXTRA = {} and no NFL case. The NFL WAS/JAC gap becomes a separate row that fixes the writer and the downstream alias together after the IDENTITY FREEZE.
(D) DEFENSIVE REFUSAL. When the resolved home_code differs from alias(sport, home) and no linked ticker has home_code, raise ValueError("home_ticker_unresolved") instead of the lexical fallback. Only non-default paths reach it, so byte-identity holds. The file stays <= 300 lines.
(E) DISCLOSED REASON CHANGES for games that are still refused.
  - A game whose resolved pair matches two same-day events now refuses ambiguous_doubleheader instead of missing_directional_team_evidence. It then leaves the refused_team_evidence block, because forward_schedule_writer.py:248 writes that block only for missing_directional_team_evidence and team_code_set_mismatch. Real example: 09-22 TB@NYY G1/G2 (KXMLBGAME-26SEP221305TBNYYG1, ...221905TBNYYG2).
  - When book rows carry directional abbreviations and link_game matches, the post-link team_code_set_mismatch check (:160) now passes on a unique resolved set. The same unique-set rule applies.
  - INVARIANTS add: a new link requires a unique exact team-code-set match on the same local date, with the home ticker matched by the resolved home code.
(B) TESTS (e)/(e2).
  - (e): two NON-default candidate pairs each exactly match a different event on local_day, with no default match, so the result must be ambiguous_team_codes. Example: SD home vs TB away with events {SD,TAM} and {SDG,TB}.
  - (e2): the default pair and a raw pair both match different events. The result must return the DEFAULT and link exactly as the base does.
  - (f) gains a mutant: resolve without default-first must fail (e2).
(F) FIXTURES. (a) uses the REAL census rows:
  - home: SF 823168 vs MIN, KC 824060 vs CWS, WSH 822681 vs NYM, SD 849843 vs CHC;
  - away: TB 823492 at NYY, WSH 824223 at DET, AZ 824298 at COL.
  - Tickers are built as <event>-<code> from compared_team_code_sets, with event ids taken from that census row.
  - TB home and AZ home are CONSTRUCTED (labelled). Kalshi event ids use the same date+codes pattern.
  - (d) uses the real 09-22 TB@NYY G1/G2 pair: assert ambiguous_doubleheader.
(G) PROBE EXPECTATIONS. The candidate D1(2026-10-01) must equal the base plus CHC@SD G2 (KXMLBGAME-26SEP302200CHCSD-SD, rule home_alias, link_path team_set). In the census, mlb linked/written rise by 1 and missing_directional_team_evidence falls by 1. The CHC@SD key leaves refused_team_evidence. Nothing else differs.

AMENDMENT 2 (build round, 2026-09-30 ~02:0xZ; binding). The owned list gains ONE MODIFIED test, tests/platformkit/execution/test_forward_schedule_team_set.py::test_refused_census_lists_exact_venue_and_compared_codes.
- That test pinned the landed defect: a construct SF@NYY with Kalshi codes {NYY, SF} was expected to refuse.
- It now asserts that the game links with the -SF home ticker, and that only TB@BOS (no Kalshi event) stays refused, with its exact evidence block unchanged.
REAL-ROW PROBE (MEASURED 01:35Z): schedule_d1 --sports mlb,nfl with the tick argv on the base (main, S611) and on the candidate.
- The candidate D1(2026-10-01) equals the base plus KXMLBGAME-26SEP302200CHCSD-SD (game 849842, link_path team_set, rule home_alias); every base row is byte-equal once selected_at is excluded.
- mlb census deltas are exactly the expected ones: linked/written 1->2, canonical_rules home_alias 1->2, missing_directional_team_evidence 1->0, and the 849842 evidence block leaves refused_team_evidence.
- future_records/ignored_record_type differ only because the live archive grew between the two runs, 37 s apart.
- Peak 89-90 MB, wall 29-38 s.

AMENDMENT 3 (fix round 1, 2026-09-30 ~02:3xZ; binding). Contract tier r1 ACCEPT. Adversarial tier r1 ACCEPT: a 6,000-case seeded differential fuzz found 0 divergences wherever the base linked; 170 new MLB links, every one oriented to the home team's own code on a unique same-date set; downstream orientation passed for TB/KC/WSH/SF/SD/AZ as home and as away in _mid, is_home_ticker, live_shadow_quoter._orientation and settlement_witness_orient._codes. Folded:
- The orientation mutant test now asserts home_ticker_unresolved, and that the unguarded revert serves the wrong -CHC ticker via lexical_fallback.
- One assert: nba/wnba resolve returns the default aliased pair even when a raw-code event exists (N4).
DISCLOSURE (E) EXTENDED:
- Same-club games may move from no_team_codes to ambiguous_team_codes.
- One construct moved from team_code_set_mismatch to ambiguous_home_ticker.
- The byte-identical counter claim holds for games that LINK. For base-refused MLB games whose raw pair matches a same-day event with an unparseable ticker month, _choose's team_sets filter can add ticker_date_parse_errors. Real Kalshi tickers carry valid months.
- home_ticker_unresolved is unreachable while team_codes derive from the event's own tickers; it is kept as a defensive guard.
