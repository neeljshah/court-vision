# G57: does the tennis court solver generalise across surface and resolution?

Date: 2026-09-02. Gap: G57, filed off the G46 acceptance footnote. Premise-first,
read-only, measurement only. No solver code was edited, no threshold and no
detection parameter was moved, nothing was re-tracked into `data/tracking/`,
no git action was taken, and nothing on the pod was killed.

**VERDICT: the tennis lane is a HIGH-RESOLUTION lane, not a grass lane.**
The premise reproduced exactly, but its stated cause was wrong. Acceptance does
not collapse "off grass": it collapses off CLAY and it collapses below 720p.
Hard court is the second-best surface measured, at 125 / 400 (31.2 pct). The
decisive number is a controlled downscale: on the same 1400 frames from the
same seven clips, the production gate accepts **347 at native resolution and 22
after resizing to 640x360** (24.8 pct -> 1.6 pct). Resolution is causal, not a
property of the footage that happens to be 360p.

Honest scope, one sentence, section 7:
**the tennis lane can claim to work on grass and hard courts at 1280x720 and
above, at a 14 to 42 pct per-frame acceptance rate; it cannot claim clay, and it
cannot claim 640x360 on any surface, which is 41 pct of the corpus (G27).**

---

## 1. The premise as stated, and whether it reproduced

From `docs/evidence/tracking/g46_court_scale_premise_2026-09-02.md` section 7:
"nyYk 720p grass 46/200 accepted; 459iho5 1080p grass 83/200; tennis_06 1080p
CLAY only 10/200; 3x3 at 360p only 1/200", read as the solver collapsing off
grass.

Re-measured here on the same evenly spaced 200-frame grid, same solver, same
gate: **46/200, 83/200, 10/200, 1/200.** All four reproduce exactly. The four
numbers are real. The reading "it collapses off grass" is what this gap tests,
and it does not survive contact with the five clips G46 never measured.

## 2. What still exists, and what does not

`ssh config.pod 'ls -la /workspace/nba-ai-system/data/footage_corpus/ | grep -i tennis'`
returns **nine** tennis source videos. **`tennis_01` through `tennis_05` have no
source video on the pod and were NOT measured.** Nothing in this document says
anything about them; their acceptance is unknown and is not inferred from the
clips that survive.

Resolution is from `ffprobe` on the pod. Surface is from a rendered frame looked
at by eye at 60 s, 150 s and 240 s of each clip, never from the filename; the
identifying detail is given so the call can be checked.

## 3. Per-clip acceptance

Method, per clip: `np.linspace(0, total_frames - 1, 200)`, de-duplicated, so the
sample spans the WHOLE clip and is never a head slice. Each sampled frame is
passed to `domains/tennis/tracking/court_diagnostics.rejection_gate`, which is
`detect_court(frame)[2]` verbatim; `accepted` is the production accept. n = 200
per clip, 1800 frames total. Script as run: `g57_scripts/g57_gate.py`, run on the
pod under `nohup setsid nice -n 10` with `PYTHONPATH=/workspace/nba-ai-system`.
Raw per-frame gates: `g57_data/*.json`.

| clip | resolution | surface | what is in frame | accepted / sampled | pct | Wilson 95 pct |
|---|---|---|---|---:|---:|---|
| tennis_nyYk2nPZAwY | 640x360 | grass | Wimbledon, Djokovic v Auger-Aliassime | **0 / 200** | 0.0 | [0.0, 1.9] |
| tennis_3x3eEWCZmWQ | 640x360 | grass | Wimbledon, wide view from the stands | **1 / 200** | 0.5 | [0.1, 2.8] |
| tennis_08 | 1280x720 | grass | Wimbledon, Krejcikova v Paolini | 28 / 200 | 14.0 | [9.9, 19.5] |
| tennis_nyYk2nPZAwY_720p | 1280x720 | grass | same match and camera as nyYk 360p | 46 / 200 | 23.0 | [17.7, 29.3] |
| tennis_07 | 1280x720 | grass | Wimbledon, Sinner v Alcaraz | 55 / 200 | 27.5 | [21.8, 34.1] |
| tennis_06 | 1920x1080 | **clay** | Roland Garros, Zverev v Alcaraz | **10 / 200** | 5.0 | [2.7, 9.0] |
| tennis_10 | 1920x1080 | **hard** | WTA Cincinnati, Swiatek v Sabalenka | 47 / 200 | 23.5 | [18.2, 29.8] |
| tennis_09 | 1920x1080 | **hard** | Australian Open Melbourne, Nadal v Medvedev | 78 / 200 | 39.0 | [32.5, 45.9] |
| tennis_459iho5_AFs | 1920x1080 | grass | Wimbledon, Muchova v Noskova | 83 / 200 | 41.5 | [34.9, 48.4] |

Two results are new and matter:

- **Hard court is not a failure mode.** `tennis_09` at 39.0 pct is the second
  highest acceptance in the corpus and its interval [32.5, 45.9] overlaps the
  best grass clip's [34.9, 48.4]. The solver was never grass-only.
- **`tennis_nyYk2nPZAwY` and `tennis_nyYk2nPZAwY_720p` are the SAME match, same
  camera, same 960 s.** At 1280x720 the gate accepts 46 of 200. At 640x360 it
  accepts 0 of 200. That pair alone is a within-content resolution control, and
  it is the sharpest single number in this document.

## 4. Cross-tab

Pooled over frames, so a cell's n is 200 times its clip count.

**By resolution**

| resolution | accepted / n | pct | Wilson 95 pct | clips |
|---|---:|---:|---|---:|
| 1920x1080 | 218 / 800 | 27.2 | [24.3, 30.4] | 4 |
| 1280x720 | 129 / 600 | 21.5 | [18.4, 25.0] | 3 |
| 640x360 | **1 / 400** | **0.2** | [0.0, 1.4] | 2 |

**By surface**

| surface | accepted / n | pct | Wilson 95 pct | clips |
|---|---:|---:|---|---:|
| hard | 125 / 400 | 31.2 | [26.9, 36.0] | 2 |
| grass | 213 / 1200 | 17.8 | [15.7, 20.0] | 6 |
| clay | **10 / 200** | **5.0** | [2.7, 9.0] | 1 |

The grass row is dragged down by its own two 360p clips. Holding resolution at
720p and above, grass is **212 / 800, 26.5 pct [23.6, 29.7]**, i.e.
indistinguishable from hard and 5x clay.

**Resolution x surface**

| resolution | surface | accepted / n | pct | Wilson 95 pct | clips |
|---|---|---:|---:|---|---|
| 640x360 | grass | 1 / 400 | 0.2 | [0.0, 1.4] | nyYk360, 3x3 |
| 640x360 | clay | -- | -- | no clip in corpus | -- |
| 640x360 | hard | -- | -- | no clip in corpus | -- |
| 1280x720 | grass | 129 / 600 | 21.5 | [18.4, 25.0] | 07, 08, nyYk720 |
| 1280x720 | clay | -- | -- | no clip in corpus | -- |
| 1280x720 | hard | -- | -- | no clip in corpus | -- |
| 1920x1080 | grass | 83 / 200 | 41.5 | [34.9, 48.4] | 459iho5 |
| 1920x1080 | clay | 10 / 200 | 5.0 | [2.7, 9.0] | 06 |
| 1920x1080 | hard | 125 / 400 | 31.2 | [26.9, 36.0] | 09, 10 |

Five of nine cells are empty. Every 360p clip in the corpus is grass, and the
only clay and hard clips are 1080p, so the raw cross-tab confounds the two axes.
Section 5 breaks the confound.

## 5. The downscale control: resolution is causal

Every native-resolution clip was resampled on the SAME 200-frame grid, each
frame resized (`cv2.INTER_AREA`) to 640x360, and the same production gate re-run.
Content, surface, camera, compression source and sampling are held fixed; only
pixel count changes. Script: `g57_scripts/g57_downscale.py`. Raw records:
`g57_data/downscaled/*.json`.

| clip | surface | native res | accepted native | accepted at 640x360 |
|---|---|---|---:|---:|
| tennis_459iho5_AFs | grass | 1920x1080 | 83 / 200 | **17 / 200** |
| tennis_09 | hard | 1920x1080 | 78 / 200 | **0 / 200** |
| tennis_07 | grass | 1280x720 | 55 / 200 | **3 / 200** |
| tennis_10 | hard | 1920x1080 | 47 / 200 | **0 / 200** |
| tennis_nyYk2nPZAwY_720p | grass | 1280x720 | 46 / 200 | **2 / 200** |
| tennis_08 | grass | 1280x720 | 28 / 200 | **0 / 200** |
| tennis_06 | clay | 1920x1080 | 10 / 200 | **0 / 200** |
| **pooled** | | | **347 / 1400, 24.8 pct [22.6, 27.1]** | **22 / 1400, 1.6 pct [1.0, 2.4]** |

Acceptance falls by a factor of 16 with nothing changed but resolution, and four
of the seven clips go to exactly zero. Pooling the control with the two natively
360p clips gives **23 / 1800 at 640x360, 1.3 pct [0.9, 1.9]**.

This kills the alternative explanation that the 360p clips are simply worse
footage. They are worse footage AND 360p, but 360p alone is enough: a clip that
accepts 39 pct of its frames at 1080p accepts 0 pct of the same frames at 360p.

## 6. Rendered rejected frames: fragile, or never solvable?

`g57_scripts/g57_look.py` re-runs the production segment finder at every
`TOPHAT_CONTRASTS` value on each chosen frame, draws the best pass (horizontal
segments green, vertical blue) and annotates the gate that rejected it plus the
segment counts. Frames are evenly spaced across the REJECTED set, not a
contiguous run. Renders in `g57_renders/`, tallies in
`g57_renders/*_summary.json`.

### 6a. Worst clip: tennis_nyYk2nPZAwY, 640x360 grass, 0 / 200. 14 rendered, 14 looked at

| cause | frames | n | what the render shows |
|---|---|---:|---|
| **resolution: far-half paint not recovered** | 0, 5070, 6760, 8571, 10261, 15331, 17142 | **7** | Clean, unobstructed, full-court broadcast views. The solver finds 33-45 horizontal and 14-20 vertical segments; ALL FIVE vertical clusters are drawn, and the near baseline, near service line and net tape are drawn green. The far baseline and far service line are NOT drawn: their paint is roughly one pixel wide at this scale and the tophat does not recover it. Gate fires at `horizontal_roles`, i.e. the role triple could not be assembled. |
| genuinely not a court view | 1690, 13641, 18832, 20522, 22212 | 5 | Players at the bench in the crowd; an aerial establishing shot of the whole Wimbledon grounds; two head-and-shoulders close-ups against the green backdrop (`no_hough_lines`, 0 and 1 segments); a crowd and trophy shot. No court in frame. Unsolvable by construction. |
| partial court, far half out of frame | 3380, 11951 | 2 | A low ground-level shot over the near court, and a player close-up in front of the stands with a sliver of court at the bottom. A full-court solve is not available. |
| motion blur | -- | 0 | Not the primary cause in any of the 14. |
| wrong surface contrast | -- | 0 | This clip is grass; contrast is not the issue here. |

**Half the rejected frames on the worst clip are frames the solver should have
solved.** Seven of 14 are clean, static, full-court views in which the solver
demonstrably found the court's vertical structure and the whole near half, and
then threw it away because the far half's paint fell below the detector at 360p.
That is fragility with a specific, resolution-driven cause. The other seven are
honestly unsolvable, and no amount of solver work recovers them.

### 6b. Clay: tennis_06, 1920x1080, 10 / 200. 14 rendered, 10 looked at

| cause | frames | n | what the render shows |
|---|---|---:|---|
| **wrong surface contrast: far-half paint not recovered** | 0, 536, 1610, 4332, 5942, 7093 | **6** | Wide, clean, perfectly framed full-court views at full 1080p. Near baseline, near service line, net tape and all vertical clusters are drawn. The far baseline and far service line are NOT drawn. White paint on orange clay carries less luminance contrast than white on green grass, and the far half is the dimmer, more foreshortened half. Compounding it, the crowd and the sponsor board band above the court generate 250 to 265 spurious horizontal segments per frame against roughly five real ones. Gate fires at `horizontal_roles`. |
| genuinely not a court view | 1111, 2683, 6594, 3757, 4831 | 5 | Three cuts to a close-up or the crowd return 0 segments (`no_hough_lines`); an extreme face close-up returns 3; a pan across the stand returns 1097 segments of which 1024 are horizontal seat rows, and fails at `cross_ratio`. |
| partial court, far half out of frame | 2147, 3259, 5444 | 3 | Net-level and low-angle shots where the far court is absent. |

Clay's failure has a different mechanism from 360p's but the same signature: the
far half of the court is never detected, so the horizontal role assignment cannot
complete. On clay this happens at full 1080p on a pristine wide shot.

## 7. Honest scope

**The tennis court solver works on grass and hard courts at 1280x720 and above,
where it accepts 14 to 42 pct of evenly spaced frames per clip (347 / 1400
pooled, 24.8 pct [22.6, 27.1]); it does not work on clay (10 / 200, 5.0 pct
[2.7, 9.0], and the failures are on clean full-court 1080p views), and it does
not work at 640x360 on any surface or any content (23 / 1800, 1.3 pct
[0.9, 1.9], including a controlled downscale of frames it accepts at native
resolution).**

What this changes for the tennis lane's existing claims:

- The **"grass only" framing is wrong and should be retired.** Hard court solves
  at 31.2 pct pooled over two venues. Every tennis geometry number this program
  owns was measured on grass, but that is a sampling fact about which clips G46
  reached, not a limit of the solver. Whether the 5.28 ft classical anchor, the
  G46 length ratio and the G23 pseudo-labels replicate on hard court is now a
  cheap, answerable question, and it is NOT answered here.
- The **clay restriction is real and is a scope limit today.** One clip, one
  venue, but the failure is systematic across every full-court frame looked at,
  not noise.
- **41 pct of the corpus is 640x360 (G27) and is effectively outside the
  solver's reach**: 1.3 pct acceptance is not a coverage problem to be improved
  at the margin, it is close to no signal. Any claim whose evidence base includes
  360p clips is resting on almost nothing from them.
- The two grass clips G46's geometry rests on are **no longer the only clips that
  can carry geometry**: `tennis_09` alone accepts 78 frames, more than any single
  clip G46 used.

## 8. NOT VERIFIED

- **`tennis_01` to `tennis_05` were not measured.** Their source videos are
  absent from the pod. Their acceptance is unknown and is not inferred, in either
  direction, from the nine clips that survive.
- **Clay is one clip, one venue, one camera, one match** (Roland Garros, Zverev v
  Alcaraz). "The solver fails on clay" is consistent with every frame looked at,
  but it could be this broadcast's grade, sponsor board band or camera rather
  than the surface. A second clay venue would settle it and does not exist in the
  corpus.
- **Hard court is two clips, both blue acrylic with a light surround** (Melbourne
  and Cincinnati). Green, grey or other hard-court paints are not measured.
- **The six grass clips are not six independent courts.** G46 already flagged
  that nyYk and 459iho5 may be the same Wimbledon court; 07 and 08 are also
  Wimbledon, and nyYk 360p and nyYk 720p are the same match. The grass row may
  rest on as few as two or three distinct court and camera geometries at one
  venue.
- **Acceptance is per FRAME on a uniform time grid, not per RALLY or per clip.**
  A clip that accepts 5 pct of uniformly sampled frames could still solve every
  rally if the accepts cluster on live-play frames, and a broadcast spends much
  of its runtime on replays, close-ups and crowd. Whether acceptance conditional
  on a live-play frame differs from these numbers is NOT measured here, and it
  would change how these rates should be read as usability.
- **Acceptance is a gate pass, not accuracy.** Nothing here says an accepted
  frame is geometrically correct. G46 measured geometry only on accepted frames
  and only on four clips; the 10 accepted clay frames and the single accepted
  360p frame have not been checked for correctness at all.
- **Four of the 14 clay renders were not looked at** (1111, 2683, 3259, 5444).
  They are classified in section 6b from gate plus segment counts alone
  (`no_hough_lines` with 0 segments twice; `insufficient_oriented_lines` with 71
  horizontal and 0 vertical, and with 24 segments), which is consistent with a
  cut away from the court but is not an observation.
- **The downscale control resizes an already-compressed 1080p or 720p source with
  `INTER_AREA`.** A natively encoded 640x360 stream carries different compression
  artefacts. The two natively 360p clips (1 / 400) agree closely with the control
  (22 / 1400), so the conclusion is not sensitive to this, but the control is not
  a byte-exact 360p re-encode.
- **17 of 1800 sampled frames failed to decode** at the seeked index and are
  counted as non-accepts. Recomputing every rate over successfully read frames
  only moves no cell by more than 0.6 percentage points and changes no ordering.
- **No mechanism claim is tested.** Section 6 reports what the renders show. Why
  the far-half paint is lost, and whether any parameter change would recover clay
  or 360p, is NOT measured: this is a measurement lane and no threshold, contrast
  value or solver line was touched. Treating "the far half is not detected" as a
  fixable cause is a hypothesis for a build lane, not a result of this one.
- The 41 pct corpus figure for 640x360 is carried over from **G27** and was not
  re-derived here.

## 9. Reproduction

Scripts verbatim as run, in `docs/evidence/tracking/g57_scripts/`:
`g57_gate.py` (per-clip acceptance), `g57_downscale.py` (resolution control),
`g57_look.py` (rejected-frame renders). All three were run on the pod under
`nohup setsid nice -n 10` with `PYTHONPATH=/workspace/nba-ai-system`; the pod
environment, including the cv2 4.14.0 pin, was not modified, and nothing on the
pod was killed. Per-frame gate records are in `g57_data/`, renders and their
tallies in `g57_renders/`.
