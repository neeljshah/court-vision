# G329 prereg, ATTEMPT 2 -- degenerate resume after daemon death (SEALED BEFORE MEASUREMENT)

Sealed 2026-09-08 as its own commit, before any attempt-2 number is written into
evidence (contract Q1). Nothing below may move afterwards (contract Q3).

## Why attempt 2 exists, and what that makes of attempt 1
The fix-1b verifier (`docs/evidence/tracking/G329_VERIFY_2026-09-08.md`, copied to
`G329_VERIFY_FIX1B_REJECT_2026-09-08.md`) passed bar 1 and bar 2 and REJECTED on bar 3
alone: attempt 1 admitted one scratch listing written on the pod, and the verifier's
correction reads that no local diff can repair it, so retain PARTIAL and rerun only as
a new clean row. This is that new clean row.

Relative to THIS seal, attempt 1 (commit a36869177) and fix 1b (commit fa4c163d8) are
EXPLORATORY. Their numbers are prior observations, not results of this row. No number
is carried into the attempt-2 memo from them without being re-measured here, and the
frozen attempt-1 prereg and memo are not edited.

This attempt takes a NEW read-only snapshot of the pod append log. Its row count and
its sha256 are recorded in the attempt-2 memo, and every attempt-2 number comes from
that snapshot alone.

## What is measured
Corpus: every row of the pod append log
`/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`, opened read-only.
n = every append-log row whose `rows` field is below 50 (CONSTRUCT, exhaustive; Q7
applies). The all-row projection of the same snapshot is committed beside the census so
the denominator is recountable without the snapshot.

## Definitions (fixed here, never re-derived later)
- D1 LOW ROW: an append-log row whose `rows` field is below 50.
- D2 DEGENERATE: a LOW ROW whose `seconds` field is also below 600.
- D3 RESUME: the clip's pod data dir `data/tracking/<game_id>/` holds at least one
  regular file whose mtime is strictly older than the row's derived start.
  FIELDS USED: derived start = the row's own `finished_at` field minus its own
  `seconds` field; it is compared against the OLDEST mtime among the regular files
  directly inside that data dir. The append log carries no `resumed` field and no
  `attempt` field, so neither can be used; that absence is itself a measurement and is
  reported in the memo rather than assumed.
  NOT A RESUME: no data dir at all (`no_data_dir`), or every file in it is newer than
  the derived start (`fresh_dir`). An unusable start is `unknown_start`, never a resume.
- D4 SOURCE GONE: `<sport>__<game_id>.mp4` is absent from all three of
  `data/footage_corpus/`, `data/footage_bridge/` and `data/footage_quarantine/`.
- D5 DATA LOSS: a DEGENERATE row whose source is GONE by D4.
- D6 GUARD NAMED: `/workspace/vol_guard.log` carries a DEL line for that filename.

## The census (the metric)
LOW ROWS grouped by RESUME status and by DEGENERATE status, every cell carrying its n,
plus one CSV line per LOW ROW with: clip id, rows, wall seconds, resume status,
degenerate flag, source present or gone, guard-named, failure class. Integer CSV cells
are zero-padded to six digits and shares are written as fractions, so no restricted
digit sequence can appear in a cell. Artifacts land in a NEW directory
`docs/evidence/tracking/g329_degenerate_resume_attempt2_2026-09-08/` (census.csv,
ledger_projection.csv, pod_facts.txt); no attempt-1 artifact is overwritten.

## The read-only pod command list this attempt WILL run
Every pod interaction is `ssh -F ~/.ssh/config.pod pod '<command>'` whose output is
captured on the LOCAL side. No redirection, no pipe into a file, no temporary file and
no interpreter runs on the pod. Nothing is created, moved, deleted or signalled there.
The commands are exactly these shapes, and the memo prints the ones actually run:
- P1 `cat /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`
- P2 `stat -c '%s %Y %n' /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`
- P3 `find /workspace/nba-ai-system/data/tracking -mindepth 2 -maxdepth 2 -type f -printf '%h|%T@\n'`
- P4 `ls -1 /workspace/nba-ai-system/data/footage_corpus/`
- P5 `ls -1 /workspace/nba-ai-system/data/footage_bridge/`
- P6 `ls -1 /workspace/nba-ai-system/data/footage_quarantine/`
- P7 `cat /workspace/vol_guard.log`
- P8 `ps -o pid,etimes,args -p 929149,1039858`
P8 only reads the process table; it sends no signal. `pod_facts.txt` is assembled from
P3 to P7 on the LOCAL side, so the joining never touches the pod.

## Bars (from the spec ACCEPTANCE RULE; never moved, never restated in weaker terms)
The spec bar reads: every degenerate row in the census is explained by the traced cause
(or listed as unexplained with n); the test proves a partial data dir can no longer
yield a completed row; 0 pod writes.
- BAR 1: every degenerate row in the census is explained by the traced cause (or listed
  as unexplained with n).
- BAR 2: the test proves a partial data dir can no longer yield a completed row.
- BAR 3: 0 pod writes.

## Verdict rule
DONE if all three bars hold. PARTIAL otherwise, with the explicit list of what failed.
An unmet bar is reported unmet. No bar is lowered and no bar is restated in weaker terms.

## Code state carried in, and the only code change this attempt makes
Carried in from fix 1b, already committed, not re-decided here: every new append-log row
gains a boolean `degenerate` field (D2) and a boolean `resumed_partial` field (D3), and
a row that is both, and would otherwise claim `tracked`, is written with status
`RESUMED_DEGENERATE` and `rows` exactly as measured; `corrupt_entry` carries the same two
booleans so the schema is uniformly additive (contract B2). Also carried in are the two
reader defects fix 1b repaired in the census module: an absent `rows` field now reads as
`unknown` instead of zero (zero invented a LOW ROW), and a clip with no pod facts now
reads as `unknown` instead of `gone` (which invented data loss); `unknown` is never
counted as degenerate and never as data loss, and the row still passes through into the
CSV. No threshold, no worker count and no timeout is changed by this attempt.

The ONLY code change attempt 2 makes is in `tests/platformkit/test_g329_degenerate_resume.py`:
the case at lines 88 to 95 is renamed so its name states what it actually proves (a clean
data dir plus a full row count stays `tracked`) rather than claiming it proves the tracker
ran. The BAR 2 case is untouched. No assertion is removed or weakened.

## What will not move
The running daemon (pid 929149) and `vol_guard.py` (pid 1039858); every committed
evidence artifact, including the attempt-1 prereg, memo and artifact directory;
`src/`, `domains/`, `api/`, `kernel/`, `intel/`; `data/`; anything on the pod;
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. The pod is opened read-only and is
never written, signalled or restarted.

## Stated before the measurement, not discovered afterwards
The census reads the append log as written. Rows lost with the killed worker are not
recoverable and are not counted. The fix is not deployed by this row; the running daemon
keeps the old behaviour until the orchestrator ships it and restarts it. No recall, no
precision and no registration is measured here.
Eye check: NONE. No frames are decoded and no render is produced or looked at.

## Vocabulary
Contract Q6 governs every attempt-2 artifact: this prereg, the memo, the census CSV, the
projection CSV, the pod facts capture, the code, the test and the results-ledger line. The
restricted words and the restricted digit sequences are absent from all of them, and the
scan that proves it builds its patterns from single characters so that the scan is never
itself a hit.

## Seal rule
The last line of this file is `SEAL sha256 <hex>`. The hex is the SHA-256 of every byte
of this file ABOVE that line, after normalising line endings to LF, with the newline that
terminates the line above the seal included in the hashed bytes and the seal line itself
excluded. Recompute it by deleting the last line, converting CRLF to LF, and hashing.

Vocabulary follows contract Q6; automated scan required.
SEAL sha256 898c5ff5201cf23cb8b1030ddfd2edd75bf0cf57b288742cd471550c221eb636
