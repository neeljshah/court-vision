# Baseball footage acquisition -- lane T5b: METRIC_LOCAL reached, corpus was the blocker

Date: 2026-09-01. Lane: T5b-BASEBALL-FOOTAGE.
Verdict: **the T5 corpus diagnosis is CONFIRMED and now fixed.** Four real MLB
broadcast sections were acquired, verified by eye, staged on the pod, and
tracked. The baseball teacher rung moved
`IMAGE_PX_DECLARED` -> **`METRIC_LOCAL`** on the pod and locally. No harness
threshold, no `SPORT_COORDINATE_SPACES` entry, and no segmenter constant was
changed; all four games still fail intake on `coordinate_contract`, which is
correct and expected.

## 1. Sources and sections

All downloaded locally (the pod IP is YouTube-bot-blocked) with
`footage_bridge.download_local`, 10-minute sections, cookies + HLS rungs.

| game_id | source | channel | section | height | bytes |
|---|---|---|---|---|---|
| `mlb_gMm3EODDb6w` | FULL GAME 2024 WS Gm1 NYY@LAD | MLB (official) | `*00:20:00-00:30:00` | 720 | 90.9 MB |
| `mlb_3Oc4S_1np98` | FULL GAME 2024 WS Gm5 LAD@NYY | MLB (official) | `*00:25:00-00:35:00` | 720 | 89.6 MB |
| `mlb_ARtRmUHC7dw` | Condensed Game 2016 WS Gm7 CHC@CLE | MLB (official) | `*00:05:00-00:15:00` | 720 | 125.6 MB |
| `mlb_2iosUkpL0Bc` | Condensed Game TB@BOS 4/8/18 | MLB (official) | `*00:02:00-00:12:00` | 720 | 148.2 MB |
| `npb_JBt4qlGQ_HI` | Full archived Fighters vs Eagles | PacificLeagueTV (official) | `*00:40:00-00:50:00` | 720 | 125.1 MB |
| `kbo_3Nh9yfvkcv4` | "KBO LIVE NC Dinos vs Hanwha Eagles" | DreadsROKTV | `*01:00:00-01:10:00` | 1080 | 96.3 MB |

Every download succeeded at 720p or better on the first ladder rung. The 360p
defect did not recur.

**One shared-code change, with a test.** `download_local` now honours an
explicit `item["section"]`. `plan_section` caps the section start at 600 s,
which on a 4-hour live stream lands inside the pregame show; the KBO and NPB
items needed a 40-60 minute offset to sample live play at all.
Test: `test_explicit_section_overrides_plan_section`
(`scripts/platformkit/test_footage_bridge.py`, 38 passed).

## 2. Verification grid (12 evenly spaced frames per clip, viewed)

Contact sheets: `docs/evidence/tracking/baseball_footage_acq_2026-09-01/<clip>_grid.jpg`.
Keep rule declared before viewing: **>= 50 pct of sampled frames must be the
centerfield pitch view or another live field view.**

| clip | field-view frames | centerfield pitch view | decision | what the frames show |
|---|---|---|---|---|
| `mlb_2iosUkpL0Bc` | 11/12 (92 pct) | 3/12 | **KEEP** | daytime Fenway; pitch views, infield, outfield plays, one graphic wipe |
| `mlb_ARtRmUHC7dw` | 10/12 (83 pct) | 0/12 | **KEEP** | Progressive Field; low first-base-side angle, no classic CF view in the sample |
| `mlb_gMm3EODDb6w` | 7/12 (58 pct) | 6/12 | **KEEP** | Dodger Stadium night; clean CF pitch views plus batter/dugout close-ups |
| `mlb_3Oc4S_1np98` | 7/12 (58 pct) | 5/12 | **KEEP** | Yankee Stadium night; same mix |
| `npb_JBt4qlGQ_HI` | 3/12 (25 pct) | 0/12 | **REJECT** | real NPB game, but the cut is close-up dominated (catcher, batter, dugout) |
| `kbo_3Nh9yfvkcv4` | 0/12 (0 pct) | 0/12 | **REJECT** | not a broadcast: a reaction co-stream -- static stadium still, lineup overlay, chat panel, webcam |

The KBO reject repeats the trap T5 found: "KBO LIVE <teams>" in a title is a
co-stream, not a game feed. Title screening is not sufficient; the
render-and-look is what catches it.

Automated census on the same 12 frames disagrees with the eye in a way that
matters: `dominant_green` returned 0 green frames on BOTH night games
(`mlb_gMm3EODDb6w`, `mlb_3Oc4S_1np98`) that a human reads as majority pitch
view. The green gate is stadium-lighting dependent, not footage dependent.

## 3. Pod status

Uploaded with `footage_bridge.push_staged` (scp to `<sport>__<game_id>.mp4.part`,
atomic rename) into `/workspace/nba-ai-system/data/footage_bridge/`, which is the
directory `track_daemon.claimable()` globs. (`data/footage_corpus/` is where the
daemon RETAINS a video after tracking, not where it picks work up.) Nothing was
killed, `track_daemon.pid` was not touched, no git operation ran on the pod.

The already-running daemon claimed all four within minutes. Ledger
(`data/tracking/track_daemon_ledger.jsonl`):

| game_id | status | rows | passed | seconds |
|---|---|---|---|---|
| `mlb_gMm3EODDb6w` | tracked | 31,181 | false | 105 |
| `mlb_3Oc4S_1np98` | tracked | 40,106 | false | 105 |
| `mlb_ARtRmUHC7dw` | tracked | 38,335 | false | 105 |
| `mlb_2iosUkpL0Bc` | tracked | 39,503 | false | 165 |

All four fail on `coordinate_contract: rows declare coordinate_space image_px`.
That is the designed rejection, not a regression.

## 4. METRIC_LOCAL result

Pod teacher metadata, 5,995 processed frames per game:

| game_id | pitch_view_frames | pitch_segments | segments carrying `scale_px_per_ft` |
|---|---|---|---|
| `mlb_2iosUkpL0Bc` | 2,424 | 176 | **176** |
| `mlb_ARtRmUHC7dw` | 417 | 84 | **84** |
| `mlb_3Oc4S_1np98` | 77 | 9 | **9** |
| `mlb_gMm3EODDb6w` | 12 | 6 | **6** |

`teacher_feature_gate.corpus_rung("baseball", ...)` now returns **`METRIC_LOCAL`**
on the pod and locally, unlocking families `("image_region", "metric_local")`.
The prior state across 87 pod games was a single `teacher_meta.json` reading
`pitch_view_frames: 0, pitch_segments: 0`.

Independent local re-run (`python -m scripts.platformkit.adapter_run baseball
data/videos/bridge/mlb_2iosUkpL0Bc.mp4 mlb_2iosUkpL0Bc --max-frames 3000`, this
box, separate filesystem from the pod): 19,576 rows, `pitch_view_frames` 1,433
of 3,000 (47.8 pct), `pitch_segments` 83, all 83 carrying a scale. Two
independent runs on two machines agree that this clip carries hundreds of
accepted pitch-view frames.

## 5. Honest limits -- what is NOT established

**The anchor is the 18 ft mound diameter, not the 60.5 ft mound-to-plate
distance.** `field_mask.MOUND_DIAMETER_FEET = 18.0`, and
`MoundChord.pixels_per_foot_lateral` is `chord_width_px / 18.0`. There is no
plate landmark in the baseball geometry module at all, so no mound-to-plate
measurement was produced or checked. Retargeting the anchor is a change to
`domains/baseball/tracking/`, outside this lane's rails.

**The scale values are not yet trustworthy.** Local segment scales span
14.9 to 66.4 px/ft (median 34.5) -- a 4.5x spread that camera zoom alone does
not explain.
`docs/evidence/tracking/baseball_footage_acq_2026-09-01/mound_detections_mlb_2iosUkpL0Bc.jpg`
overlays the detected chord on six accepted frames, ~15 s apart, and shows why:
four land on the actual pitcher's mound, and two land on unrelated wide dirt
bands (the third-base cut-out; the home-plate dirt behind the catcher). The
chord detector accepts any sufficiently wide horizontal dirt run under a green
band. So `METRIC_LOCAL` is reached in the sense the gate defines -- accepted
segments carry a scale -- but a downstream consumer must not treat the median
segment scale as a calibrated px/ft until the false-mound class is separated.
No fix is proposed here; that is a `field_mask.py` change.

**Not measured:** whether any of these games could pass the harness (they cannot
-- the coordinate contract rejects `image_px` by design); ball tracking (the
adapter has no ball detector and fails closed); pitch-view yield on the NPB and
KBO leagues, since both candidates were rejected before tracking; and whether
the night-game green-gate failure is fixable, only that it occurs.

## Reproduce

```
python -m scripts.platformkit.adapter_run baseball \
  data/videos/bridge/mlb_2iosUkpL0Bc.mp4 mlb_2iosUkpL0Bc --max-frames 3000
python -c "from scripts.platformkit.teacher_feature_gate import corpus_rung; \
  print(corpus_rung('baseball','data/tracking_reports','data/tracking'))"
```

Related: `docs/evidence/tracking/baseball_cut_detector_2026-09-01.md` (the
premise this lane acted on),
`docs/research/organization-sprint/PROPOSED_baseball_shared_2026-09-01.md`.
