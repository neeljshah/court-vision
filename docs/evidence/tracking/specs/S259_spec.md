GAP S259 | sport all (in-game) | worktree a16 | log cx_s259_ingame_power_audit_v2
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S210 CLOSED AT LIMIT (see its register row; attempt 1 was a store-visibility artefact). Attempt 2b was
  rejected on exact points: S102 counted at n=1,926,350 where its memo specifies 192,635 per hypothesis; S94
  labelled NO SERIES ARCHIVED although its differential IS archived (S94 memo line 201); the source patterns omit
  qualifying S84 (numeric in-game improvement + 95 pct CI, S84 memo line 126) and self-include the S210 output;
  the JSON filter field was removed and screen semantics renamed without aliases. This row applies that diff.
PREMISE (step 0, INFORMATIONAL): print the grep over docs/evidence/harness/ for every in-game screen memo carrying a
  numeric improvement AND a CI (all in-game and CI spellings), the file list, and the count; reproduce the two S210
  premise anchors (S82 MDE80 0.0075 vs the +0.004 bar; S117) at max abs diff <= 1e-9.
CHANGE (step 1, the verifier's CORRECTION verbatim): broaden source discovery to all in-game and CI spellings;
  exclude the S210/S259 output memos from the denominator; correct the S102 denominator to 192,635 per hypothesis;
  label S94 as archived and audit its series; restore the filter field and stable screen IDs (memo stems only as
  an additive alias); regenerate the asserted manifest. Read-only auditor <= 300 LOC under
  scripts/platformkit/eval_gate/; it writes no verdict into any existing artifact. Seal a prereg FIRST (own commit;
  seal = SHA-256 of the committed bytes above the seal line, LF, verified via git show HEAD).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per screen: n_ticks, n_game_clusters, n_eff (unequal-cluster correction as in
                  scripts/platformkit/ingame/gap_effective_n.py), observed improvement, CI half-width, the 80 pct-
                  power minimum detectable Brier delta, and UNDERPOWERED / REFUTED-AT-BAR vs the frozen +0.004 bar
  before        = S210 attempt 2b table (rejected): 17 screens claimed, grep showed 29; S84 absent; S102 n wrong
  bar           = every screen in the printed grep list appears with all seven quantities or an explicit
                  NO SERIES ARCHIVED reason (S94 must be audited, not excused); S84 present; S102 at 192,635 per
                  hypothesis; 0 screens silently omitted; the two anchors reproduce at <= 1e-9
  n             = the enumerated screen count (CONSTRUCT; exhaustiveness proved by the printed grep + file list)
  eye check     = n/a (S-row); reproduction = verifier reruns the grep, matches the list, recomputes MDE for three
                  rows chosen EVENLY across the sorted table
  must not move = every existing memo and artifact byte-identical; the +0.004 bar; every eval_gate threshold;
                  backtest_fwer.jsonl untouched, K unread; the prior S210 JSON schema (filter, screen IDs) kept
NON-TAUTOLOGY: a finding that most standing NULLs are UNDERPOWERED is expected and reported as such.
EVIDENCE: docs/evidence/harness/S259_ingame_power_audit_v2_2026-09-04.md + JSON manifest (new filenames).
TEST: one new per-file test (S84 present, S102 denominator, S94 archived, filter field), run only that file.
REPORT: the table, the grep count, the anchors, seal hashes, test line, SHA. ASCII only; no push. NEVER PARK.
