VERDICT: PARTIAL -- the ">= 30 sections proved" bar: 21 of the 31 sampled sections proved at <= 1 native frame (21 distinct source ids, so the >= 10 ids part is met); classification 884/884 and the collision list are met.
# G361 source / table identity map
Spec `docs/evidence/tracking/specs/G361_spec.md`; VERIFIER_CONTRACT B and Q self-checked. Prereg
`g361_source_identity_2026-09-09/g361_prereg_2026-09-09.md`, LF seal sha256
02c8e3534388bba404a0c83616aa8573af50e9e8d48de33e72ec14b3f0aed825, committed ALONE at bad00fad before any G361
number existed (Q1). Finisher claude-opus, fix 1b claude-sonnet, ON THE POD in `/workspace/wt/a1`. Every step
read ONE snapshot `ledger_snapshot.jsonl`, copied 2026-09-09T18:35:37Z: 892 rows, 884 distinct ids, never live.
## PREMISE (census run after the seal) -- HOLDS
    ledger rows 892 | distinct game_id 884 | table headers readable 809 | unreadable 29 (838 dirs)
    tables with a COMPLETE source binding 0 / 809 = 0.0000 (FALSE only at 0.95 or above)
Of the 809 readable headers: source_fps 808, source_height 808, and 0 each for source_sha256, source_first_pts, source_width, source_topcut_px -- no archived table carries a source binding.
## CLASSIFICATION (denominator = 884 distinct snapshot game_ids) -- CORRECTED, fix 1b
    EXACT    19 / 884  archived source bytes present and hash-bound (6 distinct source ids)
    ALIGNED  21 / 884  re-fetched, every landmark within the bar AND >= 30 distinct evaluated landmarks
    UNKNOWN 844 / 884  = table_unreadable 79 + no_source_bytes_and_no_alignment 765
    classified 884 / 884 = 100 pct; all 892 snapshot rows carry a classified game_id
COLLISIONS: 0 real over 690 parsed (video_id, start) pairs, none shared; unparseable_ids 194 (id does not
  parse) reported separately, excluded from every collision group -- att1 bucketed the 194 into one false
  UNKNOWN@UNKNOWN "collision" (collision_count 1); fixed in cmd_summary and the aligned_games floor check
  (g361_source_identity.py:124-130, :252-274).
## ALIGNMENT -- 31 sections, even sample over 632 eligible rows, k = floor(632/30) = 21
Bar: every landmark within 1.0 native frame and >= 30 distinct evaluated ticks; the start offset is the
`_s<offset>` suffix of each id. 23 sections re-fetched and aligned (693 landmark rows total), 8 blocked.
PROVED 21 of 31, class ALIGNED, 21 distinct source ids (max error by band: 0.0000 fr n=31 x11 + n=33 x1,
  0.0150 fr n=31 x8, 0.0120 fr n=31 x1; full id list and per-landmark rows in ledger_links.csv/alignment.csv).
NOT PROVED, 2 of 23 re-fetched: eurocup-qrWmO434a0k_s4161, n=31, max 3.0000 fr -- landmark 25 alone (frame
  2823, 94.100000 s archived vs 94.000000 s re-fetched, the other 30 exactly 0.0000, a localised 3-frame
  discontinuity); fiba-14Mh4JjtLVg_s6710 has 9 distinct evaluated ticks, under the 30 the prereg requires --
  INELIGIBLE, now correctly UNKNOWN/no_source_bytes_and_no_alignment (att1's module classed it ALIGNED with
  no floor check, the source of att1's 22-against-21 gap; fixed).
BLOCKED 8 of 31, every one left UNKNOWN and none inferred aligned (reasons in `refetch_failures.txt`): rung
  270 absent for 7 ids ("Requested format is not available"); 1 id "Video unavailable".
EYE CHECK: 23 strips, one per re-fetched section, boxes drawn at the archived tick beside the plain frame,
  error printed; largest 162630 B, under 200 KB.
SIGN CONVENTION: error = re-fetched presentation stamp at the archived frame index minus the archived tick
  timestamp, in native frames; POSITIVE means the re-fetched decode runs LATER.
WALL / COMPUTE: fetch-align-strip loop 1927 s over 23 sections (att1, unchanged by fix 1b); fix 1b's
  links+summary regeneration from the committed snapshot ran under 5 s total, no re-fetch, no GPU.
HASH CONVENTION: every `SHA256SUMS.txt` digest is sha256 of the file's Git blob bytes (30 current-byte matches plus 8
  CRLF-to-LF matches) -- ONE convention for all 38 (att1 mixed raw and LF-normalised across 8 of 38).
ARTIFACT SHA-256: all 38 (10 CSV/JSON artifacts, the prereg, 23 strips, 2 modules, 2 tests) are in
  `SHA256SUMS.txt`, blob/LF digest, sha256 a96b2b785641962bbe7d257426805404dfddd4a01304e51cabaf3466968643a1.
Q6 SCAN: the six retracted-figure patterns are assembled from single characters at runtime, never a
  contiguous literal in the scanner's own source; self-tested against a planted token first (FIRED) before
  trusting the real scan, which ran over this memo, both modules, both tests, the 9 evidence files: 0 hits.
## NOT VERIFIED
- The bar: 21 proved, not 30 -- unreachable from this sample (8 un-refetchable, 2 failed); NOT lowered, sample NOT re-drawn (seeing 21 then adding sections is the post-hoc selection the prereg forbids).
- The strip count: 23 of the required 30 exist, because 8 of the 31 sampled sections were unreachable at
  fetch time (rung 270 absent x7, one video unavailable); the sample was NOT re-drawn to manufacture more
  strips (B7) -- whether 23-of-30 clears the row is for the orchestrator to adjudicate.
- The 19 EXACT rows were never landmark-tested: none fell in the preregistered even sample, so they rest
  on hash-bound archived bytes alone (6 distinct source ids).
- Re-fetch provenance is in `refetch_sources.csv`, NOT appended to `sources.csv`: a 64-character digest
  there promotes a row to EXACT, so filing re-fetched bytes in it would relabel all 23 EXACT and destroy the distinction this row exists to make.
- `actual_first_pts` is UNKNOWN for 22 of the 23 re-fetched sections (the single-frame ffprobe interval
  returned no frame); the full-stream probe `align` uses returned stamps for all 23.
- `deploy_manifest_sha256` is UNKNOWN for all 884 rows: no game directory carries a producer code identity
  marker, so no archived table can be tied to the code that wrote it (A11 stays open).
- 765 of 884 rows have neither source bytes nor an alignment and stay UNKNOWN by construction; this row
  measured no tracking quality and moved no bar, flag, gate, register row or archived table.
