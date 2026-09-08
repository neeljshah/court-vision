VERDICT: DONE -- 57/161 NOT RECOMPUTABLE: over the 13 listed census memos (11 committed, 2 ABSENT) the check found 161 counts, of which 22 are RECOMPUTABLE from a committed artifact the memo itself names, 57 are NOT RECOMPUTABLE and 82 are UNPARSED; the premise holds, because 2 of the 3 reads in the G317 ledger-row sequence at line 000013 have no committed snapshot behind them and the only backed component is the row total carried in `g317_premise_census_2026-09-07.json` (n = 161 parsed counts, 13 listed memos, 11 committed).

# G319 -- are census counts recomputable from committed bytes? (TOOLING ROW)
Spec `docs/evidence/tracking/specs/G319_spec.md` VERSION 2026-09-08. Prereg `docs/evidence/tracking/g319_prereg_2026-09-08.md`, seal `9ea653854fbe4670c01e5d7ae74ef21dba9bfbe936bf10f440784e2ef7189653` over the LF-normalised bytes above its seal line, committed ALONE at `2d5f3cab5` BEFORE the sweep was run. LOCAL only: no pod, no GPU, no video, no network. Every byte read is already committed on master. **Eye check: NONE** -- there are no labels here, only arithmetic and file reading. NO BAR IS SET OR MOVED. Line numbers below are ZERO-PADDED to six digits, as in the CSV, and counts inside the swept memos are referred to BY LINE NUMBER rather than transcribed.

## PREMISE (step 0) -- TRUE
Every committed `g317*` path, with its size. NONE of them is a tabular snapshot: there are 0 committed CSV or JSONL rows across the whole G317 evidence set.

| committed path | bytes | lines | tabular rows |
|---|---|---|---|
| `docs/evidence/tracking/specs/G317_spec.md` | 8,068 | 120 | 0 (the spec) |
| `docs/evidence/tracking/g317_segment_source_metadata_2026-09-07.md` | 5,875 | 60 | 0 (the memo) |
| `docs/evidence/tracking/G317_VERIFY_2026-09-07.md` | 5,149 | 36 | 0 (the verify memo) |
| `docs/evidence/tracking/g317_premise_census_2026-09-07.json` | 3,027 | 98 | 0; a summary object, 1 ledger entry (row total 58, segment row total 25, sha256 `5024ce9d...`, 62,308 bytes), 4 incomplete-CSV records, 25 segment ids |
| `docs/evidence/tracking/g317_ffprobe_reproduction_2026-09-07.json` | 3,400 | 123 | 0; 3 reproduction records, 25 segments with video, 0 without |

The memo states a three-read ledger-row sequence at line 000013 and attributes ONE snapshot, at read 2, to the row total in the census JSON. That single entry is a snapshot-list entry under CENSUS_RULE clause 2: one sha256, one row count, one byte count. It backs ONE read. The other two reads -- the smaller first read and the third read -- have neither committed bytes nor an entry of their own, so 2 of the 3 are UNBACKED and the premise is TRUE. The check agrees mechanically: line 000013 is NOT RECOMPUTABLE with the smaller component missing. Not every count in the memo is unbacked, so the row continued rather than stopping. The wording of the spec puts the unbacked pair at the first read and the FIRST 58; the memo puts the committed snapshot at read 2, so as measured the unbacked pair is the first read and the THIRD read. Either way it is 2 of 3. The repository does hold a later ledger snapshot, `docs/evidence/tracking/g325_artifact/track_daemon_ledger_snapshot.jsonl` (147 rows, committed 2026-09-08 at `7291ff967`), which shows the practice exists; it is a different moment, G317 does not name it, and it reproduces neither G317 count.

## THE RULE
`docs/evidence/tracking/CENSUS_RULE.md`, 40 lines, six clauses: SCOPE (mutable sources only), THE OBLIGATION (committed snapshot, or a hash-chained snapshot list plus the committed projection of the columns used, when over 5 MB per file), ORDER (snapshot after the seal, before the count; the count computed from the snapshot), THE FALLBACK (otherwise reported as NOT RECOMPUTABLE, in those words), REPEATED READS (one snapshot backs exactly one read), and WHAT IT IS NOT (recomputable is not correct). It is written once, in that file, and no landed memo was edited to comply with it.

## THE CHECK
`scripts/platformkit/tracking/census_recomputable.py`, 193 lines. It reads a memo, takes every slash sequence of two or more integers and every `n = <k>` form, requires a source noun on the same line, resolves every artifact token the memo names against `git ls-files`, and derives from each artifact the integers it reproduces (line count and line count less header for CSV and TXT, non-empty lines for JSONL, every list length plus every integer under a count-named key for JSON). A count is RECOMPUTABLE only when EVERY component is reproduced. Four verdicts, exactly as preregistered: RECOMPUTABLE, NOT RECOMPUTABLE, UNPARSED (the line names no source noun, so the check declines to judge), ABSENT (the memo is not committed).

## THE SWEEP -- every listed memo, every count found
Full detail, one line per count with its components and the artifact used, in `docs/evidence/tracking/g319_census_recomputable_2026-09-08/sweep.csv` (163 data lines; every integer cell zero-padded to six digits).

| entry | memo | n | RECOMP | NOT RECOMPUTABLE (lines) | UNPARSED | note |
|---|---|---|---|---|---|---|
| G309 | `g309_multigame_census_2026-09-07.md` | 4 | 1 | 3 @ 000004, 000033, 000039 | 0 | subset of the committed 15-row census CSV |
| G312 | `g312_coverage_denominator_2026-09-07.md` | 4 | 2 | 1 @ 000035 | 1 @ 000003 | the one NOT RECOMPUTABLE is a FORMULA, not a count |
| G313 | `g313_ten_id_cap_2026-09-07.md` | 1 | 0 | 0 | 1 @ 000043 | only one count-shaped token in the whole memo |
| G317 | `g317_segment_source_metadata_2026-09-07.md` | 6 | 5 | 1 @ 000013 | 0 | the premise sequence |
| S314 | `S314_teach_packet_census_2026-09-07.md` | 2 | 0 | 2 @ 000019 | 0 | BOTH are DATE fragments; the real counts use grouped digits and were not parsed |
| G329 attempt 1 | `g329_degenerate_resume_2026-09-08.md` | 27 | 1 | 12 @ 000001 x2, 000011 x3, 000012 x2, 000030 x2, 000032, 000036, 000037 | 14 | |
| G329 attempt 2 | `g329_degenerate_resume_attempt2_2026-09-08.md` | 23 | 1 | 8 @ 000001 x2, 000011 x3, 000012, 000042, 000043 | 14 | |
| G327 attempt 1 | `g327_detector_batch_stability_2026-09-08.md` | 0 | 0 | 0 | 0 | **ABSENT** -- no `g327*` evidence path is committed on master |
| G327 attempt 2 | `g327_detector_batch_stability_attempt2_2026-09-08.md` | 0 | 0 | 0 | 0 | **ABSENT** -- same |
| G330 attempt 1 | `g330_panorama_identity_2026-09-08.md` | 19 | 1 | 5 @ 000001, 000010, 000030 x3 | 13 | |
| G330 attempt 2 | `g330_panorama_identity_attempt2_2026-09-08.md` | 35 | 1 | 12 @ 000001 x6, 000027, 000028, 000034, 000037, 000038, 000057 | 22 | its own lines 000038 and 000057 SAY a count is not reproducible |
| G310 attempt 2 | `g310_native_input_arm_attempt2_2026-09-08.md` | 25 | 8 | 4 @ 000008 x3, 000058 | 13 | the three at 000008 are a FRAME RATE, not a count |
| G331 | `g331_evaluated_frames_sidecar_2026-09-08.md` | 15 | 2 | 9 @ 000001, 000036 x7, 000054 | 4 | |
| **TOTAL** | 13 entries, 11 committed | **161** | **22** | **57** | **82** | 2 ABSENT |

WHAT THE 82 UNPARSED ARE. Overwhelmingly TABLE CELLS: a count sits in a markdown table row that carries no source noun of its own because the noun is in the column header. G330 attempt 1 line 000020, G330 attempt 2 line 000031 and G310 attempt 2 lines 000018 to 000027 are of that shape. The check reports them rather than guessing which column they belong to.
PARSER FALSE POSITIVES INSIDE THE 57, named so they are not read as defects in the owning row: S314 line 000019 contributes 2, where a slash-separated DATE LIST was matched across a date boundary; G312 line 000035 contributes 1, a ceiling FORMULA over a stride; G310 attempt 2 line 000008 contributes 3, a broadcast FRAME RATE written as a ratio. That is 6 of 57. The remaining 51 are genuine counts over a source that no artifact the memo names reproduces by a whole-artifact recount or a snapshot-list entry.
OWNING ROWS THAT NEED A REGISTER CAVEAT (the orchestrator edits the register, not this row): **G309, G317, G329, G330, G310, G331**. G312 and S314 are NOT on that list because their only NOT RECOMPUTABLE counts are the parser false positives above; G313 has none at all. S314 instead needs a different note: the check found only 2 count-shaped tokens in it and both are false positives, so this sweep says NOTHING about the counts S314 actually reports.

## NOT VERIFIED
- The check judges the INTEGERS in a read sequence, not the READS behind them, so CENSUS_RULE clause 5 (one snapshot backs one read) is NOT enforced by it. A three-read sequence of equal values reads as RECOMPUTABLE off one snapshot. Clause 5 was applied BY HAND for G317 only.
- A bare basename resolves to EVERY committed file with that name, so `census.csv`, `tracking_data.csv` and `run_summary.json` each resolved to several unrelated files. RECOMPUTABLE is therefore an UPPER bound and 57 is a LOWER bound on the defect. The artifact that supplied each component is named in the CSV so every verdict is auditable.
- NOT RECOMPUTABLE does not separate a count with no snapshot at all from a SUBSET count over a committed artifact that a column filter would reproduce. G309 is the clearest case: its committed census CSV holds 15 data rows and the memo reports a smaller matched subset, which a human can derive and this check cannot. Only the G317 sequence was adjudicated by hand.
- RECOMPUTABLE means a committed artifact reproduces the integer. It does not mean the integer is right, that the artifact is the source the memo actually counted, or that the snapshot preceded the count. Coincidence is possible and was not excluded.
- The parser misses counts written in words, counts using grouped digits with a separator, and counts whose source noun sits on a neighbouring line. It reports what it could not parse; it cannot report what it did not see.
- The 2 ABSENT entries are reported as ABSENT, not as clean. G327 has a committed spec naming both memo filenames and neither file exists on master, so those two rows are unswept, not passing.
- No landed memo, artifact, threshold or register file was modified; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` was not touched. Nothing was adopted, no default moved, no flag flipped, nothing written under `data/registry/`. The pod was not contacted.

WALL TIME: about 30 minutes from lane pickup to memo, entirely local; 0 GPU seconds; 0 pod commands. ARTIFACT SHA-256 (over LF-normalised bytes): prereg `a65a24d52c74252b920fc21ba28f2022a8f16593b9efeb043600ee91485b9f53` (as committed, seal line included) | `CENSUS_RULE.md` `6679a0b83eaf75b1da3bdb14bf369fbdfe80bf17fa8ad61f1c478b6c5cad6da2` | check `636e633767a48a2ae84838dafae67b60be0ac417910f10fb8dce25bc695221c2` | test `06521a6e0329c12d9ceb538f3db63700c8e60267564390cbdc9a5dec304384f2` | `sweep.csv` `7c1f1bfa71cf1d7400081acd0153472e8f9c7c47985084b9d607a08761d3b3f5`. Hexadecimal digests are single tokens; a digit run inside one is not a standalone figure. TEST: `python -m pytest tests/platformkit/test_g319_census_recomputable.py -q -p no:cacheprovider` -> 4 passed; `tests/platformkit/test_loc_rail_scope.py` -> 1 passed. Never a full pytest. The sweep CSV reproduces byte-identical on a second run of the check.

## Landing 2026-09-08 (verifier codex-sol: ACCEPT, no corrections)
- NEW GAP: `scripts/platformkit/tracking/census_recomputable.py:63-74` accepts arbitrary JSON list lengths and count-key integers without validating the hash, timestamp, chain, or projection required by `CENSUS_RULE.md:10-14`; the G317 read-2 object is metadata rather than a compliant prospective snapshot list.
- NEW GAP: `scripts/platformkit/tracking/census_recomputable.py:41-51` silently falls back to all filesystem files after any git-index failure, so an untracked artifact can be treated as committed; make that fallback an explicit construct-only mode.
- NEW GAP: `scripts/platformkit/tracking/census_recomputable.py:89-92` applies header subtraction to TXT although the sealed prereg specifies TXT line count only; no swept TXT artifact was used.
- NEW GAP: line 1 of this memo began `DONE --` rather than the evidence instruction's literal `VERDICT:` prefix; corrected at landing to `VERDICT: DONE --`, a prefix-only change with no other byte of the memo altered.
Vocabulary follows contract Q6; automated scan required.
