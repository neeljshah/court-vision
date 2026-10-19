# S677 cloud result -- blameless postmortems + P0/P1 link check (2026-09-30)

Row S677 (QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2; ONE-OFF OVERRIDE section 3a). Branch
`cloud/S677-2026-09-30`, commits dac0c229 (build), 049c3b8f (contract fixes), 7087c84c
(adversarial fixes), dfd08c3f (re-verify fixes), from trunk 89218a73. Paper desk only;
calibration language only throughout.
Reviewers: codex is not available in the cloud box. The pre-build critic and every verifier
tier were INDEPENDENT Opus sub-agents (Agent tool) that did not write the code.
PORTABLE: yes.

## Verdicts

| Stage | Commit | Verdict | Folded |
|---|---|---|---|
| Pre-build critic (astra) | spec | REVISE, 11 items | all 11 as spec AMENDMENT 1 |
| CONTRACT tier (A, B1-B10, Q1-Q8 + spec) | dac0c229 | ACCEPT WITH CORRECTIONS | 5 wording fixes to entries (049c3b8f) |
| ADVERSARIAL tier (35 mutants, probes) | dac0c229 | ACCEPT WITH CORRECTIONS (32/35 red) | 5 checker hardening fixes (7087c84c) |
| CONTRACT re-verify (final) | 7087c84c | ACCEPT, no corrections | - |
| ADVERSARIAL re-verify (final) | 7087c84c | ACCEPT WITH CORRECTIONS (24/28 red) | 5 fixes (dfd08c3f), see below |

The spec allows one fix-and-re-verify cycle, and it is used up. So the dfd08c3f corrections (reading an
unreadable entry or WAIVERS.md is now reported instead of raising; tests kill the 4 surviving
mutants S1-S4) were checked by the builder only. That check: the 4 mutants were re-applied one at a time,
and each turns the test file red (1 failed each). No independent tier has read dfd08c3f.

## Tests (one file per process)

- `python3 -m pytest tests/platformkit/ops/test_postmortem_link_check.py -q` -> 37 passed (dfd08c3f)
- `python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed (no allowlisted file grew)
- The test file on trunk 89218a73 (copied into a scratch worktree): collection error, the module is missing (red on old code).

## Headline (reproduce: `python3 -m scripts.platformkit.ops.postmortem_link_check --json`)

Receipts: docs/evidence/forward/issues/2026-09-29.md, 2026-09-30.md. 32 unique issue keys (8 P0,
19 P1, 5 P2; the contract tier recounted them with an independent awk parse and got the same key set).

| status | P0/P1 keys |
|---|---|
| LINKED (to an entry written by the deadline) | 17 |
| WAIVED (cited waiver) | 10 |
| PENDING / OVERDUE / LATE / DOUBLE | 0 |
| violations | 0 |

Excluded, and named in the spec: Queue pointer lines (`- P1 <hash> ...`, `- P1 S501: <hash>`) and
outage detail lines. They carry no first_seen and point at keys already counted. Any other `P<n>`-like
line that does not parse is now a violation (unparsed_issue_line).
A1.6: every entry and WAIVERS.md is dated `Written`/`waived` 2026-09-30, the same day as the commit
that adds it (dac0c229, 2026-09-30T18:46Z), so none is backdated.

## Entries (docs/operations/postmortems/)

- 2026-09-30_capture-outage-2026-09-25.md: 3 keys. The cause is recorded only secondhand ("OS-sleep signature").
- 2026-09-30_lost-slates-2026-09-27-28.md: 6 keys (61.1 h outage, both schedule_missing, night_partial 2026-09-26).
- 2026-09-30_capture-outage-2026-09-29.md: 3 keys.
- 2026-09-30_requested-sleep-2026-09-30.md: 5 keys. The polymarket and books stops are NOT attributed to the sleep.
Facts come only from forward/daily/*.md, forward/issues/*.md and DESK_STATE.md; the contract tier
checked about 60 citations. The slate row text also named an S502 parser-failure entry. The run prompt's
four seeds replaced it, so no S502 entry was written (see NOT VERIFIED).

## Waivers, verbatim (10 of 27 keys = 37 pct; they cover missing information, not resolved incidents)

- WAIVER `capture_outage books@2026-09-23T15:54:41.352771+00:00` waived: 2026-09-30 reason: outage start is "unknown" in the scanner detail line (docs/evidence/forward/issues/2026-09-29.md:49); no tracked daily report covers 09-23; closed in the same receipt.
- WAIVER `capture_outage state2@2026-09-23T15:54:44.383152+00:00` waived: 2026-09-30 reason: outage start is "unknown" in the scanner detail line (docs/evidence/forward/issues/2026-09-29.md:53); no tracked daily report covers 09-23; closed in the same receipt.
- WAIVER `capture_outage books@2026-09-24T18:24:18.137464+00:00` waived: 2026-09-30 reason: outage start is "unknown" in the scanner detail line (docs/evidence/forward/issues/2026-09-29.md:50); no tracked daily report covers 09-24; closed in the same receipt.
- WAIVER `capture_outage state2@2026-09-24T18:24:18.154571+00:00` waived: 2026-09-30 reason: outage start is "unknown" in the scanner detail line (docs/evidence/forward/issues/2026-09-29.md:54); no tracked daily report covers 09-24; closed in the same receipt.
- WAIVER `served_coverage_gap mlb:849845` waived: 2026-09-30 reason: opened and closed on 2026-09-29 (docs/evidence/forward/issues/2026-09-29.md:23); no tracked daily report records which slot or cause produced the gap.
- WAIVER `tick_refused census:2026-09-24` waived: 2026-09-30 reason: tick refusal first seen 2026-09-29T19:38:49Z and closed in docs/evidence/forward/issues/2026-09-30.md; the refusal reason is not recorded in the tracked daily reports.
- WAIVER `tick_refused census:2026-09-25` waived: 2026-09-30 reason: tick refusal first seen 2026-09-29T19:38:49Z and closed in docs/evidence/forward/issues/2026-09-30.md; the refusal reason is not recorded in the tracked daily reports.
- WAIVER `tick_refused schedule` waived: 2026-09-30 reason: tick refusal first seen 2026-09-29T19:38:49Z and closed in docs/evidence/forward/issues/2026-09-30.md; the refusal reason is not recorded in the tracked daily reports.
- WAIVER `tick_refused heartbeat:state_root` waived: 2026-09-30 reason: the morning review rules the refusals (ongoing_low_ram, owners_dead_after_cleanup_failure, previous_child_exited) a host-RAM class rather than a clear code defect and leaves it unrowed pending a ruling (docs/evidence/forward/daily/2026-09-30.md owner action 4, issue c2abe0dbe48ed3be).
- WAIVER `tick_refused heartbeat:books_root` waived: 2026-09-30 reason: escalated P2 -> P1 between docs/evidence/forward/issues/2026-09-29.md and docs/evidence/forward/issues/2026-09-30.md, closed and listed as recurring in the 09-30 receipt; its refusal reason is not recorded in the tracked daily reports (the sibling key heartbeat:state_root is ruled a host-RAM class in docs/evidence/forward/daily/2026-09-30.md owner action 4).

## NOT VERIFIED

- Laptop-only facts: the Windows System log for 09-25 and 09-29, what restarted the captures on 09-25,
  09-28 and 09-29, what requested the 09-30 sleep, and why the 09-26 and 09-29 nights were partial.
  The entries say "not recorded in tracked sources".
- The S502 minute-precision parser postmortem named in the slate row (not written; it is not a P0/P1 key).
- The dfd08c3f corrections have no independent re-verification (see Verdicts).
- The live enforcement: the real-repo test reads the wall clock and will go red after 10-06/10-07 if a
  new P0/P1 key lands without a link or waiver. That is by design (A1.2), but it has not been observed yet.

## NEW GAP (from the verifiers; not rowed, since ids come only from the register)

- Every receipt writer or landing lane now owns a postmortem or waiver duty within 7 days (wall-clock test).
- No cap on the waiver share: thin incidents can be waived; 10 of 27 are waived today.
- Bar 3's fixed cut (first_seen <= 2026-09-30) goes red at once if a later receipt escalates an older
  P2 key (for example night_late 2026-09-29) to P1, even inside its grace window.
- The checker does not compare Written dates with commit dates; a backdated late entry would read as LINKED.
- QUEUE_RE exempts any `- P<n> <16 hex> ...` line. A directory named `issues/*.md` is skipped silently.
