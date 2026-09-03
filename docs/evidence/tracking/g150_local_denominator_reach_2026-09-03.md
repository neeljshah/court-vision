# G150 local decoded-frame denominator reach

Contract: [`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7, section B, and Q8. This is a local-only measurement. No harness, threshold, coordinate contract, verdict, table, video, pod, or process was changed.

## Result

**CLOSED AT LIMIT.** **0 / 361 local tracking tables carry a recoverable, auditable decoded-frame denominator.** The **ELIGIBLE denominator is all 361 surviving local table directories**: every distinct `data/tracking/*/tracking_data.csv` match. It is exhaustive (`n = 361 CONSTRUCT`), and no table was removed because it was empty, malformed, missing metadata, or unrecoverable.

The premise's table count holds: a one-level directory enumeration of `data/tracking/*/tracking_data.csv` returns 361 matches. Its jump-gate premise is falsified: the same local census finds **1**, not zero, that reaches the pre-registered jump calculation. `G83_tennis_09` has declared `court_feet`, 38 distinct frames, required player fields, and one unique positive same-track modal stride of 2. The other 360 fail an earlier prerequisite: 358 lack a coordinate declaration in the legacy header, `mlb_2iosUkpL0Bc` declares `image_px`, and `failclosed_smoke` is header-only. This premise correction does not create a decoded denominator.

## Recoverability census

The per-table, exactly-one-bucket census is [`local_table_recoverability.csv`](g150_denominator/local_table_recoverability.csv).

| Recoverability bucket | Tables | Basis |
|---|---:|---|
| `RECOVERABLE_DECODE_MANIFEST` | 0 | No persisted decoder-derived manifest is paired to a current table. |
| `RECOVERABLE_LEDGER` | 0 | No local `track_daemon_ledger.jsonl` exists. |
| `RECOVERABLE_SIBLING_ARTIFACT` | 0 | All 2,999 direct sibling CSV headers were checked; none records a decoded-frame field. The 331 direct `run.log` files also contain no decoded-count record. |
| `RECOVERABLE_LOCAL_VIDEO` | 0 | No surviving table has an auditable persisted pairing to a local source video. |
| `NOT_RECOVERABLE` | 361 | Sum of the four zero recoverable buckets' complement; every table is named in the CSV. |

The four legacy `manifest.json` files are explicitly retained as `NOT_RECOVERABLE`: three positive `total_frames` values and one `-1` are not decoder-derived counts. The pipeline writes this field from processed `frame_idx`, not the `ffprobe -count_frames` / `nb_read_frames` contract. Their CSV evidence codes are `LEGACY_MANIFEST_FRAME_IDX` or `LEGACY_MANIFEST_NEGATIVE`.

The only tempting local source candidate is also not promoted. `data/footage_corpus/tennis__tennis_09.mp4` is present and a local decoder pass returns 7,501 frames, but the retained source census pairs it to absent `g89_tennis_09`, not to current `G83_tennis_09`. The current G83 directory has no manifest, ledger row, or other persisted table-to-video pairing. A suffix match is not auditable provenance, so the CSV records `LOCAL_VIDEO_UNPAIRED` and the 7,501 count is not used.

## Coverage comparison

There are no recoverable tables, so there are **no current-versus-corrected coverage pairs and no ratios**. This local population therefore **cannot say** whether its inflation agrees with G147's 2.5x--4.9x legacy-tennis reproduction. No frame-span, emitted-row count, container header, duration-times-FPS estimate, or unpaired-video decode was substituted as a denominator.

To make this comparison computable, the producer must persist the decoder-derived `decoded_frames` count together with an auditable source identity (at minimum the selected source filename and SHA-256) in a decode manifest or ledger row associated with the exact tracking-table directory.

## Three raw-CSV hand cross-checks

1. `G83_tennis_09`: the physical CSV has 88 lines: `1` header + `87` data rows. The raw rows contain two player rows for each of the 38 frame values 0, 2, ..., 74, hence `2 * 38 = 76` player rows; the remaining `87 - 76 = 11` are ball rows. All 38 frames have the required two players, so the unchanged harness numerator arithmetic is `38 / 38 = 1.0000`. This validates the stated jump-gate recheck but supplies no source denominator.
2. `0022400625`: the physical CSV has 2,585 lines: `1` header + `2,584` data rows, matching the raw-table reader count. Its sibling `manifest.json` has `total_frames=367977`; this is rejected because the producer writes processed `frame_idx`, not a decoded-frame count.
3. `failclosed_smoke`: the physical CSV has exactly `1 = 1` header + `0` data rows. It is included in the 361-unit denominator and classified `NOT_RECOVERABLE`, rather than being silently dropped.

## Verifier-contract self-check

### A

- **A1:** No code was added, so no per-file test applies; no full suite was run.
- **A2:** Recomputed the 361 table count from the committed CSV and independently from the one-level local glob; all 361 rows are `NOT_RECOVERABLE`.
- **A3:** The metric is an exhaustive construct census, not a render metric. The three required raw checks above cover a recoverable-looking table, a legacy-manifest table, and a header-only table rather than a head slice.
- **A4:** The unit is a distinct table directory. The CSV has 361 unique `table_id` values and 361 unique `tracking_csv` values.
- **A5:** Evidence only; no field, schema, or reader changed.
- **A6:** This worktree makes an explicit-path evidence commit only. Archive landing, ledger/register append, and any master-side action remain verifier work.
- **A7:** At self-check, this memo, the per-table CSV, the G150 spec, the verifier contract, and the cited G116 source census all exist.

### B

- **B1:** Clear. Every glob match is named before the zero result; no unrecoverable or empty table was excluded.
- **B2:** Clear. No schema or field changed.
- **B3:** Clear. Missing evidence is recorded as `NOT_RECOVERABLE`, not treated as a bad-quality verdict or quarantined.
- **B4:** Clear. No claim lifecycle changed.
- **B5:** Clear. No pod connection, deploy, copy, restart, or tracking run occurred.
- **B6:** Clear. No module, import, test, or command moved.
- **B7:** Clear. The 361-table census is exhaustive; the three raw checks are deliberately non-head cases.
- **B8:** Clear. No fit or residual is reported.
- **B9:** Clear. Each denominator unit is one distinct local table directory, never a frame, row, or track ID.
- **B10:** Clear. `tracking_harness.py`, the 0.90 bar, every threshold, coordinate contract, and existing verdict remain untouched.

### Q8

- **Premise re-measured:** table count is confirmed at 361; zero jump-gate eligibility is falsified by the one named G83 table. This is reported as a valid premise correction, not hidden or used to manufacture a coverage result.

## NOT VERIFIED

- A decoded-frame denominator or corrected coverage for any of the 361 local tables.
- Any local table-to-video association not persisted in a manifest, ledger, or sibling artifact.
- Whether the unpaired `tennis__tennis_09.mp4` is byte-identical to the source of `G83_tennis_09`.
- Whether a future producer artifact will retain the exact source identity and decoder count needed for this comparison.
- Any pod state, deployment, re-tracking, test-suite result, or threshold/verdict change.
