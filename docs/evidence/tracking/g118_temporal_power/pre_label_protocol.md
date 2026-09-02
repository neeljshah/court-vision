# G118 pre-label protocol: new temporal strips

## Blind boundary

This protocol was written before any new G118 blind call.  Candidate enumeration
read only `clip` and `source_frame` from:

- `g65_ball_labels/labels.csv` (150 identities),
- `g85_consistency/blind_labels.csv` (60 identities), and
- `g102_temporal_labels/sample_manifest.csv` (40 identities).

No prior `ball_visible`, `blind_label`, agreement, or G65 label value was read.

## Canonical identity and coverage census

The canonical clip names are `tennis_09`, `tennis_10`, and `nyyk_720p`.
Normalization lowercases, removes a terminal video extension, changes path
separators to `__`, and applies these explicit source aliases:

| Raw family | Canonical clip |
| --- | --- |
| `tennis__tennis_09` / `tennis_09` | `tennis_09` |
| `tennis__tennis_10` / `tennis_10` | `tennis_10` |
| `tennis__tennis_nyYk2nPZAwY_720p` / `nyyk_720p` | `nyyk_720p` |

The G65/G85 identity intersection is 60 unique source frames: 20 each for
`tennis_09`, `tennis_10`, and `nyyk_720p`.  Local source MP4s exist for
`tennis_09` and `nyyk_720p`, so the source-available overlap is 40.  The local
`tennis_10` source is absent; its 20 overlap identities are a named,
pre-render availability exclusion.

G102 already blind-labelled 29 of the 40 source-available identities.  They
are retained for future pooling and are excluded here by normalized identity
only.  This pass therefore labels every remaining source-available identity:
11 rows (eight `tennis_09`, three `nyyk_720p`), enumerated in
`candidate_manifest.csv`.

## Pre-label precision statement

At an assumed agreement proportion of 0.75, the Wilson 95% interval for the
planned 40-row source-available pool is [0.598060, 0.858129] (half-width
0.130034).  The 11 newly-labelled rows alone would have a Wilson 95% interval
of [0.455687, 0.914897] (half-width 0.229605) at the same assumed proportion.
Thus this bounded extension improves the pooled precision but cannot by itself
provide a narrow separation test.

## Rendering and blind-label procedure

For each of the 11 rows, render predecessor/current/successor source frames
from only its local MP4, construct spatially aligned 2x tiles, and assemble a
review card from those clean strips.  One labeller will call `ball_visible` or
`uncertain` from the strips and review card only.  The resulting blind label
CSV, render manifest, strips, and cards will be committed before any prior
row-level G85/G102/G65 label value or comparison is opened.

This artifact deliberately contains no join, agreement computation, pooled
metric, or final G118 memo.
