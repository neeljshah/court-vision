GAP S261 | sport all | worktree a18 | log cx_s261_ingame_headline_rederive_v2
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S211 REJECT (709e2297492d21eeae739d47ea8987708bfe0437, S211_VERIFY_2026-09-04.md). B2 FAIL: attempt 2
  removed v1 fields finite_resamples and reproduction_abs_diff without aliases and changed checkpoint_count's
  meaning (s211_headline_rederive.py:194-210,229-235); B1 FAIL: MLB's 2,458 invalid-inning and 2,246 tied rows
  were filtered before scoring 23,279 admitted paths, with neither count nor reason printed. Apply the
  verifier's exact corrections (lines 31-33).
PREMISE (step 0, INFORMATIONAL): re-open S211_ingame_headline_rederive_2026-09-04.json/csv; confirm NBA
  0.218832501/0.172353183/0.163246781 and MLB 0.248972824/0.128228347/0.127997560 (n_eff 1,313 / 23,279) still
  reproduce at max abs diff <= 1e-9; confirm s211_headline_rederive.py:71-78 still drops the 2,458 invalid-inning
  and 2,246 tied MLB rows with no count printed anywhere in the memo.
CHANGE (step 1): write the CPCV rederive to NEW filenames (S261_*), preserving every v1 field name and meaning
  (finite_resamples, reproduction_abs_diff, checkpoint_count = raw checkpoints) as additive aliases beside the
  new attempt-2 fields. The memo carries static-minus-conditional, score-only share, contribution, n_eff, exact
  public-value diffs (NBA 0.00983250084408843/0.00424678066236500; MLB 0.00797282410431543/0.00199755953257377),
  the 2,458/2,246 excluded MLB row counts with reason, and NOT REPRODUCED wherever the bar is unmet. Seal a
  prereg FIRST (own commit; seal = SHA-256 of the committed bytes above the seal line, LF, verified via
  git show HEAD), before any scoring. Never write docs/research/ or data/; no src/ kernel/ api/ intel/ edits.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per sport: static Brier, conditional Brier, delta, score-only share, prior contribution,
                  n_eff, and exact diff vs the public page value, all under CPCV with purge + symmetric embargo
  before        = NBA 0.218832501/0.172353183/0.163246781 (n_eff 1,313); MLB 0.248972824/0.128228347/0.127997560
                  (n_eff 23,279), schema fields removed and MLB exclusions unprinted (S211 attempt 2)
  bar           = v1 fields present as additive aliases; 2,458/2,246 MLB exclusions named with reason; every
                  public-value diff printed exactly; NOT REPRODUCED used wherever unmet; 0 silent field removal
  n             = 1,313 NBA game paths / 23,279 MLB game paths (n_eff), both >= 30
  eye check     = n/a (S-row); reproduction = verifier reruns cpcv_evaluate and diffs every field, alias, count
  must not move = the 1e-6 published-value bar; both v1 field names/meanings (as aliases); the CPCV fold design
NON-TAUTOLOGY: the 2,458/2,246 excluded MLB rows are named in the denominator note, not dropped from view; a CI
  covering zero is reported as the honest result, not omitted.
EVIDENCE: docs/evidence/harness/S261_ingame_headline_rederive_v2_2026-09-04.md plus JSON/CSV under new
  filenames (v1 artifacts untouched). ASCII only; calibration language only; evidence files under 50 MB.
TEST: one new per-file test (v1 field aliases present; MLB exclusion counts printed; public diffs match), run
  only that file.
REPORT: both sports' full metric set, aliases confirmed, exclusion counts, seal hashes, test line, SHA. Commit
  by pathspec, no push. NEVER PARK.
