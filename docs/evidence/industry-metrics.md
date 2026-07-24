# The industry's player-metric landscape -- mapped, approximated where honest, and a do-not-fake list for the rest

> A credible analytics shop knows which metrics its data can actually support and which it
> cannot -- and says so out loud. This page does that: we mapped the public NBA player-metric
> landscape against our raw input coverage, built transparent approximations of the three
> families our box-score data genuinely supports, and published a do-not-fake list for the
> rest, with the RAPM family (RAPM/EPM/DARKO/LEBRON/RAPTOR) declared explicitly out of reach.
> Every number below is quoted verbatim from committed JSON. The single truth-source for any
> figure is [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md). No dollar/ROI/edge is
> claimed anywhere -- every module carries a `DESCRIPTIVE_ONLY` label.

---

## The claim

We mapped the industry's player-metric landscape, built honest approximations of the three
families our data supports, and published a do-not-fake list for the rest. Concretely:

1. **A capability matrix** grades every well-known player-metric family `supported` /
   `partial` / `not_supported` against our actual input-column coverage -- and refuses to
   claim any branded metric is reproduced.
2. **Three built approximations** -- a box-only value index, an on/off net-rating
   differential, and a per-36 rate cast -- each with frozen weights or an unchanged source
   formula, each labelled for exactly what it is *not*.
3. **An honest refusal** -- aging curves -- where the data does not exist, returned as a
   `not_buildable` verdict rather than a fabricated curve.

The discipline is the point: approximate only what the columns support, name every metric it
is *not*, and refuse the rest.

---

## 1. The capability matrix (the map)

`analytics_showcase/out/player_metric_landscape.json` grades nine metric families against our
raw coverage of 77,744 player-game rows / 807 players / 3,611 games across seasons 2023-24,
2024-25, 2025-26 (all 17 core box columns 0% missing). Its own note binds the framing:
"Support = raw input-column coverage only, never a claim that a branded metric is reproduced."

| Metric family | Verdict | Why (verbatim) |
|---|---|---|
| box_only_value_index (APPROX, not BPM/EPM) | supported | Full box present, 0% missing. Transparent linear weights only -- no RAPM target to fit against. |
| on_off_differential (unadjusted precursor to RAPM) | supported | plus_minus + min present per player-game. Labeled unadjusted/biased, not RAPM. |
| box_rate_now_cast (per-36, DARKO-lite BOX ONLY) | supported | Per-36 rate stats computable from min + counting stats. NOT a claim of DPM/DARKO. |
| playmaking_creation_profile (APPROX) | partial | ast/tov/fga present but no potential-assists/passes/touches -- volume, not quality. |
| shot_selection_descriptor (zone-baseline eFG) | partial | 2/3 makes/attempts present, but no shot-location/zone column -- no true zone baseline. |
| gravity_proxy (CV subset only) | partial | Needs broadcast-CV defender-distance tracking; box parquet only. Separate 241-game CV subset. |
| lineup_synergy (descriptive, unadjusted) | not_supported | -- |
| aging_curve | not_supported | -- |
| RAPM/xRAPM/EPM/DARKO-DPM/LEBRON/BPM/RAPTOR/qSQ/qSI/qSP/EPV/official_Gravity | not_supported | The RAPM family -- declared out of reach (no stint-level PBP + ridge solve; the trained-to-RAPM metrics inherit that). |

Chart: `docs/img/player_metric_landscape.png`.

---

## 2. Box-only value index (built approximation #1)

`analytics_showcase/out/box_value_index.json`, chart `docs/img/box_value_index.png`.
A box-only, per-36-normalized linear index in the Win-Score/Berri (2006) convention -- sum
weighted box counts, credit production, debit missed shots/turnovers/fouls. Weights are
**frozen and declared once before running** (`weights_frozen: true`,
`weights_tuned_to_output: false`): pts 1.0, reb 1.0, stl 1.0, blk 0.7, ast 0.7, fga -0.7,
fta -0.4, tov -1.0, pf -0.4. Minutes floor 750 total across the 3-season pool (501 of 807
players qualify).

**What it is NOT** (`not_this` block, verbatim): NOT RAPM/xRAPM (no stint-level PBP + ridge
solve); NOT EPM/DARKO/LEBRON (both trained to predict RAPM); NOT Basketball-Reference BPM
(no team pace/position/team-record adjustment terms); NOT defense-tracking-informed (box
counting stats only; blk/stl are the only defensive ingredients).

**Top 10 (box_value_index_per36, verbatim):**

| Rank | Player | Index | Total min | Games |
|---|---|---|---|---|
| 1 | Nikola Jokic | 30.86 | 2444.0 | 68 |
| 2 | Nikola Jokic (2nd id) | 30.068 | 4985.0 | 142 |
| 3 | Giannis Antetokounmpo | 27.558 | 5841.1 | 175 |
| 4 | Victor Wembanyama | 26.261 | 5429.9 | 179 |
| 5 | Luka Doncic | 24.884 | 4733.0 | 129 |
| 6 | Anthony Davis | 24.821 | 5032.3 | 147 |
| 7 | Joel Embiid | 24.651 | 2977.5 | 93 |
| 8 | Domantas Sabonis | 24.133 | 5926.1 | 171 |
| 9 | Shai Gilgeous-Alexander | 23.517 | 7375.7 | 218 |
| 10 | Jonas Valanciunas | 22.982 | 1466.5 | 80 |

**Face validity (verbatim):** "Top of the list is the expected 2023-26 MVP-tier cluster
(Jokic, Giannis, Wembanyama, Doncic, Davis, Embiid, SGA) -- passes face validity. Reported
as-is, not retuned."

**Known data issue caught during the run (verbatim, not fixed here):** accented names
(Jokic, Doncic, Valanciunas) are split across two distinct `player_id` values in the source
parquet -- an upstream name-encoding join issue, not a modeling choice. This fragments their
minutes/games across two rows, so Jokic appears twice in the top 10. Fixing the `player_id`
join lives in the data layer, out of scope for this index. (Player names carry diacritics
inside the JSON; they are spelled ASCII here.)

---

## 3. On/off net-rating differential (built approximation #2)

`analytics_showcase/out/on_off_showcase.json`, chart `docs/img/on_off_showcase.png`.
Reuses the committed `nba_lineup_context_net_rating_delta` claims (no play-by-play recompute).
Metric, unchanged from source: `net_rating_delta = net_rating_on_per48 - net_rating_off_per48`.

Every row (top-15 and bottom-15, both seasons) carries the verbatim **roster confound**
caveat: "who shares the floor with a player correlates with coach trust, opponent strength,
and garbage-time usage, and none of those are controlled for here. DESCRIPTIVE_ONLY, not a
predictive or edge claim." This is an unadjusted precursor to RAPM, explicitly not a causal
player-impact estimate.

| Season | n_considered | n_ranked | Top 1 | Bottom 1 | Median |
|---|---|---|---|---|---|
| 2024-25 | 653 | 353 | Nikola Jokic +23.713 | Craig Porter Jr. -19.206 | +0.195 |
| 2025-26 | 686 | 350 | Victor Wembanyama +17.043 | Tre Mann -24.09 | +0.127 |

---

## 4. Aging curve -- the honest refusal (do-not-fake)

`analytics_showcase/out/aging_curve_lite.json`. Verdict: **`not_buildable`**. No chart was
written -- the refusal is the deliverable.

Reason (verbatim `why`): "No birthdate/age column exists in any table under
data/domains/basketball_nba/ (scanned all parquets). Only 3 season snapshots of box scores
exist... 3 seasons with no age field is not honestly buildable." Both the codebase's own prior
audit (`player_metric_landscape.py`, which grades `aging_curve: not_supported`) and the
industry research independently reach the same verdict. Where the data does not exist, the
system returns a refusal instead of a fabricated curve.

---

## Reproduce

```
cd nba-ai-system

# capability matrix (the map)
python scripts/platformkit/analytics_showcase/player_metric_landscape.py

# built approximations
python scripts/platformkit/analytics_showcase/box_value_index.py
python scripts/platformkit/analytics_showcase/on_off_showcase.py

# the honest refusal (writes JSON only, no chart)
python scripts/platformkit/analytics_showcase/aging_curve_lite.py

# each module ships a self-check
python scripts/platformkit/analytics_showcase/box_value_index.py --check
python scripts/platformkit/analytics_showcase/on_off_showcase.py --check
python scripts/platformkit/analytics_showcase/aging_curve_lite.py --check
```

Outputs land in `scripts/platformkit/analytics_showcase/out/*.json` and charts in
`docs/img/*.png`.

---

## Why this matters to an employer

The hard part of sports analytics is not computing a box index -- it is knowing where your
data runs out and refusing to fake the rest. This page maps the full public metric landscape,
builds only the three families the columns actually support (each labelled for what it is
*not*), declares the RAPM family out of reach, and returns a `not_buildable` refusal for
aging curves rather than inventing a curve from three seasons with no age field. It even
surfaces a real upstream data bug (diacritic-split player ids) instead of hiding it. The
throughline: approximate only what the columns support, name every confound, and never dress a
descriptive metric as an edge.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
