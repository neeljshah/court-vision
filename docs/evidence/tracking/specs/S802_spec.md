GAP S802 | nba mlb nfl soccer tennis (cumulative roll-up pooled reader) | worktree: dispatcher's choice | paper-desk-improve 2026-10-09
# The S721 pooled reader skips and counts out-of-corpus sport rows instead of refusing the whole night receipt
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md A, B, Q (S-row). PAPER ONLY; calibration read-out only, no new metric, no verdict.
WHERE: local. Construct tests under tmp_path. The real-row probe reads docs/evidence/forward/scoreboard/*.json READ-ONLY (RSS cap 400 MB).

PREMISE (re-measured 2026-10-09 14:3xZ by the improve run; corrects the row text): pooled_reader.CORPUS = {mlb, nba, soccer};
the sports outside it on disk are nfl (scoreboard 2026-10-02, -04, -06 carry mlb + nfl cells) and tennis (2026-10-08 carries
mlb + nba + tennis). build_receipt (pooled_reader.py:160-166) raises unknown_corpus on the first out-of-corpus ROW inside the
per-path try, so the WHOLE receipt of that night is dropped, its in-corpus (mlb) pairs included, and the night is absent from
sources. cumulative_rollup --date 2026-10-07 therefore printed refusals {'ValueError:unknown_corpus': 1} and mlb "have 2";
nba reads have None because 10-07's nba cells have no C-and-A outcome pairs (B/C/D no_eligible_ticks), not because of CORPUS.

DESIGN (two source files, additive keys only, no schema id change, no new module):
(1) scripts/platformkit/ingame/paper_calibration_additive/pooled_reader.py (293 LOC; stay <= 300): in build_receipt, an
    out-of-corpus row is SKIPPED and COUNTED: receipt["outside_corpus"] = {sport: n_rows} (sorted; {} when none) and the
    night's source entry gains rows_outside_corpus = n. No refusal is raised or counted for it; status stays "OK" when the
    only skipped rows are out-of-corpus. Every other refusal, the duplicate / conflicting logic, the group maths, the
    _night() checks, seal handling, _rss_guard calls and the "no_paired_support" rule are byte-identical.
(2) scripts/platformkit/evidence/cumulative_rollup.py (210 LOC): pooled() carries outside_corpus through; the floor lines:
    a sport IN CORPUS with at least one read source but no group -> have 0, need 30, projected None, note
    "no C-and-A outcome pairs in <n> read receipts"; a sport OUTSIDE CORPUS -> have None, note
    "outside pooled_reader.CORPUS (rows skipped: <n>)"; the unknown_corpus note text (:92-93, :98) is replaced by these;
    the markdown "refusals" row is unchanged; one added line "Rows outside pooled_reader.CORPUS (skipped, counted): ...".
    FLOOR = 30 and FLOOR_LABEL unchanged (Q3).

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric = construct cases passing in tests/platformkit/ingame/test_pooled_reader_s802.py (new file; test_pooled_reader.py is
  at 298 LOC and is not edited) plus tests/platformkit/evidence/test_cumulative_rollup.py extended by the roll-up cases.
  before (master): case (a) -> refusals {"ValueError:unknown_corpus": 1}, sources [], groups [].
  bar = 6 of 6 pass; these files green one per process with no existing assertion edited: tests/platformkit/ingame/
  test_pooled_reader.py, test_pooled_reader_round5.py, tests/platformkit/evidence/test_cumulative_rollup.py,
  test_coverage_receipt.py, tests/platformkit/evidence/test_cumulative_rollup_night.py if it exists.
  n = 6 (CONSTRUCT):
   (a) one receipt with mlb pairs + nfl rows: status OK, refusals {}, one mlb group with the mlb games, outside_corpus
       {"nfl": k}, the source carries rows_outside_corpus k and eligible_pairs as _night() counted them (unchanged).
   (b) a receipt holding ONLY out-of-corpus rows: source listed, groups [], outside_corpus counted, refusals
       {"no_paired_support": 1} (unchanged rule), status ATTENTION.
   (c) two receipts whose mlb rows duplicate / conflict exactly as in the existing duplicate test, one of them also holding
       tennis rows: duplicate_receipts and conflicting_receipt counts equal master's for the same mlb rows.
   (d) an all-in-corpus input: the receipt equals master's receipt except for the two added keys (outside_corpus {}, each
       source rows_outside_corpus 0) -- compare by deleting those keys.
   (e) roll-up floors: nba in CORPUS, sources read, no nba group -> have 0 / need 30 / projected None with the "no C-and-A
       outcome pairs" note; nfl -> have None with the "outside pooled_reader.CORPUS (rows skipped: n)" note.
   (f) roll-up markdown: the refusals row absent when refusals are {}, and the new "Rows outside" line present with counts.
  eye check = n/a (S-row). reproduction = REAL-ROW PROBE, read-only: pooled_reader.build_receipt over every
  docs/evidence/forward/scoreboard/2026-*.json (non-PREREG) on master vs the candidate, psutil RSS cap 400 MB; report per
  version: refusals, sources count, mlb n_games per seal group, outside_corpus. Expected: master refusals carry
  unknown_corpus with sources missing the nfl / tennis nights; candidate refusals without it, those nights in sources,
  mlb n_games >= master's. The numbers go in the memo; none is a verdict.
  must not move: CORPUS, FLOOR, FLOOR_LABEL, SCOPE text, the schema string s721.descriptive.v1, every committed cumulative
  receipt (the roll-up is not re-run into docs/ by this row), seal-pinned files (none touched).
NON-TAUTOLOGY: reverting hunk (1) turns (a) red (refusal returns); reverting hunk (2) turns (e) red.
OUT OF SCOPE: adding nfl / tennis / soccer_intl corpus mappings (S721 prereg decision); the 0-byte qualification leftovers
(09-30, 10-01: an issue, never git-added); re-running the roll-up into docs/evidence/forward/cumulative/.
NOT VERIFIED at spec time: the per-night outside-corpus row counts; whether any other reader keys on "unknown_corpus"
(grep before building; a hit outside cumulative_rollup.py is a B2 check for the verifier).

AMENDMENT 1 (2026-10-09 14:5xZ, improve run, BEFORE the fix round; binding): two existing assertions pin the whole-receipt
refusal this row removes by design, so the bar "no existing assertion edited" is replaced for exactly these two sites and
nothing else (the verifier rejects any other edited assertion):
  (i) tests/platformkit/ingame/test_pooled_reader.py:253-264 test_refused_source_never_contributes_rows (nfl row beside the
      mlb REAL_ROW): rename to test_out_of_corpus_row_is_skipped_and_counted; line 263 becomes
      `assert len(receipt["sources"]) == 1 and receipt["outside_corpus"] == {"nfl": 1}`; line 264 becomes
      `assert [g["sport"] for g in receipt["groups"]] == ["mlb"] and receipt["refusals"] == {}`. ZERO net lines (298 LOC).
  (ii) tests/platformkit/evidence/test_cumulative_rollup.py:66-70 test_out_of_corpus_row_keeps_the_floor_line: line 70 becomes
      `assert mlb and mlb[0]["have"] == 1 and nfl and nfl[0]["have"] is None and "rows skipped" in nfl[0]["note"]` with
      `nfl = [f for f in floors if f["sport"] == "nfl" and f["floor"] == cr.FLOOR_LABEL]` added on the line before (+1 line).
  The real-row probe found only 10-06 refused on master (10-02 / 10-04 / 10-08 hold no out-of-corpus OUTCOME row with both
  arms A and C, so master already read them); rows_outside_corpus counts the rows build_receipt iterates (outcome rows with
  arms A and C), not every paired row of that sport -- the memo states this and the key's docstring / comment must say so.

AMENDMENT 2 (2026-10-09 15:1xZ, post-landing disclosures by the improve run): LANDED c479e1693 + e432e842a (both tiers ACCEPT).
- Coverage gap (adversarial M6): no enumerated case checks that receipt["outside_corpus"] is summed across sources; a mutant
  keeping only the last source's counts passes 16 of 16. A follow-up adds case (g): two sources with nfl rows -> the sum.
- rows_outside_corpus counts only the rows build_receipt iterates (outcome rows with arms A and C): 10-04's 380 nfl mid-target
  rows read as 0 skipped and the nfl floor note then says "rows skipped: 0" on such a night. Documented, not changed.
- cumulative_rollup.build() shells out to `git -C <root> ls-tree` (cumulative_rollup_night.tracked()); a read-only probe of
  build() on the real tree must stub tracked().
- Measured on the real tree (read-only): master 8 sources / mlb 2 games under seal 6abb1a851628; candidate 9 sources / 4 games;
  outside_corpus {nfl: 789}; 10-08's 48 tennis cells carry no paired rows (tennis "rows skipped: 0").
- Memo LOC lines are stale by one (pooled_reader.py 298, test_cumulative_rollup.py 159 at HEAD); both under 300.
