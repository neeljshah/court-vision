VERDICT: PARTIAL -- both rules land and every test passes on this tree as-is, but step 3(e) holds only after ONE existing test's SETUP was re-expressed (named below). Eye check: NONE, as the spec says.
Row S319, worktree a22, LOCAL only (no pod, no GPU). Prereg sealed and committed ALONE first: `fd00b430f`, `docs/evidence/harness/S319_preregistration_2026-09-08.md`, `SEAL sha256 6583456965bd3ea92b245e70d6dc42c27e7a77dfbb153d9e9c4a560edaa11a8b`.
Changed: `receipt_guard.py` (140 -> 236 lines), a new sidecar JSON, a new test file, one test setup. 0 ledger rows written or rewritten, 0 landed memos edited, `resolver_registry.py` unchanged at 1320 lines (allowlist 1323).
## PREMISE (step 0) -- TRUE, both refusals printed. n = 4 receipt-bearing rows naming 6 receipts
Scratch copy of the ledger and its 6 receipts; the LANDED guard run against it (P0 control, untouched copy: no refusal).
P1 (`S293_tail_metric_rail_attempt2_2026-09-07.md` rewritten CRLF -> LF, 16936 -> 16651 bytes, content identical):
  `receipt validation refused this answer -- the receipt docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07.md no longer hashes to the 288635e41b242dad685156a5f814351bd025228e63801947cdf1a955c72b606d row 's293_tail_log_loss_rail' names. No number is composed from a receipt that did not verify.`
P2 (same file, bytes unchanged, mtime advanced 14400 s past the ledger):
  `receipt validation refused this answer -- stale: the ledger domains/basketball_nba/knowledge/validation_ledger.jsonl is older than its required input docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07.md, so the as-of of this answer would outrun the receipt it derives from. No number is composed from a receipt that did not verify.`
The SAME two probes against the new guard: 0 refusals, both accepted. On an LF tree with UNIFORM mtimes (the pod / `git archive -c core.autocrlf=false` condition) all 6 verify, every one by rule `sidecar_lf`.
## Receipt hash table -- n = 6 of 6 named receipts, exhaustive (16-char prefixes)
| receipt | raw digest | LF digest | recorded | matched before | matched now |
|---|---|---|---|---|---|
| S296_full_boxscore_oof_2026-09-07.md | ed618ec301b8edbf | ca797942754f55a6 | ed618ec301b8edbf | raw (CRLF tree only) | sidecar_lf |
| S310_tail_beta_offset_2026-09-07.md | 7713397fc16d2361 | b94218e81271b57b | 7713397fc16d2361 | raw (CRLF tree only) | sidecar_lf |
| S312_spec.md | 816350ba70fde99f | 8b46b4d3b2adb42b | 816350ba70fde99f | raw (CRLF tree only) | sidecar_lf |
| S314_teach_packet_qualification_2026-09-07.md | 9117329d4361514b | 9c6132f221a0ddf5 | 9117329d4361514b | raw (CRLF tree only) | sidecar_lf |
| S293_tail_metric_rail_attempt2_2026-09-07.md | 288635e41b242dad | b171c8658441a62e | 288635e41b242dad | raw (CRLF tree only) | sidecar_lf |
| S293_tail_metric_rail_attempt2_2026-09-07_summary.json | f8c40d3d46d9ff1d | 7714ea02d95e6482 | f8c40d3d46d9ff1d | raw (CRLF tree only) | sidecar_lf |
All 6 recorded digests were sealed over CRLF bytes, so 6 of 6 differ from the LF digest and 6 of 6 sidecar entries were needed (`docs/evidence/harness/S319_receipt_hashes_2026-09-08.json`, keyed BY THE RECORDED DIGEST and never by path, so a row quoting an altered digest still refuses). Acceptance order: `lf`, then `sidecar_lf`, then legacy `raw`; binary extensions are `raw` only.
## Per-receipt date table -- n = 6 of 6, exhaustive
| receipt | structured `run_utc`/`generated_at`/`as_of` field | latest ISO date it records | row date (`run_ts`) | branch | outcome |
|---|---|---|---|---|---|
| S296_full_boxscore_oof_2026-09-07.md | NONE | 2026-09-07 | 2026-09-08 | recorded dates | accepted |
| S310_tail_beta_offset_2026-09-07.md | NONE | 2026-09-07 | 2026-09-08 | recorded dates | accepted |
| S312_spec.md | NONE | 2026-09-07 | 2026-09-08 | recorded dates | accepted |
| S314_teach_packet_qualification_2026-09-07.md | NONE | 2026-09-07 | 2026-09-08 | recorded dates | accepted |
| S293_tail_metric_rail_attempt2_2026-09-07.md | NONE | 2026-09-07 | 2026-09-08 | recorded dates | accepted |
| S293_tail_metric_rail_attempt2_2026-09-07_summary.json | NONE | 2026-09-07 | 2026-09-08 | recorded dates | accepted |
0 of 6 carry a structured date field, so 6 of 6 fall to the latest-ISO-date rule (an artifact cannot predate the newest date it names, so the fallback errs toward refusing, never toward accepting). 0 of 6 reach the mtime fallback. All 4 rows record `run_ts`; none records `as_of` or `date`.
## Tests (each file alone, `-p no:cacheprovider`, on the tree AS-IS -- no line-ending or mtime repair by hand)
`tests/platformkit/test_s313_answers_label_survival.py --confcutdir=tests/platformkit` -> `11 passed in 2.70s`
`tests/platformkit/test_s319_receipt_guard_lf.py --confcutdir=tests/platformkit` -> `6 passed in 0.21s` (line endings; mtime-newer accepted; recorded-date-newer refused; flipped digit refused; sidecar integrity; sidecar-only verification)
`tests/platformkit/test_loc_rail_scope.py` -> `1 passed in 0.80s`
`scripts/platformkit/answers/test_resolver_registry_routing.py` -> `37 passed in 0.54s`
`scripts/platformkit/answers/test_mechanism_effect.py` -> `20 passed in 0.50s`
Not required, run as a regression check on the added ok-envelope note: `tests/platformkit/mcp_server/test_envelope_contract.py` -> `46 passed, 5 failed`, the same split S313 recorded.
## Why PARTIAL -- the explicit list, 1 item
1. `test_a_stale_ledger_refuses_instead_of_answering` built its staleness by back-dating the ledger FILE's mtime, the exact construct
   rule 2 removes; with rule 2 in place it returned `ok` and failed (the other 10 of 11 passed untouched). Its SETUP now back-dates the
   row's own `run_ts`; its name, its stated bar and all 4 of its assertions are unchanged and none was weakened. This outcome was
   preregistered as the expected PARTIAL before the change was made.
## NOT VERIFIED
- Any pod or real LF-checkout run of the two test FILES; only the guard itself was exercised against a synthetic LF / uniform-mtime tree.
- That the latest-ISO-date rule dates correctly any artifact beyond these 6; it is a fallback, and 0 of the 6 carry a real date field.
- That the recorded digests are CORRECT for the content they seal -- normalisation makes the hash checkout-invariant, not correct.
- Anything about the S313 verdict, its bars, or any prediction quality; no row's number was recomputed. The pod was not contacted, and `data/`, `data/registry/`, `domains/`, `src/`, `api/`, `kernel/`, `intel/` were read only and none was written.
## Honest limitations
- `as_of` still derives from mtimes (the spec says it stays). Measured: on an LF tree with uniform mtimes the S313 as_of test's own premise, `oldest < ledger_mtime`, is False, so that one test stays checkout-dependent. This row does not fix it.
- An artifact carrying no internal date keeps the weaker mtime rule with its 3600 s slack, and the note says so when it fires.
- The legacy `raw` acceptance rule remains for rows sealed on a CRLF machine and read on one; it is the one non-invariant rule left.
Wall: about 19 minutes, from the row's first command at 05:44 CDT to this memo at 06:04 CDT on 2026-09-08.
SHA-256, LF-normalised, of what this row adds or changes (this memo excluded):
`aba4974534455019382a02d3a4286d6472765a79a737f31d0caa19f65a58a315  docs/evidence/harness/S319_preregistration_2026-09-08.md`
`28819e3a94a67abe63ede00e6b6db71a3e7739fd0c4bc31b870982050ab3f5a6  docs/evidence/harness/S319_receipt_hashes_2026-09-08.json`
`4de21c5dc66fde0c4ee619194d49a44af477456bdbf8a423c9129b103e0ec6a4  scripts/platformkit/answers/receipt_guard.py`
`5ab02de00b02a3863e66789a755119a64ab84ea5a04c874b96b0c8eea5264089  tests/platformkit/test_s319_receipt_guard_lf.py`
`2b5231787f41bca275756a38d4f2bd52b8ce3be210ed6917d3421d31887d5f69  tests/platformkit/test_s313_answers_label_survival.py`
Proposed ledger line for the lander (this row does NOT write `docs/evidence/RESULTS_LEDGER_SYSTEM.md`):
2026-09-08 | harness-to-answers calibration | S319 | 6 of 6 named receipts now verify checkout-invariantly (6 sidecar entries, 0 ledger rows rewritten); 6 of 6 receipts carry no structured date field and all 6 decide on recorded dates, 0 on mtimes; 11+6+1+37+20 tests pass with 1 of the 11 setups re-expressed | PARTIAL
