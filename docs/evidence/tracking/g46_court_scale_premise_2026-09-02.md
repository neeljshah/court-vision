# G46: does the tennis court solver call the far SERVICE line the far BASELINE?

Date: 2026-09-02. Gap: G46, filed by G39 section 4 as a `NEW GAP`. Premise-first,
read-only. No solver code was edited, no threshold and no detection parameter was
moved, nothing was re-tracked into `data/tracking/`, no git action was taken.

**VERDICT: FALSIFIED.** The solver's far edge is the far BASELINE, not the far
service line, on 91 of 91 accepted frames across four clips and three cameras,
and on 20 of 20 rendered frames looked at. The measured length ratio is
**0.9878 (n = 91, sd 0.0058, p10 0.9825, p90 0.9948, min 0.9664, max 1.0101)**,
where 1.000 means correct and the suspected mislabel predicts **1.30**. The
tennis `court_feet` length axis carries no ~1.3x scale error. The 5.28 ft
classical anchor and the G23 pseudo-labels do not need rescaling on this account.

---

## 1. The premise as stated, and what would have to be true

From `docs/evidence/tracking/g39_ball_projection_diagnosis_2026-09-02.md`
section 4: "In all 12 renders the far edge of the back-projected 78x36 rectangle
sits on the **far service line**, not the far baseline." That was read off 12
renders of ONE clip (`tennis_nyYk2nPZAwY_720p`), all inside frames 5501-5902, by
one observer, and G39 itself listed it under NOT VERIFIED.

Court truth used throughout: 78 ft baseline to baseline, 36 ft doubles width,
27 ft singles width, each service line 21 ft from the net. So baseline to
service line is 18 ft, the far service line is at 60 ft from the near baseline,
and the net is at 39 ft. A service-line-for-baseline mislabel maps the physical
60 ft line to the solver's 78 ft, compressing 78 claimed feet onto 60 true feet:
a length ratio of 78/60 = **1.30**.

## 2. Method

Four clips on the pod, every frame sampled on an EVENLY SPACED grid of 200
indices across the whole clip (`np.linspace(0, total-1, 200)`), never a head or
tail slice. Every accepted frame was analysed; where more than 40 were accepted
the reported set was thinned by a second `np.linspace` over the accepted set, so
the table still spans the clip.

Each frame ran the production path unchanged: `court_line_segments` at each of
`TOPHAT_CONTRASTS`, then `select_court_lines`, then `solve_corners`, first
accept wins. That is exactly what `detect_court` does; the probe only keeps the
intermediate `CourtLines` object that `detect_court` throws away.

Three independent quantities were then measured against the solver's own
homography (image -> 78x36 ft, `findHomography(corners, COURT_FEET)`):

1. **Far end of the painted centre service line.** The centre service line is
   painted from the net (18 ft) to the far service line (60 ft) and no further.
   Its topmost painted pixel is therefore the far service line, at a true 60 ft.
   Correct labelling reads ~60 solver-feet; the mislabel reads ~78, because
   under the mislabel that line IS the solver's far edge. Hough gaps can only
   SHORTEN a detected extent, so this test can only be pulled down toward 60:
   it is conservative against CONFIRMING the premise.
2. **Far end of the painted doubles sidelines.** Painted 0..78 ft. Correct
   labelling reads ~78; the mislabel reads up to ~116 (see the arithmetic below).
3. **Painted width of every detected horizontal court line.** This is the
   decisive one, and it is untouched by any length mislabel: the width axis is
   pinned by the two near doubles corners, and a baseline is 36 ft wide while a
   service line is 27 ft wide. Whatever line the solver calls "far" must measure
   36 ft wide if it is a baseline and 27 ft wide if it is a service line.

Quantity 1 also gives the headline ratio. The length axis of a ground-plane
homography is a 1D projective map, so it is fixed by three correspondences. Two
of them are solver anchors (near baseline 0 -> 0, near service line 18 -> 18);
the third is the measured `s_c` for the true-60 ft line. Solving
`s = a t / (c t + 1)` for that triple and inverting for the true `T` with
`s(T) = 78` gives the true court length the solver's rectangle actually covers.
**ratio = 78 / T.** Correct labelling -> 1.00; the mislabel (`s_c = 78`) ->
`T = 60`, ratio 1.30, and quantity 2 then reads 116.4.

Scripts, verbatim as run: `docs/evidence/tracking/g46_scripts/g46_probe.py`
(measurement) and `g46_look.py` (render). Both were run on the pod under
`nohup setsid nice -n 10` with `PYTHONPATH=/workspace/nba-ai-system`.

## 3. The decisive number: painted width

Pooled over all 91 accepted frames, every horizontal line the solver detects,
binned by the length it projects to and reported by the width its paint spans:

| projected length bin (ft) | occurrences (91 frames) | median painted width (ft) | median span (ft) | what it is |
|---:|---:|---:|---|---|
| 0 | 92 | **36.1** | -0.1 .. 36.1 | near BASELINE (36 ft = doubles) |
| 18 | 91 | **26.9** | 4.5 .. 31.4 | near SERVICE line (27 ft = singles) |
| 54 | 79 | 37.8 | -0.9 .. 36.9 | the net's top tape, an off-plane object (see NOT VERIFIED) |
| 60 | 89 | **26.8** | 4.5 .. 31.4 | far SERVICE line (27 ft = singles) |
| 78 | 91 | **36.2** | -0.2 .. 36.1 | far BASELINE (36 ft = doubles) |

The line the solver calls the far baseline measures 36.2 ft wide and runs from
-0.2 to 36.1 ft, i.e. sideline to sideline including both doubles alleys. The
far service line is separately present at 60.0 ft, 26.8 ft wide, running 4.5 to
31.4 ft, i.e. between the singles sidelines only. Both appear in ~90 of 91
frames. Under the premise, the 78 ft line would measure 27 ft wide and there
would be nothing at 60. That is not what is there.

Nothing projects near 116 ft in any frame of any clip.

## 4. Ratio, and the two paint-extent probes

| clip | camera | accepted / sampled | centre-svc paint top (ft, true 60) | L sideline paint top (ft, true 78) | ratio median |
|---|---|---:|---:|---:|---:|
| tennis_nyYk2nPZAwY_720p | Wimbledon grass, 1280x720 | 46 / 200 | 59.44 | 78.34 | 0.9864 |
| tennis_459iho5_AFs | Wimbledon grass, 1920x1080 | 83 / 200 | 59.57 | 78.39 | 0.9897 |
| tennis_06 | Roland Garros clay, 1920x1080 | 10 / 200 | 59.50 | 77.61 | 0.9879 |
| tennis_3x3eEWCZmWQ | 640x360 | 1 / 200 | 59.61 | 78.79 | 0.9906 |

**Pooled: ratio n = 91, median 0.9878, mean 0.9884, sd 0.0058, p10 0.9825,
p90 0.9948, min 0.9664, max 1.0101.** Predicted under the premise: 1.30.
Predicted under correct labelling: 1.00. Measured: 0.988, i.e. the solver's
78 ft rectangle covers about 78.9 true feet, a 1.2 percent overshoot, which is
the size of the paint-edge and line-fit noise and is 25x smaller than and in
the opposite direction from the suspected error.

Centre-service paint top, pooled: n = 91, median 59.49, mean 59.52, sd 0.24,
min 58.64, max 60.43, against a truth of 60.0. Under the premise this number
would read 78.

Per-frame table: section 8.

## 5. Renders: 20 rendered, 20 looked at

`docs/evidence/tracking/g46_renders/`. Each render draws the solver's claimed
78x36 rectangle in green, back-projected reference lines at 39 and 60
solver-feet, every detected horizontal labelled with the length it projects to,
and a red circle on the topmost painted pixel of the centre service line. All
overlay lines are broken in the middle so the paint underneath stays readable.
Frames are the evenly spaced accepted frames of section 8, not a contiguous run;
the nyYk set deliberately includes 5553 and 5794, which fall inside G39's
5501-5902 window.

| render | clip | solver 78 ft green edge lands on | 60 ft magenta lands on | 39 ft cyan lands on |
|---|---|---|---|---|
| nyYk_look000000 | nyYk grass | far baseline | far service line | net base |
| nyYk_look005553 | nyYk grass | far baseline | far service line | net base |
| nyYk_look005794 | nyYk grass | far baseline | far service line | net base |
| nyYk_look009899 | nyYk grass | far baseline | far service line | net base |
| nyYk_look011830 | nyYk grass | far baseline | far service line | net base |
| nyYk_look018832 | nyYk grass | far baseline | far service line | net base |
| nyYk_look020522 | nyYk grass | far baseline | far service line | net base |
| nyYk_look024144 | nyYk grass | far baseline | far service line | net base |
| nyYk_look029938 | nyYk grass | far baseline | far service line | net base |
| nyYk_look033801 | nyYk grass | far baseline | far service line | net base |
| nyYk_look037906 | nyYk grass | far baseline | far service line | net base |
| nyYk_look043942 | nyYk grass | far baseline | far service line | net base |
| 459_look000076 | 459 grass | far baseline | far service line | net base |
| 459_look001711 | 459 grass | far baseline | far service line | net base |
| 459_look003650 | 459 grass | far baseline | far service line | net base |
| 459_look005057 | 459 grass | far baseline | far service line | net base |
| 459_look006882 | 459 grass | far baseline | far service line | net base |
| t06_look000498 | t06 clay | far baseline | far service line | net base |
| t06_look004102 | t06 clay | far baseline | far service line | net base |
| t06_look006249 | t06 clay | far baseline | far service line | net base |

**Tally: 20 of 20 have the green far edge on the painted far baseline.
0 of 20 have it on the far service line.** In every one the doubles alleys are
visible terminating at that green edge, the far player stands beyond it, and the
far service line is separately and visibly picked out 18 ft nearer by the magenta
line. On the clay clip the same holds on a different court, camera and surface.

## 6. Why the original read was plausible anyway

Two features sit within about ten image rows of each other in this camera family
and are easy to confuse in a render that draws thick opaque overlays: the far
service line (ground, 60 ft) and the net's top tape, which is an off-plane object
about 3 ft above the court at 39 ft and whose camera ray meets the ground plane
at roughly 54 solver-feet. Both are detected in almost every frame (the 54 and 60
rows in section 3). A render that shows the 78 ft edge plus this pair, and does
not show the paint underneath, invites the reading "the rectangle stops at a
service line".

The solver also has a structural defence against the mislabel, which the
measurement is consistent with but did not itself test: `select_court_lines`
windows the `far` role to `(top - 0.1*span, top + 0.1*span)` where `top` is the
topmost pixel of the five vertical clusters, and the doubles sidelines end at the
baselines. A far service line sits roughly 0.35 span below that `top` and is not a
candidate at all.

## 7. NOT VERIFIED

- **This does not clear anything else G39 found.** The ball detector picking the
  far player's head, the unbounded ground-plane projection of off-plane objects,
  and `ball_valid_pct` measuring presence rather than validity are all untouched
  here and all still stand. In particular the 54-ft net-tape row in section 3 is
  a live instance of the off-plane projection defect: a real object at 39 ft
  reads as 54 ft because it is 3 ft above the plane. That is a different gap.
- The four clips G39 measured its magnitudes on (`tennis_02` to `tennis_05`)
  could not be re-examined; their source videos are still absent from the pod.
  Whether the solver ever mislabelled on THOSE cameras is not measured and cannot
  be from here. The falsification covers the four clips named in section 4 only.
- `tennis_3x3eEWCZmWQ` (640x360) contributes n = 1: the solver accepted 1 frame
  of 200. `tennis_06` contributes n = 10 of 200. Acceptance rate is a separate
  coverage problem and is NOT addressed here; the ratio for those two clips rests
  on very few frames and only the two grass clips carry n >= 40. That low
  acceptance is itself a finding worth a gap.
- The three cameras are not three independent court geometries: nyYk and
  tennis_459iho5_AFs are both Wimbledon grass from a similar behind-baseline
  position and may be the same court. Only tennis_06 (clay) is clearly a
  different venue.
- The 1.2 percent residual (ratio 0.988, not 1.000) is NOT explained. It is
  consistent in sign across all four clips, so it is more likely a systematic
  paint-edge or line-fit bias than noise, but no cause was established and no
  correction is proposed.
- The homography's accuracy in the WIDTH axis, its behaviour on frames the solver
  REJECTS, and any error at points far off the sampled grid were not measured.
  Only accepted frames can be measured at all.
- Nothing was verified about the G23 pseudo-labels or the 5.28 ft classical
  anchor directly. The claim in the verdict is narrower: the specific ~1.3x
  length-scale defect that would have invalidated them is not present in the
  solver on these clips.
- No fix is proposed and none is needed for this gap. No threshold, detection
  parameter or bar was changed, and nothing was deployed to the pod.

## 8. Per-frame table


### tennis_nyYk2nPZAwY_720p (1280x720) -- 40 accepted of 200 evenly spaced samples
| frame | centre-svc paint top (ft, true 60) | L doubles sideline paint top (ft, true 78) | solver far role (ft) | length ratio |
|---:|---:|---:|---:|---:|
| 0 | 59.68 | 78.29 | 77.63 | 0.9923 |
| 5553 | 59.78 | 78.31 | 77.91 | 0.9948 |
| 5794 | 60.43 | 78.31 | 79.14 | 1.0101 |
| 7001 | 59.23 | 78.36 | 77.12 | 0.9813 |
| 7243 | 59.54 | 78.34 | 78.04 | 0.9890 |
| 7484 | 59.57 | 78.31 | 78.02 | 0.9897 |
| 7726 | 59.61 | 78.35 | 78.13 | 0.9907 |
| 8691 | 59.47 | 78.34 | 78.28 | 0.9872 |
| 8933 | 59.25 | 78.34 | 77.86 | 0.9818 |
| 9899 | 59.15 | 78.31 | 76.99 | 0.9793 |
| 10140 | 59.11 | 78.34 | 77.62 | 0.9782 |
| 10382 | 59.33 | 78.28 | 76.67 | 0.9839 |
| 11830 | 59.18 | 78.30 | 77.00 | 0.9800 |
| 15452 | 59.92 | 78.92 | 78.55 | 0.9981 |
| 18108 | 59.47 | 78.36 | 78.01 | 0.9873 |
| 18832 | 59.46 | 78.36 | 77.99 | 0.9870 |
| 19073 | 59.37 | 78.36 | 77.70 | 0.9849 |
| 20281 | 59.39 | 78.36 | 78.13 | 0.9854 |
| 20522 | 59.41 | 77.97 | 77.42 | 0.9857 |
| 20764 | 59.34 | 77.97 | 78.05 | 0.9840 |
| 24144 | 59.44 | 78.39 | 77.59 | 0.9866 |
| 29697 | 59.41 | 78.39 | 77.80 | 0.9858 |
| 29938 | 59.41 | 78.36 | 77.61 | 0.9857 |
| 30180 | 58.64 | 78.37 | 78.48 | 0.9664 |
| 30421 | 59.42 | 78.36 | 77.96 | 0.9861 |
| 30663 | 59.57 | 78.33 | 78.39 | 0.9896 |
| 31870 | 59.59 | 78.33 | 78.36 | 0.9902 |
| 33319 | 59.60 | 78.39 | 77.92 | 0.9905 |
| 33560 | 59.35 | 78.36 | 77.75 | 0.9842 |
| 33801 | 59.47 | 78.36 | 78.22 | 0.9873 |
| 34284 | 59.50 | 78.36 | 78.18 | 0.9878 |
| 36457 | 59.47 | 78.45 | 78.13 | 0.9873 |
| 37906 | 59.34 | 78.34 | 78.11 | 0.9840 |
| 38389 | 59.43 | 78.34 | 78.33 | 0.9862 |
| 38872 | 59.70 | 78.31 | 78.34 | 0.9929 |
| 39355 | 59.32 | 78.25 | 78.04 | 0.9836 |
| 42010 | 59.28 | 78.34 | 78.00 | 0.9825 |
| 43218 | 59.45 | 78.09 | 78.03 | 0.9867 |
| 43459 | 59.39 | 78.34 | 78.24 | 0.9854 |
| 43942 | 59.69 | 78.09 | 78.42 | 0.9926 |

### tennis_459iho5_AFs (1920x1080) -- 40 accepted of 200 evenly spaced samples
| frame | centre-svc paint top (ft, true 60) | L doubles sideline paint top (ft, true 78) | solver far role (ft) | length ratio |
|---:|---:|---:|---:|---:|
| 76 | 59.49 | 78.41 | 77.82 | 0.9877 |
| 152 | 59.37 | 78.35 | 77.62 | 0.9848 |
| 228 | 59.40 | 78.36 | 77.64 | 0.9855 |
| 304 | 59.36 | 78.29 | 77.52 | 0.9846 |
| 380 | 59.53 | 78.38 | 77.93 | 0.9886 |
| 570 | 59.83 | 78.39 | 77.85 | 0.9960 |
| 684 | 59.69 | 78.53 | 77.99 | 0.9925 |
| 1444 | 59.55 | 78.63 | 77.84 | 0.9892 |
| 1521 | 59.37 | 78.35 | 77.65 | 0.9847 |
| 1597 | 59.41 | 78.40 | 77.97 | 0.9859 |
| 1711 | 59.86 | 78.64 | 77.92 | 0.9966 |
| 1787 | 59.65 | 78.44 | 78.11 | 0.9915 |
| 1863 | 59.26 | 78.34 | 77.46 | 0.9820 |
| 1939 | 59.38 | 78.61 | 77.74 | 0.9849 |
| 2015 | 59.46 | 78.54 | 77.64 | 0.9869 |
| 2509 | 59.50 | 78.30 | 77.84 | 0.9881 |
| 2585 | 59.69 | 78.40 | 77.98 | 0.9926 |
| 2661 | 59.59 | 78.38 | 78.00 | 0.9902 |
| 3118 | 59.60 | 78.54 | 77.56 | 0.9904 |
| 3194 | 59.74 | 78.36 | 78.02 | 0.9937 |
| 3650 | 59.45 | 78.39 | 77.66 | 0.9867 |
| 3726 | 59.98 | 78.34 | 78.11 | 0.9996 |
| 3802 | 59.39 | 78.31 | 77.60 | 0.9852 |
| 3878 | 59.51 | 78.37 | 77.94 | 0.9881 |
| 3954 | 59.72 | 78.39 | 77.82 | 0.9932 |
| 4258 | 59.38 | 78.37 | 77.49 | 0.9849 |
| 4334 | 59.64 | 78.65 | 78.18 | 0.9912 |
| 4410 | 59.52 | 78.40 | 77.96 | 0.9884 |
| 4486 | 59.51 | 78.32 | 77.89 | 0.9883 |
| 4563 | 60.21 | 78.55 | 78.53 | 1.0049 |
| 5057 | 59.75 | 78.40 | 77.79 | 0.9939 |
| 5665 | 59.82 | 78.63 | 78.01 | 0.9957 |
| 5741 | 59.78 | 78.60 | 77.99 | 0.9948 |
| 5817 | 59.86 | 78.61 | 78.11 | 0.9967 |
| 5893 | 59.91 | 78.66 | 78.19 | 0.9979 |
| 5969 | 59.65 | 78.31 | 77.61 | 0.9915 |
| 6464 | 59.49 | 78.36 | 77.70 | 0.9878 |
| 6540 | 59.29 | 78.38 | 77.73 | 0.9829 |
| 6768 | 59.67 | 78.35 | 77.93 | 0.9920 |
| 6882 | 59.69 | 78.33 | 78.07 | 0.9926 |

### tennis_06 (1920x1080, clay) -- 10 accepted of 200 evenly spaced samples
| frame | centre-svc paint top (ft, true 60) | L doubles sideline paint top (ft, true 78) | solver far role (ft) | length ratio |
|---:|---:|---:|---:|---:|
| 498 | 59.62 | 78.00 | 77.61 | 0.9908 |
| 575 | 59.40 | 67.32 | 77.76 | 0.9855 |
| 2607 | 59.47 | 78.00 | 77.49 | 0.9872 |
| 2837 | 59.25 | 77.74 | 77.39 | 0.9817 |
| 4102 | 59.38 | 65.78 | 77.44 | 0.9851 |
| 5061 | 59.67 | 78.00 | 77.97 | 0.9922 |
| 5099 | 59.52 | 59.64 | 77.66 | 0.9885 |
| 6134 | 59.16 | 56.27 | 77.33 | 0.9796 |
| 6211 | 59.54 | 77.48 | 77.54 | 0.9889 |
| 6249 | 59.55 | 78.00 | 77.60 | 0.9891 |

### tennis_3x3eEWCZmWQ (640x360) -- 1 accepted of 200 evenly spaced samples
| frame | centre-svc paint top (ft, true 60) | L doubles sideline paint top (ft, true 78) | solver far role (ft) | length ratio |
|---:|---:|---:|---:|---:|
| 9053 | 59.61 | 78.79 | 78.61 | 0.9906 |

POOLED n=91 ratio median 0.9878 mean 0.9884 sd 0.0058 p10 0.9825 p90 0.9948 min 0.9664 max 1.0101
POOLED centre-svc paint top n=91 median 59.49 mean 59.52 sd 0.24 min 58.64 max 60.43

## painted-width table (pooled)
| projected length bin (ft) | n frames | median painted width (ft) | median span (ft) |
|---:|---:|---:|---|
| 0 | 92 | 36.1 | -0.1 .. 36.1 |
| 18 | 91 | 26.9 | 4.5 .. 31.4 |
| 54 | 79 | 37.8 | -0.9 .. 36.9 |
| 60 | 89 | 26.8 | 4.5 .. 31.4 |
| 78 | 91 | 36.2 | -0.2 .. 36.1 |
