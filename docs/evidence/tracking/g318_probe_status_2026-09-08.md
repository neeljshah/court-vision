VERDICT: DONE -- every new ledger row now carries `probe_status`; the pod census finds 0 all-null-timebase rows in 274 (n=274, exhaustive), so the defect is LATENT and the re-read table is empty (n=0).
G318, 2026-09-08. Prereg sealed as its own commit before any number below: `g318_prereg_2026-09-08.md`. Eye check: NONE -- no frame was decoded and no render was produced or looked at.

PREMISE: TRUE (the row proceeds). Both return statements of `probe_source()` are dict literals, so neither
can be falsy: `scripts/platformkit/tracking/source_timebase.py:15-18` (reader would not open) and `:24-28`
(reader opened), pre-change line numbers at master af08c7b61. Local runs, printed verbatim:
  MISSING   exists=False return={'source_fps': None, 'source_width': None, 'source_height': None, 'source_resolution': None, 'source_duration': None} truthy=True
  ZERO_BYTE exists=True  return={'source_fps': None, 'source_width': None, 'source_height': None, 'source_resolution': None, 'source_duration': None} truthy=True
The two returns are byte-identical, and a never-probed row reaches the ledger with the same four null fields, so the row alone could not tell those three cases apart.
TRACE (pre-change file:line)
- probe runs at `track_daemon.py:387` (job launch) and `track_daemon_sources.py:90` (ranking only).
- failure paths, all truthy: a missing file and an unopenable file both return `source_timebase.py:15-18`; no video stream leaves `source_resolution` None at `:23`; an unreadable frame rate leaves `source_fps` and `source_duration` None at `:24,:28`.
- the daemon consumes it at `track_daemon.py:239` and `:307` (`if source:`, always true) and `:318`.
- ledger rows come from exactly two places, `track_daemon.py:326` (`_finish`) and
  `track_daemon_sources.py:88` (`record(corrupt_entry(...))`, a quarantined staged file); both funnel
  through `_record_loudly` into `_record` at `track_daemon.py:143-152`.
CENSUS -- pod ledger `data/tracking/track_daemon_ledger.jsonl` under `/workspace/nba-ai-system/`,
read-only, snapshot 2026-09-08T10:49:59Z, one file with no rotation sibling, every row (B7). Full table
in `g318_probe_status_2026-09-08/census.csv`.
- ledger rows total (the denominator): n=274; unparsable: n=0
- rows with all four timebase fields null: n=0; with every timebase field present: n=274
- rows null in source_fps / source_height / source_duration / source_resolution: n=0 / 0 / 0 / 0
- rows already carrying `probe_status`: n=0; rows by status, tracked / thin / timeout: n=239 / 34 / 1
CENSUS RE-READ -- each all-null row classified by what survives on disk today
- R1 source absent from corpus, bridge and quarantine: n=0; R2 present but unprobeable today: n=0
- R3 present and probeable today: n=0; R4 unknown, outside the budget: n=0
- pod ffprobe calls used, of a budget of 20: n=0 There is no all-null row to re-classify, so no pod ffprobe call was needed and none was made.
THE FIELD (additive, B2). `probe_status` on every new row, one of `ok`, `failed:missing`,
`failed:ffprobe_rc`, `failed:no_video_stream`, `failed:parse`, `not_probed`. `probe_source()` keeps its five key names and meanings, gains an additive `status`, and stays truthy on failure; `probe_status()` in
`source_timebase.py` maps a missing result to `not_probed`. Call sites: `track_daemon.py:318` (one keyword
in the existing `entry.update`) and `corrupt_entry` in `track_daemon_ledger.py`, `not_probed` because a file quarantined on its size alone is never probed. 0 fields renamed, 0 defaults changed, `track_daemon.py` unchanged at 440 lines (allowlist 440).
TESTS, each file run alone with `-q -p no:cacheprovider`: `tests/platformkit/test_g318_probe_status.py`
9 passed; `test_track_daemon.py` 29; `test_track_daemon_done.py` 7; `test_track_daemon_job_budget.py` 1;
`test_track_daemon_ledger_denominator.py` 1; `test_track_daemon_timeout_verdict.py` 1; `test_g329_degenerate_resume.py` 10; `test_tennis_sequential_plan.py` 2; `test_loc_rail_scope.py` 1.
NOT VERIFIED
- No pod row carries `probe_status`: the pod daemon runs pre-G329 code and this row deploys nothing.
- The four `failed:` reasons are exercised locally; none has been observed on a real pod source.
- `ok`, `failed:no_video_stream` and `failed:parse` are tested through a stand-in reader; only
  `failed:missing` and `failed:ffprobe_rc` run against real files and the real reader. The re-read is
  empty, so R1 to R4 are defined and unexercised, not confirmed.
- The census reads what the daemon wrote; rows lost with a killed worker cannot be counted.
- The reader is `cv2.VideoCapture`, not a literal `ffprobe` subprocess; `ffprobe_rc` is kept as the spec's
  name for "would not open" rather than renamed to suit the implementation.
WALL TIME: row opened about 2026-09-08T10:44Z; prereg sealed 10:49:30Z; memo written 10:58Z.

SHA-256 over LF-normalised bytes
ab606d577e63f088ce9ca885c9ed81acf65025b4a599f778b1d7d9837deb2586  g318_prereg_2026-09-08.md (embedded SEAL 1ca27e6cb4d29c433295db047f1e93b9c19ada5d41a8f996a2d0afcc2c93a729)
681d5231c4152a55801eaadebeeab8e763cddd9d3efde4b4f4e61fa55bb65234  g318_probe_status_2026-09-08/census.csv
a0a44f58514e3741e326e0bbb054f0fbfc482314e0ce5c32a63f914823450879  scripts/platformkit/tracking/source_timebase.py
b30d8b5962dd2d1f785d6a685c461dec664898c8156c6e54334107a689e8207d  scripts/platformkit/track_daemon.py
68c55386924a297d1fcf8bed8bfbb6d878257aae9c8f227c15b9e389865f1b22  scripts/platformkit/track_daemon_ledger.py
1120fc84f98b5b601bfcad8b9766f3243740e30288c285d8e347caefe96a44df  tests/platformkit/test_g318_probe_status.py
## Corrections applied at landing 2026-09-08 (verifier codex-sol)
CALL SITE: `track_daemon.py:322` in the TRACE bullet and in THE FIELD now reads `:318` -- the line in the LANDED master file. The verifier read 321 against the a1 tree (440 lines); master carries G328's slot wiring, 2 lines shorter, so the landed file is 438 lines and the union is the same 2 edited lines. The `track_daemon.py` digest below is the a1 candidate file, not the landed union; the other five reproduce on master.
LEDGER ROW: `9 new tests plus 8 existing files green` -> `9 new tests; 11 existing files green; 1 inherited importer file red` in the RESULTS_LEDGER row.
NEW GAP: `track_daemon.py` is above the repository 300-line target (440 in the candidate, 438 as landed); G318 did not grow it and its explicit bar permits 440.
NEW GAP: `test_g149_persist_decoded_denominator.py:30-42` has a stale verdict stub that rejects the existing publish keyword at `track_daemon.py:278`; candidate and master both fail identically.
NEW GAP: `test_night_report.py:38,57` expects pre-freshness supervisor output; candidate and master both report 2 passed, 2 failed, unrelated to probe_status.
NEW GAP: the G318 spec test is absent on master before this landing, so contract A1 could not run there (`VERIFIER_CONTRACT.md:11`; `G318_spec.md:66-68`).
Vocabulary follows contract Q6; automated scan required.
