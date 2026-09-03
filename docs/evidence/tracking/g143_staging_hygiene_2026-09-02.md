# G143: local bridge staging hygiene

## Verdict

ACCEPT: during 40 minutes and 1 second of undisturbed, live bridge operation,
`data/videos/bridge` stayed at 1,507,324,921 bytes in 17 files. This is a
bounded observed window, not a claim that every failure path is safe forever.
No cleanup change is recommended because no real staging leak was measured.

## Scope and method

The target was the local bridge stage, `data/videos/bridge`. Its configured
owner is `scripts/platformkit/footage_bridge.py:66`; its distinct remote pod
stage is `data/footage_bridge`. At the observer's start, seven
`footage_bridge --forever` workers and two `scp` uploads from the local stage
were live. No worker, fetcher, or pod process was killed, restarted, or
otherwise changed. `data/videos/reference` was not read, modified, or deleted.

The observer enumerated every regular file recursively at each interval and
summed `Length`. Its committed raw record is
`g143_hygiene/g143_staging_samples_2026-09-02.csv`.

| Timestamp | Bytes | Files |
| --- | ---: | ---: |
| 2026-09-02 21:53:47 -05:00 | 1,507,324,921 | 17 |
| 2026-09-02 22:03:48 -05:00 | 1,507,324,921 | 17 |
| 2026-09-02 22:13:48 -05:00 | 1,507,324,921 | 17 |
| 2026-09-02 22:23:48 -05:00 | 1,507,324,921 | 17 |
| 2026-09-02 22:33:48 -05:00 | 1,507,324,921 | 17 |

The five timestamps are evenly spaced at ten-minute intervals. The window is
40 minutes and 1 second; it exceeds the required 30 minutes and has five
samples (required: at least four).

## Cleanup-path audit

`_purge_leftovers(destination)` (`footage_bridge.py:277`) unlinks every
top-level path matching `destination.stem + "*"`. For `game.mp4`, this covers
`game.mp4`, `game.f137.mp4`, `game.mp4-FragNNNN`, and `game.mp4.ytdl`, as well
as other same-prefix siblings. It neither descends into directories nor matches
another base prefix. It runs after a 416 resume failure, requested-height
failure, low section height, or local section-cut failure.

The per-item `finally` (`footage_bridge.py:656-665`) applies the same
top-level prefix cleanup only when `download_local` returned a `local` file and
the successful item is not retained as the sport reference. `_resolve_download`
(`footage_bridge.py:209-218`) deliberately refuses `.part`, `.ytdl`, `-Frag`,
and `.fNNN.` files as a successful result.

| Item route | Patterns removed | Patterns that can survive |
| --- | --- | --- |
| Completed, not retained as reference | All top-level `local.stem*` siblings, including merged media, `.fNNN.mp4`, `-FragNNNN`, and `.ytdl`. | No matching top-level `game*` artifact. Nested paths are not traversed. |
| Completed and retained as reference | The primary file is moved to `data/videos/reference`; the normal sibling cleanup is bypassed. | Any existing same-prefix yt-dlp sidecar can remain in local staging. Nested artifacts, such as `verification/*.jpg`, are never matched by this glob. |
| Failed with 416, height/section validation, or section-cut failure | `_purge_leftovers` removes the same top-level `game*` family before retry. | No matching top-level family after that purge, absent a later write. |
| Terminal timeout or non-416 yt-dlp failure | None on the terminal failure route: `download_local` raises, `local` remains `None`, and `finally` skips cleanup. | `game.mp4`, `game.f137.mp4`, `game.mp4-FragNNNN`, and `game.mp4.ytdl` can survive until a later retry happens to purge or complete them. |

The last row is a code-path exposure, not an observed accumulation in this
window. The existing focused bridge tests demonstrate the 416 `.ytdl` purge and
fragment exclusion from resolution, but do not exercise terminal non-416
failure cleanup.

## Risk bound

Observed staging growth is `(1,507,324,921 - 1,507,324,921) bytes / 40.0167 h
= 0 bytes/h`; file-count growth is also `0 / 40.0167 h = 0 files/h`. Using the
specified current 963 GB headroom, the staging-only runway at the observed rate
is `963 GB / 0 GB/h`, which has no finite hour value (infinite hours at this
observed rate). This is not a prediction of other disk consumers.

## NOT VERIFIED

- A terminal non-416 or timeout failure did not occur in the observation, so
  the code-path exposure above was not measured in production.
- The provenance of each pre-existing file in the 17-file staging set was not
  reconstructed; filenames alone cannot label an item completed or failed.
- Behavior beyond this 40-minute live window, and after a killed worker, was
  not measured. Deliberately killing a worker would violate this task.
- Whether yt-dlp leaves a sidecar on a successful reference-retained item was
  not observed; the bypass is established by the cleanup control flow.

## Verifier-contract self-check

| Contract item | Result |
| --- | --- |
| A1 | `python -m pytest scripts/platformkit/test_footage_bridge.py -q` was rerun in the master checkout: 43 passed in 1.16 s. No code changed and no new test was required. |
| A2 | Recomputed directly from the committed CSV: first and last bytes are both 1,507,324,921; delta is 0. |
| A3-A4 | The five time samples are evenly spaced, and file counts are recursive filesystem enumerations, not duplicate rows or head slices. |
| A5 | No source fields or readers changed. |
| A6 | Evidence is committed in worktree `a5` with explicit pathspecs. The master checkout had unrelated concurrent modifications to the shared ledger and tracking gap register, so no archive/ledger/register write was made there. A clean-master verifier must perform that landing step. |
| A7 | At self-check, both named evidence paths exist: this memo and `g143_hygiene/g143_staging_samples_2026-09-02.csv`. |
| B1-B10 | Checked: no exclusions, schema changes, gates, re-claims, deployment, retired modules, head-slice evidence, fitted metric, degenerate denominator, or threshold changes. |
