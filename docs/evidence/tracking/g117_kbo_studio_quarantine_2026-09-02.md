# G117 KBO studio-programme quarantine

**Verdict: ACCEPT.** Twelve KBO corpus clips are predominantly non-game
studio/statistics programming under the predeclared five-frame rule. All
twelve were confirmed by eye and reversibly moved to
`data/footage_quarantine/`; no clip was deleted, re-tracked, copied to the
bridge, or otherwise scored. This memo follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7 and the section B
self-check below.

## Rule and candidate set

Before the G117 review, a clip was defined as predominantly non-game only if
at least 4 of 5 spread frames (80 percent) were not `live_action`. The strict
supermajority avoids quarantining a marginally mixed broadcast. The label
vocabulary, selection construction, and quarantine convention were frozen in
[`g117_studio/protocol.md`](g117_studio/protocol.md) before the two added
frames were inspected.

The preliminary set was the twelve KBO clips with 0/3 live-action labels in
G113. For each, the eye check used the three retained G113 interior frames
plus mechanical 20 percent and 80 percent source-frame seeks. The exact
zero-based keys and panel order are in
[`g117_studio/review_manifest.csv`](g117_studio/review_manifest.csv); all 60
individual labels are in [`g117_studio/labels.csv`](g117_studio/labels.csv).
Every labelled panel is either `studio_or_desk` or `graphic_or_scoreboard`.

| Clip | Live / 5 | Live-action share | Confirming sheet |
|---|---:|---:|---|
| `kbo__kbo_2WqtNa-uUZU.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_2WqtNa-uUZU.jpg) |
| `kbo__kbo_8yxSFxuR2Lk.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_8yxSFxuR2Lk.jpg) |
| `kbo__kbo_9Hv-cd-BmSY.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_9Hv-cd-BmSY.jpg) |
| `kbo__kbo_ahHGpSJWcIU.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_ahHGpSJWcIU.jpg) |
| `kbo__kbo_bGQwZl43E9Y.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_bGQwZl43E9Y.jpg) |
| `kbo__kbo_FDSWjM_OaTs.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_FDSWjM_OaTs.jpg) |
| `kbo__kbo_Lh8n_DUXyGE.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_Lh8n_DUXyGE.jpg) |
| `kbo__kbo_lIxmDQyQDtc.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_lIxmDQyQDtc.jpg) |
| `kbo__kbo_lrK_Hv6BEE0.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_lrK_Hv6BEE0.jpg) |
| `kbo__kbo_qLQbGFQ0-EQ.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_qLQbGFQ0-EQ.jpg) |
| `kbo__kbo_tzC71aneg9c.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_tzC71aneg9c.jpg) |
| `kbo__kbo_W-tKSex-WPU.mp4` | 0 / 5 | 0.000 | [sheet](g117_studio/sheets/kbo__kbo_W-tKSex-WPU.jpg) |

Thus the measured G117 result is **12 clips, each 0/5 live action**, not a
duration-weighted estimate of every frame in each source. The remaining KBO
clip, `kbo__kbo_tHih8xD7MSY.mp4`, had 3/3 G113 live-action labels and was not
a candidate or moved.

## Reversible quarantine

Following `footage_content_gate.quarantine_manual`, each confirmed source was
moved from `data/footage_corpus/` to `data/footage_quarantine/` and received
an adjacent JSON sidecar with reason
`human_confirmed_predominantly_studio_or_statistics_programming_g117`,
`sport_verified: false`, and `metrics: null`. The source-to-target receipts,
including preserved byte counts, are committed in
[`g117_studio/quarantine_receipts.csv`](g117_studio/quarantine_receipts.csv).
The post-move check found all twelve corpus sources absent, all twelve
quarantine targets and sidecars present, and zero bridge moves.

## Existing gate assessment

The existing [`footage_content_gate.py`](../../scripts/platformkit/footage_content_gate.py)
does **not** detect this studio-programme content. Its code samples nine seeks
and accepts on playing-surface colour and shot continuity; it is explicitly an
ingest-only, fail-open screen rather than a `live_action` classifier. I ran it
against these same twelve source clips before the move: every one returned
`accept`, `playing_surface_and_shot_continuity_present`, with nine sampled
frames. The retained results are
[`g117_studio/gate_verdicts.jsonl`](g117_studio/gate_verdicts.jsonl).

Therefore the fix is **not simply to apply the gate already present**: the
gate does not distinguish a baseball studio show, whose graphics and set
include field imagery, from contest coverage. No second gate was written in
this row.

## Exposure boundary; no recomputation

- **Direct exposure: G104 baseball landmark reachability.** Its 120-frame
  primary denominator includes 20 sampled frames from each of
  `kbo__kbo_FDSWjM_OaTs.mp4` and `kbo__kbo_bGQwZl43E9Y.mp4`, both now
  quarantined. Those 40 rows were already retained as non-game programme
  content; its published visible-point rates are 13/120 for at least two,
  3/120 for at least three, and 1/120 for at least four. This row names the
  exposure only and does not replace G104's denominator or recompute it.
- **Explicit non-exposure: G11 baseball night pitch-view fractions.** G11's
  four published fractions use 398 decodable targets for each of two named
  MLB clips, not any of these twelve KBO filenames. It remains a whole-clip
  quantity but is not a measurement over the quarantined clips.
- **Broader corpus boundary:** G34's view/rally shares and daemon coverage
  figures are intentionally whole-broadcast operating quantities, not
  detector-quality rates to revise from this review. No published value is
  recomputed here.

## NOT VERIFIED

- The 0/5 shares are five spread-frame review results, not duration-weighted
  live-action shares or a permanent property of future versions of a clip.
- One observer supplied the labels; there was no blinded second pass or
  inter-rater measurement.
- This row proves the current gate's twelve false accepts, not the precision
  or recall of a prospective live-action classifier.
- No detector, coordinate contract, existing threshold, prior verdict, or
  published baseball measurement was changed or recomputed.

## Verifier self-check

- **A2/A4:** the committed label artifact has 60 rows and 60 unique
  `(file_name, source_frame)` keys; it groups to 12 clips with exactly five
  frames each and 0 live-action labels per clip. **A3/B7:** each sheet spans
  the three G113 interior strata plus fixed 20 and 80 percent seeks, not a
  head slice. **A5:** no production field or reader changed. **A6:** this
  worktree commit uses explicit evidence pathspecs only; no master landing is
  attempted by this lane. **A7:** at memo time, the protocol, manifest,
  labels, gate verdicts, receipts, and all twelve sheet paths named above
  exist locally.
- **B1 circular metric:** clear. Candidates were selected by named 0/3 G113
  labels, then every five-frame row for every candidate was retained and
  labelled; none was discarded for its content.
- **B2 non-additive schema:** clear. This is additive evidence only; no
  schema, field, status value, or reader changed.
- **B3 fall-through loss / B4 re-claim loop:** clear. The existing manual
  quarantine convention supplies a reversible sidecar and `is_quarantined`
  recognition; no gate or claim behavior changed.
- **B5 pre-verification deploy:** clear. No code or file was deployed to the
  pod; only the expressly permitted post-eye-check quarantine moves occurred.
- **B6 orphans:** clear. No module, test, import, or command moved or retired.
- **B8 self-fit as independent:** clear. This is an eye-content review, not a
  fitted residual. **B9 degenerate denominator:** clear; units are unique
  clip/frame pairs. **B10 moved bar:** clear; the 4-of-5 rule was declared
  before review and no existing threshold or coordinate contract changed.
