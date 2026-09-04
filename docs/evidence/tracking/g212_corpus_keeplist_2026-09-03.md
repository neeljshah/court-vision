# G212 Corpus Keep-list

## Result

This is an analysis and keep-list only. No corpus byte was deleted, moved,
renamed, decoded, or opened for inference. No daemon, keeper, bridge, watchdog,
or deployment action was taken.

The live pod snapshot contains exactly 12 top-level corpus sources totaling
25,959,096,378 bytes. The candidate-list contains zero deletion candidates.
This is the correct full-success result: two current readers dynamically
enumerate every source, so every source is cited. Durability is necessary but
not sufficient and does not override a reader citation.

The complete per-source lists are committed as:

- `g212_corpus_keep_list_2026-09-03.csv`
- `g212_corpus_candidate_list_2026-09-03.csv`

`candidate=no` on every row is intentional. The candidate file is a complete
decision ledger rather than an empty header-only artifact, so it records why
each source failed the candidate predicate.

## Snapshot and construct

The unit is each top-level `data/footage_corpus/*.mp4` file on the pod at the
metadata snapshot. The construct excludes local worktree cache and archival
copies under the local `data/footage_corpus/g130_recensus/`, bridge staging,
`.part` files, images, logs, and all non-`.mp4` files. Those are not live
corpus sources. It also excludes sources destroyed before G180, because they
are not resident and cannot be reconstructed as byte-identical sources.

The pod command was metadata-only: it enumerated top-level `*.mp4`, used
`stat` for source/tracking/verdict byte sizes, and used `du -sb` for aggregate
usage. It did not use OpenCV, ffprobe, frame counting, `run_clip.py`, an
adapter, or any inference path.

| Snapshot quantity | Bytes |
|---|---:|
| Sources | 12 |
| Corpus sources | 25,959,096,378 |
| Pod `data/` | 40,343,530,027 |
| Recoverable if every candidate were deleted | 0 |
| Resulting `data/` usage | 40,343,530,027 |

For headroom arithmetic, the stated working figure is treated as 50,000,000,000
bytes. This final snapshot has 9,656,469,973 bytes below that figure and is
343,530,027 bytes above the prior 40,000,000,000-byte alert level. Zero
recoverable bytes does not create operational headroom. The corpus therefore
still outgrows this volume as acquisition continues; the real remedy is an
infrastructure or retention-policy decision by the user, not a manufactured
deletion candidate.

## Durability cross-check

For this G212 necessary screen, `yes` means the matching `tracking_data.csv`
and `harness_verdict.json` both existed and had a positive byte size in the
metadata snapshot. It does not parse the verdict and is not a claim that a
source is safe to delete. The stricter daemon predicate also requires a data
row and required fsynced verdict fields; G212 did not invoke it because every
source is already retained by reader citations.

Eleven of 12 files pass the presence/size screen. The NCAA protected source
has neither sidecar. `wnba__wnba_01.mp4` currently has positive-size sidecars,
but is protected by the explicit G212 rule irrespective of that observation.

## Re-derived A5 source-reader survey

### Reproducible search method

1. Ran this tracked-executable literal path search from the `track-a7` root:

   `git grep -l -i -E 'footage_corpus|FOOTAGE_CORPUS|POD_ROOT' -- '*.py' '*.sh' '*.ps1' '*.bat' '*.cmd'`

2. Inspected every returned executable. A match was counted only when its code
   opens, decodes, submits to a video processor, or otherwise re-emits a
   concrete corpus source. Mere transport, dedupe, fixture, junction, path
   string, and code-hash uses were recorded as exclusions below.

3. Checked untracked executable coverage with:

   `git ls-files --others --exclude-standard -- '*.py' '*.sh' '*.ps1' '*.bat' '*.cmd'`

   It returned no untracked executable paths.

4. Read the manifests consumed by the resulting readers and intersected their
   named clips with the live 12-source snapshot. Generic passed-path video
   helpers are not separate corpus readers: they name or enumerate no corpus
   source and only open a path supplied by one of the counted callers.

The direct path search found 20 executable paths. Eleven are true corpus-source
readers. The remaining nine are named in the exclusions section.

| ID | Reader | Current required sources | Requirement type |
|---|---|---|---|
| R01 | `scripts/platformkit/tracking_corpus_ab.py` | Every current source | Dynamic: its corpus selector enumerates sport-family clips. Across supported sport runs it needs the whole corpus. |
| R02 | `scripts/platformkit/tracking/footage_census.py` | Every current source | Dynamic: `discover_clips` iterates every top-level video in the default corpus directory. This alone is decisive. |
| R03 | `scripts/platformkit/basketball_relabel_image_px.py` | Conditional WNBA/NCAA sources formed from current tracking directories | Dynamic conditional: `--reemit-out` forms a source filename for every basketball tracking target. At snapshot, no current target had the required `.pre_relabel` input, so it has no additional successful live re-emission; it is not needed to make the no-candidate result. |
| R04 | `scripts/platformkit/g103_g68_tile_recipe.py` | `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`; `wnba__wnba_01.mp4` | Named through the fixed G84 manifest (which also names nine historical absent sources). |
| R05 | `scripts/platformkit/g110_tile_nonreproducibility.py` | Same two current basketball sources as R04 | Named through the G103 tile manifest used for seek/sequential reconstruction. |
| R06 | `scripts/platformkit/g126_g111_label_audit.py` | Same two current basketball sources as R04 | Named through the fixed G111 labels and G126 blind-selection manifest. |
| R07 | `scripts/platformkit/g137_qualifying_frame_scale.py` | Both current basketball sources | Dynamic for `--sample`: it inventories every resident `ncaa_basketball__*.mp4` and `wnba__*.mp4`; the frozen G137 manifest also names both. |
| R08 | `scripts/platformkit/g148_two_slot_measure.py` | None of the 12 by default | Its fixed defaults are three historical tennis files (`tennis_09`, `tennis_10`, `tennis_459iho5_AFs`); `--clips` can explicitly target a later tennis source. |
| R09 | `docs/evidence/tracking/g52_reproducibility/g52_driver.py` | None of the 12 | Fixed historical tennis sources: `tennis_nyYk2nPZAwY_720p`, `tennis_09`, `tennis_10`. It runs range processing and a decode probe when invoked. |
| R10 | `docs/evidence/tracking/g52_reproducibility/local_range.py` | None of the 12 | Fixed historical `tennis_nyYk2nPZAwY_720p` range run. It hardcodes the old main-worktree path and is not runnable from this A7 worktree without changing it. |
| R11 | `docs/evidence/tracking/g52_reproducibility/local_range2.py` | None of the 12 | Same fixed historical `tennis_nyYk2nPZAwY_720p` range runs and old main-worktree path. |

Relative to the seven readers named in the G212 prompt, R08 is an additional
platformkit reader. The committed G180 memo did list R08, so the discrepancy is
between the prompt's seven-name summary and that memo, not a new G180 discovery.
R09-R11 are additional legacy evidence readers that G180's stated search scope
excluded because they are tracked executable files under `docs/evidence/`.
All seven readers named in the prompt still exist. No named G180 reader was
found to have been removed.

## Exclusions from the direct executable matches

| Path | Why it is not a corpus source reader |
|---|---|
| `scripts/platformkit/baseball_s4_emission.py` | Compares a manifest string and uses already-emitted JPEG paths; it does not open the corpus video. |
| `scripts/platformkit/footage_bridge.py` | Transport/staging/retain path; it does not re-open a retained corpus source for evidence regeneration. |
| `scripts/platformkit/test_baseball_s4_emission.py` | Temporary fixture only. |
| `scripts/platformkit/test_footage_bridge.py` | Mocked command strings and temporary files only. |
| `scripts/platformkit/test_track_daemon.py` | Temporary test corpus only. |
| `scripts/platformkit/track_daemon.py` | Consumes staged sources and retains them; it does not enumerate and re-measure retained corpus sources. |
| `scripts/platformkit/tracking/pod_drift.py` | Hashes code modules only. |
| `scripts/platformkit/tracking/worktree_data_links.py` | Creates/exposes a worktree junction only. |
| `scripts/runpod_backup_to_b2.sh` | Reads `/root/nba_videos`, not `data/footage_corpus`. |

## Candidate predicate and result

A source could be a candidate only if all three conditions held:

1. Its tracking CSV and verdict sidecar both passed the necessary durability
   screen.
2. No reader cited or dynamically selected it.
3. It was not either protected source:
   `wnba__wnba_01` or `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds`.

No source satisfies condition 2 because R01 and R02 select every current source.
The candidate count and recoverable bytes are both zero. This does not mark any
tracking threshold, harness verdict, or source quality as changed.

## Before and consequence

G180 correctly refused to land retention after finding source re-measurement
readers. Before that survey, 23 sources totaling about 22.9 GB had already been
destroyed in manual passes that used durability alone. The footage bridge is
growing the corpus again, and source bytes move from stage to corpus rather
than leaving the volume. This keep-list does not repeat that error: it removes
nothing and does not supply deletion code.

## NOT VERIFIED

- The semantic content of positive-size tracking CSVs and verdict JSON files:
  this row used metadata-only pod queries and did not parse them.
- Whether each historical source named by R04-R11 can be re-downloaded or is
  byte-identical to its original. G110 exists because that cannot be assumed.
- The future corpus membership after this snapshot; bridge activity can change
  it immediately, so a future retention decision needs a fresh snapshot and a
  new reader cross-check.
- A storage expansion, off-volume archive, or any revised retention policy.
  Those are infrastructure decisions for the user.
