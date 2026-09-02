# G110: why G68 source tiles do not reproduce while G84 renders do

## Result

**CLOSED AT LIMIT for durable source-tile reconstruction.** The apparent
contradiction has two distinct stages and two distinct causes:

1. G84/G97 rebuilds from the surviving decoded G68 contact-sheet crops. It
   therefore starts from the exact intermediate pixels that produced the
   committed render. Its 33/33 byte-exact render result is valid.
2. G103 rebuilds from the current pod video and writes an independent JPEG
   tile. For 30/33 fixed frames, the current picture is materially the same
   but the original was a crop of a quality-95 JPEG contact sheet and the
   rebuild is a direct quality-92 JPEG tile. Decoded pixels are not expected
   to be identical across those write paths. For the three `WFl3V7ZY4ss`
   frames, the current source stream is also on a different timeline at the
   recorded index, so the pictures themselves differ.

The named cause of G103's 0/33 is therefore **a non-equivalent source-tile
construction path, compounded by a source-stream timeline/provenance change
for WFl3V7ZY4ss**. It is not a current frame-seeking failure.

## Fixed all-33 pixel triage

[`pixel_triage.csv`](g110_tiles/pixel_triage.csv) compares every one of the
33 unique fixed `(clip, frame_index)` identities. Its original decoded crop
SHA-256 agrees with G103's frozen source-tile manifest for all 33. The
comparison results are:

| comparison | result |
|---|---:|
| original decoded crop pixel-identical to rebuilt seek JPEG | 0/33 |
| current seek raw pixels identical to current sequential raw pixels | 33/33 |
| low-delta, same-picture reconstruction evidence | 30/33 |
| visibly different-content reconstruction | 3/33 |

The 30 low-delta items have per-tile mean absolute channel deltas from 0.079
through 4.487; the three WFl items have 66.747, 86.627, and 99.051. Every
pixel equality, changed-pixel share, raw SHA-256, and delta is retained in
the CSV. This is a full fixed set, not a head slice.

The seek/sequential check is decisive for candidate (a): both modes decode
the same current raw pixels for all 33 named indices. No B-frame seek behavior
can explain the mismatch at those current inputs.

Current pod FPS, frame count, dimensions, and duration for all eleven clips
are retained in [`current_source_metadata.csv`](g110_tiles/current_source_metadata.csv).
G68 did not preserve the corresponding historical file metadata or checksum,
so a file-level before/after comparison is not possible.

For the WFl source, a whole-current-stream low-resolution search locates old
sheet frame 2483 at current frame 20466 (mean grayscale delta 0.760) and old
sheet frame 2865 at current 20848 (1.095), not at their recorded indices.
The third old frame has no comparably exact current match. The complete result
is [`wfl_provenance_search.csv`](g110_tiles/wfl_provenance_search.csv). This
supports a re-acquired or differently trimmed source stream; without the old
file metadata, the precise acquisition event remains unverified.

## Eye check

All 33 original/rebuilt pairs are preserved as compact side-by-side JPEGs in
[`g110_tiles/side_by_side/`](g110_tiles/side_by_side/); no 116 MB contact
sheet set was copied. I inspected these two source-spaced examples:

- [`IB-_u4gW3ds f19200`](g110_tiles/side_by_side/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__f19200.jpg)
  shows the same UConn/Michigan court picture on both sides, despite decoded
  pixel mismatch from the contact-sheet versus direct-tile write path.
- [`WFl3V7ZY4ss f2865`](g110_tiles/side_by_side/ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss__f2865.jpg)
  shows a close-up in the original crop and in-play court action in the
  rebuild. This is content divergence, not an encoder-only difference.

## G93 disposition

**G93 is not run and remains NOT VERIFIED.** The committed G84 renders are
enough to inspect visible paint lines, and
[`per_group_labels.csv`](g84_candidate_quality/per_group_labels.csv) retains
all candidate endpoints: its per-frame counts match the fixed G84 manifest
for 33/33 frames. They are not, however, sufficient to run the frozen G93
program unchanged. The program deliberately reruns the fixed detector on an
unannotated source tile; every G84 render contains its yellow candidate-line
and index overlays, which alter that detector input.

The surviving untracked main-worktree contact sheets could make a local
one-off rerun possible, but they are outside this worktree and are explicitly
not durable source evidence. Copying the 116 MB sheet set or replacing G93's
fixed raw-tile detector call with archive endpoints would change the evidence
interface. Neither is a valid G93 unblocking action. Accordingly there is no
G93 recall table, Wilson interval, or miss-reason histogram to report.

## Reproduction

With the surviving original sheets available read-only, run:

```text
python -m scripts.platformkit.g110_tile_nonreproducibility --source-sheets <g68_contact_sheets>
python -m scripts.platformkit.g110_tile_nonreproducibility --source-sheets <g68_contact_sheets> --provenance-search
python -m pytest tests/evidence/tracking/test_g110_tile_nonreproducibility.py -q
```

The probe only reads the pod clips and writes the compact local evidence
listed above. It does not copy to, deploy to, or otherwise mutate the pod.

## Verifier contract self-check

- A7: every path named in this memo exists at verification time: this memo,
  the three CSVs, all 33 side-by-side JPEGs, the G84 manifest/endpoint CSV,
  the diagnostic entry point, and its one focused test.
- B1: all 33 frozen identities are retained. The 30/3 split is descriptive;
  no row was excluded from the 0/33 or 33/33 metrics.
- B2: all additions are new files. No existing field, status, reader, or
  schema changed.
- B3-B5: no gate behavior, claim lifecycle, deployment, pod file, or feature
  flag changed.
- B6: no module was moved or retired.
- B7: all fixed G84 identities are evaluated, not a head slice; eye checks
  intentionally show both a low-delta and high-delta clip family.
- B8-B9: no fit or recycled denominator is presented. The unit is one unique
  fixed source tile.
- B10: G93 protocol values, G84 sample/seed, detector parameters,
  `line_calibration.py`, thresholds, and the coordinate contract are untouched.

## Not verified

- The exact historic WFl file hash, duration, FPS, and acquisition event were
  not preserved by G68. The evidence proves its recorded frame indices no
  longer address the same current pictures, but cannot distinguish every
  possible re-acquisition/trimming mechanism.
- A direct 33/33 pixel-exact reconstruction from current source video is not
  established. The original contact-sheet write path has not been retained as
  a durable, byte-reconstructible recipe.
- G93 hand marks, per-role recall, Wilson intervals, and miss-reason histogram
  remain unmeasured. No substitute measurement is claimed.
