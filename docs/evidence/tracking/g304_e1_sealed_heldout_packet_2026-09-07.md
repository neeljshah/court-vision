# G304 E1 sealed held-out packet

Spec: [G304_spec.md](specs/G304_spec.md). Verifier contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), section B self-checked below.

Verdict: NOT VALIDATED. Denominators: 60 enumerated inventory rows, 0 selected eligible rows of 40 required, 0 selected negatives of 20 required, 0 held-out correspondences of 240 required, 2 broadcasts, 2 visually distinct arenas, and 1 available locator of 2 required. G306, G307, and G308 remain blocked.

## Premise confirmation

All work was local CPU-only. No pod, GPU, detector, fitting, homography, registration, prediction, calibration, or tracking route ran. The cited research source `docs/research/astra_tracking_registration_2026-09-07.md` is absent from this worktree; this memo uses the supplied G304 specification as the available binding copy.

| source | full path | bytes | stream | duration | SHA256 |
|---|---|---:|---|---:|---|
| A | `data/videos/bridge/wnba_01.f137.mp4` | 2,841,750,689 | h264, 1920x1080, 30/1 | 5814.333333 s | `f2421bc24e5cbb28f41fa79f9ea755b2eeff4daebd48dc5496cc97e5617cf9d3` |
| B | `data/videos/bridge/wnba_04.f137.mp4` | 1,114,349,874 | h264, 1920x1080, 30/1 | 3193.666667 s | `1331fba8c2544e3ef3f44ceb7ff2886d67faa3027cc07c4d6f1919d4d53dc166` |

ffprobe and byte-size checks match the declared originals. Each SHA256 was streamed one source at a time in 1 MiB blocks. The inventory eye check found distinct courts: A has a dark court with bright blue apron and Atlanta end branding; B has pale two-tone wood, forest-green paint/apron, and Seattle/Climate Pledge visual branding. This confirms arena distinctness by eye. The exact arena names remain transcribed rather than independently verified.

## Before

No E1 exists. E1, its second-attempt replacement packet, and reviewed seed atlases are prerequisites,
not claimed existing artifacts; none of the three is a completed artifact today, and this row does not
make one. The one prerequisite this row does confirm is a second native-1080p arena: `wnba_04` is
present locally at the declared bytes and its court is visibly distinct from `wnba_01`. Confirming that
arena is not the same as completing E1 -- the packet below stays an unvalidated inventory. E0 (the 17
G140 frames / 68 targets, of which 12 are native 1080p) is repeatedly inspected development material,
so a success on E0 is feasibility evidence only and never a held-out success.

## Sealed inventory and shortfall

The [manifest JSON](g304_e1_sealed_heldout_packet_manifest_2026-09-07.json) enumerates all 60 retained rows: 30 evenly spaced PTS positions through each full broadcast, with original dimensions, frame index, PTS, league, source hash, and a SHA256 for each decoded native-size render. No candidate, projection, homography, detector, registration result, or prediction was visible to the locator.

Eligibility would require identifiable, well-spread court evidence and six named landmarks across at least three marking structures. The frame-good rule sealed in the manifest is `p90 <= 12 px AND max <= 24 px`; its primary acceptance bars are copied there with no threshold moved. The sealed `primary_acceptance` string now also carries the spec's final clause, `zero false acceptances among the 40 eligible frames`, which the first seal had omitted; no bar changed value. Every row is retained as `UNRESOLVED_NO_INDEPENDENT_SECOND_LOCATOR`, with no inferred scope, shot identity, court end, or landmark values.

One available locator was `Codex G304 visual review`, a model locator. No independent second locator was available, so no native-zoom crop pair, inter-locator disagreement distribution, or >4 px adjudication can honestly be claimed. Unresolved labels mean INSTRUMENT NOT VALIDATED; they are not omitted frames and not successful abstentions. Agreement alone never establishes correctness.

The canonical-payload manifest SHA256 changed in this fix pass. Old seal: `6a1e7c76c44312b1ae79637166f4762b6923c25b789310cd72e45400393eb1b4`. New seal: `5806527e2d50c9830a12774e690e440dcda6a4e56fe04b933c676fd48aed14c1`, recomputed by `scripts/platformkit/tracking/seal_g304_inventory.py` over the same canonical payload (sorted keys, compact separators, ASCII) after the acceptance clause, the corrected frame indices, and the decode recipe were added. Consumers must quote the new seal. Both seals identify an unvalidated inventory, not a completed E1 evaluation packet. The 60 row IDs, the 60 decode SHA256s, the published PTS values, and both source SHA256s are byte-identical across the two seals.

Measured machine burden: source hashing 20.758 s total and decoding 60 native-size frames 20.1 s. Completed annotation burden is 0/60 because the independent second locator was absent; a future attempt must budget a second independently annotated crop set and adjudication for every disagreement above 4 px. Bytes added are itemised below.

## Frame index, PTS, and the durable decode recipe

`pts_seconds` is authoritative; `frame_index` is derived from it and is never an independent input.
Each render was produced by an input seek to the published six-decimal PTS, so the frame that lands is
the first frame at or after that seek time: `frame_index = ceil(pts_seconds * 30)`. The first seal
instead stored `round(exact_pts * 30)`, computed before the six-decimal rounding; that names a
different frame whenever the exact position falls below the half-frame boundary, which is 30 of the 60
rows -- not only the 6 that a `round(pts_seconds * 30)` comparison surfaces. All 30 were recomputed;
PTS, decode hashes, and source hashes are unchanged.

The rule was measured, not assumed. For every row the frame at `ceil(pts_seconds * 30)` is the closest
of the three candidates {k-1, k, k+1} to the committed render by mean absolute pixel difference, 60/60,
with the winner at 1.3-3.4 mean levels against a nearest rival of 3.5-57.3. Stronger: re-running
`ffmpeg -nostdin -v error -y -ss <pts_seconds> -i <source> -frames:v 1 -q:v 2 <render_path_local>`
reproduces the committed JPEG byte-for-byte, 60 of 60 rows re-verified, so `decode_sha256` is re-derivable from
`pts_seconds` alone. The manifest now carries that command and the ffprobe stream fields it depends on
(`codec_name=h264`, `codec_tag_string=avc1`, 1920x1080, `pix_fmt=yuv420p`, `r_frame_rate=30/1`,
`avg_frame_rate=30/1`, `time_base=1/15360`, `start_pts=0`; `nb_frames=N/A` on both sources) in a
`decode_recipe` block, and `tests/platformkit/test_g304_e1_packet.py` pins the rule over all 60 sealed
rows. The mismatch was not inherent variable frame timing: both sources are constant-frame-rate 30/1.

## Bytes added

`git diff --stat b8f7ab394^` reports 68 tracked changed paths, plus the verifier memo added by this fix
pass, for 69 paths in total. Byte sum of the additions across all of them:

| path | bytes added |
|---|---:|
| `g304_local_renders/` (60 row renders + 2 contact sheets) | 15,343,802 |
| `docs/evidence/tracking/g304_e1_sealed_heldout_packet_manifest_2026-09-07.json` | 49,256 |
| `scripts/platformkit/tracking/seal_g304_inventory.py` | 5,143 |
| `docs/evidence/tracking/G304_VERIFY_2026-09-07.md` | 4,927 |
| this memo | 9,329 |
| `tests/platformkit/test_g304_e1_packet.py` | 3,933 |
| `scripts/platformkit/tracking/g304_e1_packet.py` | 2,981 |
| `docs/evidence/tracking/RESULTS_LEDGER.md` (one appended line) | 601 |
| total, 69 paths | 15,419,972 |

No corpus source, and no bridge partial download, was changed or deleted.

## Fix pass 1b (verifier corrections applied)

- `scripts/platformkit/tracking/g304_e1_packet.py:44` reads `source_rows`, the key the manifest
  actually writes, instead of the absent `sources`; each arena is now checked for its own 4/3/3
  negative split and its own four-shot minimum, so a per-arena-invalid packet can no longer return
  zero validator errors.
- `docs/evidence/tracking/RESULTS_LEDGER.md` was restored to its parent bytes (451 UTF-8/LF lines) and
  the G304 row appended as a single UTF-8/LF line; the whole-file CRLF rewrite and the UTF-16LE line
  are gone, and `git diff --numstat b8f7ab394^` on the ledger is 1 / 0.
- `primary_acceptance` carries the zero-false-acceptance clause and the packet was resealed.
- The before-condition paragraph above states that no E1 exists.
- All 60 `frame_index` values follow the measured `ceil(pts_seconds * 30)` rule and the manifest
  records the durable decode recipe.
- Total bytes added are reported above for all 69 touched paths.

## NOT VERIFIED

- The transcribed arena names beyond visual distinctness.
- All 60 selection classifications, the per-arena 20/10 and 4/3/3 composition, and the at-least-four-shot condition.
- 240 held-out landmark correspondences across three marking structures.
- A second independent locator, inter-locator agreement, and all required adjudications.
- Any registration, calibration, prediction, detector, or tracking quality. This row measures none of them.
- E1 itself, its replacement packet, and reviewed seed atlases: none is a completed artifact.

## Contract B self-check

B1: no metric is computed and no row was dropped. B2-B6: additive new files only, no schema reader or deployment changed. B7: the inventory is evenly spaced across each complete duration, not a head slice. B8-B10: no fit, residual, denominator reuse, or threshold change occurred.
