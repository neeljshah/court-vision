GAP G139 | sport all | worktree a5 | log cx_g139_decoded_frame_denominator
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A preventable loss on freshly tracked games, found while verifying the pipeline.
THE SIGNAL, measured by the orchestrator on the live pod ledger. Of the last 60 rows, first-failure
heads are: coordinate_contract 39, **decoded_frame_denominator 6**, and four real quality failures
(oob x3, coverage x1) that actually reach the gate. So roughly **10 pct of recent tracked games die
on decoded_frame_denominator**, and unlike the coordinate contract -- which G91/G101/G106 showed is
a genuine camera limit -- this one looks like a tooling failure rather than a property of the
footage. A concrete instance: `kbo_8UMcAyU1pi0`, 162,557 rows, failure head
"decoded_frame_denominator: ffprobe did not return exactly o...".
THIS MATTERS MORE THAN THE RATE SUGGESTS. The footage bridge was repaired this evening (a stale
yt-dlp capped every download at ~10.4 MB; upgrading restored full-game downloads) and full games are
now landing -- that kbo game is a complete track. A 10 pct loss applied to a pipeline that is
finally moving is worth removing before the backlog arrives.
ANSWER:
  (a) QUOTE the check. Find where decoded_frame_denominator is raised -- start from
      `_with_decoded_denominator` and `build_decode_manifest` reached from
      scripts/platformkit/track_daemon_done.py:112 -- and state exactly what it asks ffprobe for
      and what it requires back. Quote the code, do not infer from the message.
  (b) REPRODUCE it on a named affected game, read-only, and paste the actual ffprobe output beside
      what the code expected. "did not return exactly one" suggests a stream-count assumption; find
      out what these files actually contain. Multiple video streams, an attached cover image, or a
      data stream are all plausible and are ordinary in broadcast media.
  (c) COUNT the blast radius across the whole ledger, not just the recent window: how many distinct
      games have ever failed this way, and are they concentrated in one sport, one source, or one
      acquisition period. A failure that only affects post-repair downloads is a different problem
      from one that has been there all along.
  (d) DECIDE whether the check is right and the files are odd, or the check is too strict. Say which
      plainly. If the file genuinely has two video streams, picking one needs a stated rule -- do NOT
      silently take the first, because a cover image is a video stream and would give a frame count
      of one.
  (e) RECOMMEND a fix in one paragraph. Implement it ONLY if it is small and lives outside the
      human-gated trees; track_daemon.py is under the shared-module token, so prefer
      track_daemon_done.py or the decode manifest module. If the fix belongs in a gated tree, write
      a proposal and stop.
DO NOT change any harness threshold, the coordinate contract, or any verdict. Do not re-track
anything. NEVER KILL ANYTHING ON THE POD -- the track daemon is live and seven bridge lane workers
run under scripts/platformkit/bridge_keeper.
ACCEPTANCE RULE:
  metric        = distinct games ever failing on decoded_frame_denominator, with the per-sport
                  breakdown, plus a named cause reproduced on at least one game
  before        = 6 of the last 60 ledger rows; total unknown; cause unknown
  bar           = NO pass bar. Success is the check quoted, the cause reproduced with real ffprobe
                  output, the blast radius counted, and a clear verdict on whether the check or the
                  files are at fault. "The check is correct and those files are genuinely
                  unusable" is a full success.
  n             = every ledger row; state the count you read and the window, since the ledger grows
                  while you work
  eye check     = n/a for the arithmetic, but OPEN one affected file with ffprobe and show its real
                  stream list rather than trusting the error string.
  must not move = every threshold, the coordinate contract, every verdict, the daemon, and every
                  pod process
EVIDENCE: docs/evidence/tracking/g139_decoded_frame_denominator_2026-09-0X.md with the quoted check,
the reproduced ffprobe output, the blast radius, the verdict, the recommendation, and a NOT VERIFIED
list. Commit derived tables under docs/evidence/tracking/g139_denominator/ BEFORE reporting (A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree and
commit with explicit pathspecs only.
TEST: exactly one new per-file test if you change code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
SHARED MODULE: track_daemon.py is under the token -- READ it, prefer not to change it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
