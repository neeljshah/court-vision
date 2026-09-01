# Corpus mislabel quarantine + cross-sport census (2026-09-01)

Lane CORPUS-MISLABEL, verifying and closing lane T4's football finding
(`docs/evidence/tracking/football_imagepx_snap_2026-09-01.md`), then
generalizing to the cross-sport pattern lane T5 found in baseball
(`docs/evidence/tracking/baseball_cut_detector_2026-09-01.md`).

## 1. Football: 4 local + 6 pod clips confirmed non-football, all quarantined

| Clip | Location | Content | How confirmed |
|---|---|---|---|
| `football_fsrQPwTpaSQ` | local | volleyball (UC San Diego/California, ACC) | already quarantined by the auto gate before this lane |
| `football_WHjFQ5Nca20` | local | volleyball (Butler/Clemson, ACC) | already quarantined by the auto gate before this lane |
| `football_BN5zn5hu1zU` | local | volleyball (Kent St/Virginia Tech, ACC) | rendered by T4; quarantined this lane |
| `football_mqQsnKyLXlY` | local | **EA Sports College Football video-game esports** ("Rally Cry Championship Tour", Tennessee vs NC State, `eslvcf25_02` overlay) | rendered 3 frames this lane, see `docs/evidence/tracking/corpus_mislabel_2026-09-01/mqQsnKyLXlY_*.jpg` |
| `football_DrxDFaRonuE` | pod corpus | SEC baseball press conference (Kentucky) | census JUNK, rendered this lane |
| `football_VEoXn84p9o8` | pod corpus | SEC baseball press conference (Texas A&M) | census JUNK, rendered this lane |
| `football_cxbBz4nkovE` | pod corpus | SEC "AI in Sports" studio panel | census JUNK, rendered this lane |
| `football_iaDDTxNEOfE` | pod corpus | SEC baseball press conference (LSU) | census JUNK, rendered this lane |
| `football_GU6CrRLjTkw` | pod corpus | SEC baseball press conference (Ole Miss) | census SUSPECT, rendered this lane |
| `football_L3WOKdFhdkQ` | pod corpus | ACC volleyball (Kansas vs Pittsburgh) | census SUSPECT, rendered this lane |

All 10 are now in `data/footage_quarantine/` (local) or the pod's
`data/footage_quarantine/` (pod), each with a `<name>.json` sidecar carrying
`sport_verified: false` and `quarantine_reason`. No video was deleted, only
moved. `mqQsnKyLXlY`'s stray `.f298/.f299/.ytdl` partial-stream fragments and
the two already-quarantined ids' orphaned `.f136/.f137` fragments were deleted
(these are not videos -- single-stream yt-dlp merge leftovers, unplayable
alone).

## 2. Root cause -- file:line

`scripts/platformkit/queue_expander.py:62-67` lists football's YouTube
sources. Two of the four are **general conference-network channels that also
publish other sports**, confirmed by `yt-dlp --print channel`:

* `UC0hy7TcR1gGD8nQBqrF2FaA` = "ACC Digital Network" -- also listed as a
  `ncaa_basketball` source (line 80) and a `volleyball` source (line 95).
  Produced 3 of the 10 bad clips (volleyball matches).
* `UC60q_WUDde_NK-ze3frvtiA` = "SEC" -- produced 5 of the 10 bad clips
  (baseball press conferences and a studio panel).

None of the 10 titles contain the word "football", so the existing content
gate at `queue_expander.py:149-153` (`_football_metadata`, requires
`"football" in title` and a replay phrase) and `:156-174`
(`_verify_football_candidate`, samples a frame and runs the yard-line
detector) would have rejected every one of them -- **if they had gone through
`expand_queue`**. They did not: `_valid_football_item`
(`queue_expander.py:208-212`) is the only check ever re-applied to items
already sitting in the queue file, and it validates shape only (sport tag +
11-char video id), never content. These are legacy entries that predate the
metadata/frame gate (or were seeded outside `expand_queue`), and nothing
in the current code ever re-screens a queued item once it is in the file.
**Fix recommendation (not applied, out of this lane's scope): re-run
`_football_metadata` + `_verify_football_candidate` over existing queue items
in `_valid_football_item`, not just new candidates.**

The post-download gate (`footage_content_gate.py`, called from
`footage_bridge.py:570`) caught 2 of the 4 local clips
(`static_non_sport_no_playing_surface`) for the right symptom, wrong
diagnosis -- it does not test for volleyball vs football, only "no green
surface anywhere". It structurally **cannot** catch `mqQsnKyLXlY` (real green
turf, just a video game) or most of the 6 pod clips (SEC baseball press
conferences shot on a branded purple/maroon backdrop with no green at all --
those DID have near-zero surface fraction and should have been caught if they
had gone through the same download-time gate; they are pod-side legacy
tracked games from before this gate was wired into the bridge, or were
pushed via `push_and_track`/manual staging that bypassed it).

## 3. Quarantine mechanism (scripts/platformkit, not human-gated)

`scripts/platformkit/footage_content_gate.py`:
* `quarantine()` (existing) now also writes `sport_verified: false` and
  `quarantine_reason` (alias of `reason`) into the sidecar, additive only --
  the 2 pre-existing sidecars and their consuming test still read fine.
* `quarantine_manual(video, reason)` (new) -- same move+sidecar for clips
  confirmed bad by a human/agent rendering a frame, not by the color gate.
* `is_quarantined(video)` (new) -- true if the file lives under
  `QUARANTINE_DIR` OR carries an in-place `sport_verified: false` sidecar.

`scripts/platformkit/tracking_corpus_ab.py:corpus_clips()` (the harness-style
shared enumerator over `data/footage_corpus/`) now calls `is_quarantined()`
and skips flagged clips -- this is the "ONE shared enumeration point" the
task asked for. `track_daemon.py`'s `claimable()` scans `data/footage_bridge`
(the upload stage), a different directory the quarantined files were never
in, so no change was needed there; quarantining a clip already removes it
from every directory any consumer walks.

## 4. Pod status + sweep-count correction

`ssh root@213.192.2.83:40048` (read-only `ls`, confirmed before any write):
none of the 4 originally-suspect local ids (`fsrQPwTpaSQ`, `WHjFQ5Nca20`,
`BN5zn5hu1zU`, `mqQsnKyLXlY`) exist in the pod's `data/tracking/` or
`data/footage_corpus/` -- they were never uploaded, so they were **never**
counted in the 173-game harness sweep. No correction needed for them.

The generic census (section 5) found 6 **additional**, previously-unflagged
bad clips already inside the pod's `data/footage_corpus/` and already
tracked: `DrxDFaRonuE`, `VEoXn84p9o8`, `cxbBz4nkovE`, `iaDDTxNEOfE`,
`GU6CrRLjTkw`, `L3WOKdFhdkQ`. All 6 game-id directories are present in the
pod's `data/tracking/` (`football_DrxDFaRonuE` etc.) and match names in the
41 "football" games counted by
`docs/evidence/tracking/harness_sweep_173_games_2026-09-01.md`.
**Correction: 6 of the 41 football games in that sweep (14.6%) are confirmed
non-football content.** This does not change the sweep's bottom-line verdict
(0/173 passes -- these 6 already failed the harness too, for unrelated
reasons), but the honest football corpus denominator for that sweep is 35,
not 41. The sweep itself was **not rerun**, per instructions. These 6 plus 2
baseball clips (below) were quarantined on the pod as a deliberate,
interactive action once visually confirmed -- not by the read-only census
job itself.

## 5. Cross-sport footage census tool

New: `scripts/platformkit/tracking/footage_census.py` (183 LOC) + test
`scripts/platformkit/tracking/test_footage_census.py` (4 tests). Samples 24
evenly-spaced frames per clip, reuses `footage_content_gate._surface_fraction`
per-sport HSV ranges (rung 2: reuse, not a new color model) for
`surface_frac`, adds a Canny-edge-density floor (`GRAPHIC_EDGE_FLOOR=0.02`)
for `graphic_frac` (flat graphic/talking-head proxy). Verdict thresholds,
fixed before running:
`JUNK` = surface_frac exactly 0.0 (no frame ever shows the sport surface),
`SUSPECT` = 0 < surface_frac < 0.5, or graphic_frac >= 0.5,
`USABLE` = otherwise. SUSPECT clips get 3 rendered frames under
`docs/evidence/tracking/corpus_census_2026-09-01/`; JUNK clips are
quarantined via `quarantine_manual`.

**Known limitation, found by running it**: the surface-color heuristic is a
much weaker test than lane T5's baseball census (mound-chord + infield-band
structural detector, 400 frames/clip). T5 hand-confirmed `kbo_2ZtgAvs67so`
(KBO studio talk show) and `mlb_QqHhEShXAX0` (podcast screen-share of a stats
app) as non-game content -- this tool's naive HSV surface check scored them
`USABLE` (0.667 and 1.0 surface_frac: a studio set's colors plus lower-third
graphics apparently clear the green/tan mask). **This generic tool does not
supersede T5's baseball finding; it missed it.** Both ids were quarantined
manually this lane, citing T5's memo, not the census verdict.

### Local corpus (data/footage_corpus, data/videos/bridge, data/videos/reference)

After quarantining the 4 football clips: **0 JUNK, 0 SUSPECT** across
tennis(5) cricket(1) handball(2) mlb(4, one unreadable/corrupt --
`mlb_231Mmqijar8`, flagged `SUSPECT:unreadable`, unrelated to mislabeling)
ncaa_basketball(1) nhl(1) npb(1) soccer(4) volleyball(1) wnba(2) baseball(1)
football(1, the real reference clip) kbo(1). Full csv:
`docs/evidence/tracking/corpus_census_2026-09-01/census.csv`.

### Pod corpus (data/footage_corpus, read-only nohup: `ssh -p 40048 root@213.192.2.83 'cd /workspace/nba-ai-system && nohup python3 -m scripts.platformkit.tracking.footage_census --dirs data/footage_corpus --out-dir /tmp/footage_census --no-quarantine > /tmp/footage_census/run.log 2>&1 < /dev/null &'`, nothing under `data/` touched by the job itself)

| sport | usable | suspect | junk | of |
|---|---:|---:|---:|---:|
| football | 9 | 2 | 4 | 15 |
| kbo | 12 | 0 | 0 | 12 |
| mlb | 7 | 0 | 0 | 7 |
| ncaa_basketball | 6 | 0 | 0 | 6 |
| npb | 6 | 0 | 0 | 6 |
| soccer | 5 | 0 | 0 | 5 |
| tennis | 9 | 0 | 0 | 9 |
| wnba | 4 | 1 | 0 | 5 |

`wnba__wnba_05`'s SUSPECT flag (surface_frac 0.042) is a heuristic false
positive -- rendered frames show a real WNBA game on a blue-tinted court that
the tan/green mask under-detects. Left un-quarantined; noted as a tool
ceiling (blue-court sports need their own color range, not the `_TAN`
fallback -- not built here, YAGNI until it recurs).
`mlb`/`kbo`/`npb` showing 0 junk/suspect here is the false-negative described
above, not a clean bill of health -- see T5's memo for the real baseball
corpus verdict (16/24 clips zero green field).

## 6. Other sports -- suspects without full rendering

`queue_expander.SOURCES` shares `UC0hy7TcR1gGD8nQBqrF2FaA` (ACC Digital
Network) across **three** sport labels: `football`, `ncaa_basketball`
(line 80), and `volleyball` (line 95) -- the same channel that produced 3 of
the 10 bad football clips. Checked the 5 currently-queued
`ncaa_basketball` items by title (`yt-dlp --print channel,title`, no
download): all 5 are from the "March Madness" channel, not the ACC channel --
**no suspect items currently queued**, but the source-sharing itself is a
standing risk since basketball/tennis/soccer/volleyball have **no
per-item content gate at expand_queue time at all** (only football has
`_football_metadata`/`_verify_football_candidate`); their only backstop is
the generic post-download surface-color gate, which this lane's own census
run just showed has real false-negative gaps (studio content, blue courts).
Not rendered further: no title in the current tennis/soccer/mlb/kbo/npb/wnba
queues looked suspicious by name.

## Test

```
python -m pytest scripts/platformkit/tracking/test_footage_census.py scripts/platformkit/test_tracking_corpus_ab.py scripts/platformkit/test_footage_content_gate.py -q
10 passed
```

## What is NOT verified

* `_valid_football_item` was not fixed to re-screen legacy queue items (out
  of scope; recommendation only, section 2).
* The pod's `data/tracking/<id>/tracking_data.csv` and
  `data/tracking_reports/` for the 8 pod clips quarantined this lane were
  left in place -- quarantining removed the source video, not the already-
  computed (and already-failing) tracking artifacts. The 173-game sweep
  document itself was not edited or rerun.
* `wnba__wnba_05`'s false-positive SUSPECT and the general blue-court gap in
  `_ranges()` are noted, not fixed.
* T5's mound-chord/infield-band baseball census was not re-run or extended;
  this lane only manually quarantined the 2 ids it had already named.
* Other sports' queues were spot-checked by title/channel, not exhaustively
  rendered.
