# S641 fix -- cloud result 2026-09-30 (S504+S641 landed row 7e334bddc, review F2)

Source: LANDINGS_REVIEW_cloud_2026-09-30.md F2 (medium), branch cloud/review-landings-2026-09-30.
Branch: cloud/S641-fix-2026-09-30 from origin/trunk 8eccd364 (ls-remote 'cloud/S641-fix*' empty
before build). Commits: 735123e2 (build), 7d5ab849 (fix round 1), plus this memo commit.
Spec: docs/evidence/harness/S641_fix_spec_2026-09-30.md (AMENDMENT 1 = pre-build Opus critic
REVISE, 10 items; AMENDMENT 2 = fix round 1 from both verifier tiers).

## Defect (reproduced on trunk)
served_asof.input_as_of fell back to the newest file mtime whenever no played date was found, and
mapped any read exception to "no date". A dated input with zero played rows (e.g. an MLB frozen
parquet whose rows are all future-dated with null runs) or a corrupt / unreadable parquet was
served with as_of = file mtime, as_of_source "input_mtime" and staleness_status "fresh".

## Fix (edits only under scripts/platformkit/ and docs; no human-gated tree touched)
- scripts/platformkit/mcp_server/served_asof.py: _max_played_date returns (date|None, filtered,
  dated). input_as_of: any exception on any present spine file (stat or read) -> as_of None,
  as_of_source "input_unreadable" (fail closed); >= 1 dated file and zero played rows -> as_of
  None, "no_played_rows"; the mtime stands in ONLY when every present file is readable and has no
  date column (unchanged "input_mtime"). as_of None -> staleness_status "unknown" and
  finalize_served skips aging (unchanged). staleness_note names the cause. Null / unparseable
  date columns are masked before the clamp (-> no_played_rows, not a TypeError). Cache key gains
  st_size. 211 lines.
- docs/MCP_TOOLS.md: as_of_source list gains no_played_rows and input_unreadable (additive).
- NEW tests/platformkit/mcp_server/test_served_asof_s641_fix.py (11 cases, synthetic tmp_path).
MLB fail-closed rationale: the predictor's combined corpus reads both parquets and raises on
either, so a date from the readable one describes a corpus it could not have built.

S504 AMENDMENT 3 (recorded here; the S504 spec file is not edited): this TIGHTENS the S504
contract. S504 AMENDMENT 1 item 2 read literally let a dated-but-zero-row file take the mtime, and
the S504 spec body labelled unreadable input "unknown"; now mtime only for a readable undated
file, and two as_of_source values are added. No value renamed or removed.

## Verdicts
- Pre-build critic (Opus): REVISE, 10 items, all folded (AMENDMENT 1).
- CONTRACT tier (Opus), round 0 on 735123e2: ACCEPT WITH CORRECTIONS (result memo missing).
  Round 1 on 7d5ab849: ACCEPT WITH CORRECTIONS (wording only: 10 trunk reds are 8 by assertion,
  2 by the defect's own exception; folded into AMENDMENT 2 and this memo).
- ADVERSARIAL tier (Opus), round 0 on 735123e2: ACCEPT WITH CORRECTIONS (A: all-null /
  unparseable date column mislabelled input_unreadable; B: cache key; C: stat-race and note
  mutants survived). Round 1 on 7d5ab849: ACCEPT. 13 probes, none yields "fresh" from a
  zero-row or unreadable input; mutants #1-#12 and M15 killed.
  Survivors: M13 / M14 are equivalent (the object cast and the NaT mask each fix A on their own).
  M16 (st_size removed from the key) is untested hardening.

## Tests (one file per process, cloud clone, Python 3.11)
- python3 -m pytest tests/platformkit/mcp_server/test_served_asof_s641_fix.py -q -> 11 passed
  (trunk 8eccd364 with the file copied in: 10 failed / 1 passed. 8 fail by assertion; 2 fail by
  the defect's own exception (FileNotFoundError, KeyError 'staleness_note'). The only pass is the
  undated->mtime pin, which is meant to pass on both. On 735123e2: 2 failed (null, junk) / 9 passed.)
- python3 -m pytest tests/platformkit/mcp_server/test_served_asof_s504.py -q -> 20 passed (unchanged file)
- python3 -m pytest tests/platformkit/mcp_server/test_envelope_contract.py -q -> 49 passed, 2 failed
  (A06, X06; identical on trunk; pre-existing, out of scope per the S504 spec)
- python3 -m pytest tests/platformkit/mcp_server/test_server.py -q -> 8 passed

## NOT VERIFIED
- Real corpus files (no data/ in the clone): behaviour on the laptop's real MLB / NBA / soccer
  parquets; the Windows re-verify of test_envelope_contract W01-W04.
- Residual (low): a rewrite that keeps both mtime_ns and byte size identical can still serve a
  cached date (only a content hash closes it; not done).
- Probe 8 (low): a directory at games_current makes inputs_for date the frozen file alone while
  refresh_ratings checks .exists(); the predictor most likely fails first. Not fixed.

## NEW GAP candidates (not fixed here; register untouched)
1. served_asof.py `utc=True` then `.dt.date` moves an offset timestamp (e.g. 21:00-04:00) to the
   next UTC day.
2. health_status.py:36-37 calls stat() after the presence check: a file deleted in between
   raises and system_health crashes.
3. inputs_for raising (domain import error) turns an ok answer into a tool error (never "fresh").
4. Cache key collision on identical mtime_ns + size (see NOT VERIFIED).

PORTABLE: yes (pure envelope code + synthetic tests; runs on the cloud clone).
Calibration language only; no number is authored by this module.
