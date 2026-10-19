# S804 -- the rolling week report is counted, not a digest raise, when an older night is re-read (PAPER ONLY)

## Premise (measured 2026-10-09 17:3xZ, read-only on the main tree)
- `paper_desk_evidence.receipt(main, day, artifacts=True)` raises `night_artifact_digest_mismatch` for 2026-10-06 and 2026-10-07 and
  returns normally for 2026-10-08. The only mismatching artifact is step `week`, docs/evidence/forward/weeks/2026-W40_maker_forward.json:
  pinned 27274d94a3ca (10-06) and df93c7fb1013 (10-07), on disk b6d64d64de56, which is 11,534 B in every case (rewritten 14:01Z 10-09 by night 10-08).
- Cause: paper_night._steps writes `week_out` = weeks/{iso_year}-W{iso_week}_maker_forward.json for the PREVIOUS ISO week of the
  as_of date (paper_night_budget.json:16), so every night of a week rewrites the same file.
- Reader module edited: scripts/platformkit/ops/paper_desk_evidence.py `receipt()` (the night-record reader behind
  paper_desk_actions.accepted_receipt). It is not in the paper_night_* family and it is not seal-pinned under docs/evidence/forward.

## Change (smaller diff of the two options: exempt, not version)
- `ROLLING_WEEK = FORWARD + r"/weeks/[0-9]{4}-W[0-9]{2}_maker_forward\.json"`. In receipt(), a digest mismatch on an artifact that is
  (a) under step name `week`, (b) a full match of ROLLING_WEEK and (c) present on disk sets `week_artifact_rolling = 1` on the week
  outcome and skips that artifact (its later summary is never attributed to the older night). Every other mismatch still raises.
- Versioning per night (option 1) would need paper_night_budget.json / paper_night.py (pinned zero-net-line file) and a new
  consumer path, so it was not chosen. forward_week_report.py is unchanged.

## Clauses
- V1 Real 10-06 and 10-07 receipts (artifacts=True) return, with week_artifact_rolling 1. 10-08 is unchanged (week summary read).
- V2 A rewritten qualification / scoreboard / history artifact still raises night_artifact_digest_mismatch.
- V3 No exemption for a non-week step pinning the week path, a week step pinning another path, or a missing week file.
- V4 The rolling week adds no artifact_refusal_reasons, so accepted_receipt's night_artifact_refused count is unchanged by it.
- V5 The tests fail on HEAD's paper_desk_evidence.py. Existing paper_desk_evidence / s711 / s794 tests still pass. LOC <= 300.
- V6 No $/edge language; PAPER ONLY.

## Fix round 1 (adversarial REJECT on c1ab24266: M13 unescaped dot, M14 date shape widened to .* survived)
- V7 A week step pinning weeks/../scoreboard/..._maker_forward.json, weeks/old/2026-W40_maker_forward.json or weeks/2026-W40_maker_forwardXjson,
  rewritten, still raises (the date shape and the escaped dot are pinned by the test).
- Fix round 2 (adversarial round 2 REJECT: M10/M10c prefix, M15 digit counts, M16 optional W, M17 _full_selection, M18 dash survived):
  V7 also covers other/weeks/, x/docs/..., 20260-W40, 2026-40, 2026XW40 and _full_selection paths.
- Fix round 3 (adversarial round 3 REJECT: N1 re.I, N2 [Ww], N7 W[0-9]{1,2}, N8 startswith("week") survived):
  V8 every one-character deletion, X insertion and case swap of the real week path raises; steps weekly / Week / week_full / weeks
  pinning the week path raise; a directory at the week path raises.
- Fix round 4 (adversarial round 4 REJECT: \d, jsonl?, [W-], optional prefix, [0-9A-Z], strip(name), lstrip/strip/backslash
  path normalisation survived): V9 the near-miss set is every one-char deletion, case swap, and insertion or substitution from
  "X-./ l\\0A" plus a non-ASCII digit, plus the bare repo-root weeks/ path (other valid YYYY-Www week files excluded; names the
  filesystem cannot hold skipped; > 1000 tried); none is exempt. Step names " week" / "week " raise.
- Fix round 5 = CODE CHANGE (adversarial round 5 REJECT: any character class / alternation outside the finite alphabet survived;
  the regex was the wrong shape). ROLLING_WEEK and `import re` are deleted. The exemption now requires
  `item["path"] == week_path(day)`, where `week_path(day)` derives the one week file this night writes, the same way
  paper_night._steps does: the ISO week before the as_of date (day + 1). This leaves no pattern to widen. Another valid week file
  (W39, W41, 2025-W40) pinned by mistake now also raises.
- V10 week_path: 10-04/05/06/07 give 2026-W40, 10-11 gives 2026-W41, 2026-01-04 gives 2026-W01 and 2025-12-28 gives 2025-W52.
  A night pinning another valid week raises. The near-miss set includes other valid weeks and still admits 0.
- Fix round 6 (adversarial round 6 REJECT: M6 calendar year, M17 day_after(day, 2) survived; +6 is equivalent):
  V11 week_path equals paper_night._steps' own expression, formatted with the real paper_night_budget.json week_out, for every
  day 2025-01-01..2027-12-31 (1,095 days).
