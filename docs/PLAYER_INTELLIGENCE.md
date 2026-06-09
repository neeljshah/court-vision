# Player & Team Intelligence Layer

The intelligence system synthesizes **1,249 per-player dossiers** and **30 per-team scheme cards** from three raw inputs: NBA Stats API gamelogs + play-by-play microstructure, CV behavioral features extracted from broadcast video (defender distance, spacing, fatigue, shot quality), and possession-type / shot-clock tracking. Every dossier is deterministic and regenerable from raw data.

> **Scope:** Descriptive intelligence + CV-ready substrate for the prediction stack. The player head improves early-to-mid-game projections (validated offline, shadow-tested, not yet live). Team-score / win-probability simulation holds up across the full game. Honest in-game validation results are in [.planning/ingame/](../.planning/ingame/).

---

## What a player dossier contains

Each player note captures up to 28 statistical categories:

| Section | What it measures |
|---------|-----------------|
| **Scheme & Role** | Usage rate, AST%, PIE, on/off net diff, PnR handler / roll-man / ISO / post-up frequency |
| **Scoring** | Shot zone distribution (paint / 3PT / mid / FT), unassisted rate, drives/game, catch-and-shoot eFG, transition vs. halfcourt split |
| **Playmaking** | Passes made, potential assists, AST pts created, AST:TOV ratio, PnR possession fraction |
| **Rebounding** | Total / OREB / DREB rates, OREB:DREB ratio, box-outs |
| **Defense** | FG% allowed at matchup, blocks, early foul trouble rate, foul-out risk, FT generation |
| **Situational** | Clutch scoring (pts/36 in clutch situations), quarter shape (Q4 vs. early ratio), plus-minus |
| **Strengths / Weaknesses** | Auto-derived from percentile ranks across all sections |
| **CV behavioral** | Folded in from `data/intelligence/` — defender distance profiles, fatigue trajectory, shot quality index (where CV games are available) |

Data completeness score: median 0.82 across all 1,249 players (24/28 sections populated). Players with fewer than 3 real CV games have weaker CV sections; the NBA Stats sections are complete for all active rosters.

---

## Three dossier examples

### Nikola Jokić — Playmaking Big (DEN, DROP COVERAGE scheme)

The dossier encodes what makes Jokić structurally different from other bigs:

```
Archetype:  Playmaking Big
Usage rate: 27.8%  (96th percentile)
AST %:      39.9%  (99.6th percentile — highest in the system)
PIE mean:   21.0%  (97.6th percentile)
On/off net diff: +20.5

Scheme usage:
  Post-up freq: 22.5%  (96.7th pct)     Post-up PPP: 1.13  (elite)
  PnR handler:   8.5%                    PnR roll:   11.4%
  ISO freq:      6.7%

Scoring:
  Paint share: 56.8%  |  3PT share: 20.0%  |  FT share: 17.4%
  Unassisted 2PM: 34.7%  (post-up creator, not isolation ball-handler)
  Drives/game: 4.9    AST pts created/game: 28.2  (100th pct)

Playmaking:
  Passes made/game: 73   Potential AST: 17.6   AST:TOV: 3.71 (99.7th pct)
```

**How this plugs into the prediction stack:** When the model prices Jokić's AST line, it reads his AST% percentile rank (99.6), his PnR handler fraction, and the DEN team scheme card (DROP COVERAGE — opponents drop the big, reducing pick-and-roll options that would otherwise inflate assist opportunities). The matchup deviation artifact then adjusts for tonight's opponent specifically.

---

### Shai Gilgeous-Alexander — Primary Initiator / Lead Guard (OKC, DROP COVERAGE scheme)

```
Archetype:  Primary Initiator / Lead Guard
Usage rate: 32.5%  (99.6th percentile — league-high tier)
AST %:      28.0%  (95.3rd percentile)
PIE mean:   18.9%  (94.4th percentile)
On/off net diff: +12.1

Scheme usage:
  PnR handler: 36.0%   ISO freq: 28.0%   Post-up: 4.3%
  Post-up PPP: 1.16    Creator role: primary_creator

Scoring:
  Paint share: 42.1%  |  3PT share: 19.7%  |  FT share: 24.2%
  Unassisted 2PM: 78.8%   Unassisted 3PM: 65.0%   (pure self-creator)
  Drives/game: 20.6   Self-creation rank: 98.6th pct
  FTA/game: 9.23  (elite FT-generation, highest-leverage line for models)

Playmaking:
  AST:TOV: 2.84 (97.6th pct)   AST pts created: 17.5/game (97.5th pct)
```

**Key prediction signal:** FT share is 24.2% of all points — the highest in this archetype. When modeling his PTS line, FTA/game variance is the dominant source of game-to-game spread, not field goal volatility. The dossier encodes this explicitly so the model can weight accordingly.

---

### Sam Hauser — 3&D Wing (BOS, DROP COVERAGE scheme)

```
Archetype:  3&D Wing  (secondary: Floor Spacer)
Usage rate: 13.9%  (26th percentile — off-ball role)
Creator role: spot_up
On/off net diff: +1.7

Scheme usage:
  PnR handler: 4.9%   PnR roll: 7.8%   (almost never primary creator)

Scoring:
  3PT share: 82.3%   Paint share: 10.2%   FT share: 1.8%
  Unassisted 3PM: 4.8%   (catch-and-shoot, not pull-up)
  Drives/game: 0.9   Catch-shoot eFG: 60.6%  (81.6th pct)

Rebounding: Total reb rate: 7.4%  (46.8th pct — limited role)
```

**Prediction signal:** Hauser's 3PT share (82.3%) is the structural key. His line is almost entirely 3PT volume × efficiency, with near-zero variance from paint scoring or FTs. The model reads catch_and_shoot archetype + BOS tempo tag (DROP COVERAGE = space for shooters off movement) and sizes the 3PT-dependent models accordingly.

---

## Team scheme card example — Denver Nuggets (DEN)

```
Dominant scheme: DROP COVERAGE
All tags: DROP COVERAGE | HELP DEFENSE
Confidence: med

Defensive intensity z-scores (5-game window):
  Contested Shot Rate:        -0.184  (season avg: +0.521)
  Avg Defender Distance:      +0.482  (give perimeter space)
  Paint Attempts Allowed %:   -0.559  (deny paint)
  Pace Imposed:               +0.718  (force slower pace)
  Catch-and-Shoot Allowed %:  -0.264
  Composite Intensity:        +0.070  |  League rank: 18/30

Offensive profile:
  Tempo z: +0.707  (above average pace)
  Spacing z: -0.656  (tight spacing — heavy post usage)
  Composite: +0.026  → "average tempo, balanced"

Comparable teams by defensive intensity: IND, PHX, GSW
Comparable teams by tempo/spacing: CLE, MIN, ATL

Matchup notes: Big stays paint-side; opponents see clean mid-range
and high paint dwell share (z=+0.73 vs league avg).
```

**How the scheme card feeds predictions:** When a player faces DEN, the model reads: DROP COVERAGE → guards get perimeter space → boost catch-and-shoot probability for movement shooters; low contested-shot rate → eFG uplift for open-look archetypes; high paint dwell allowed → paint scorers see below-average resistance. This is the `defensive_schemes.parquet` + `archetype_scheme_interactions.parquet` combination.

---

## Scale and coverage

| Item | Count |
|------|-------|
| Player dossiers (all archetypes, full NBA) | **1,249** |
| Team scheme cards | **30** |
| Players with ≥3 real CV games (dense tier) | **124** |
| Statistical categories per dossier | up to 28 |
| Intelligence artifacts feeding models | **80** (see [INTELLIGENCE.md](INTELLIGENCE.md)) |
| Archetype labels | 12 (Playmaking Big, Primary Initiator, 3&D Wing, Movement Shooter, High-Usage Scorer, Dominant Two-Way Big, Rebounding Big, Floor Spacer, Stretch Big, Playmaking Guard, Role Player, Specialist) |
| Defensive scheme tags | 6 (Drop Coverage, Switch Heavy, Help Defense, Paint-First Defense, Pace Control, Balanced) |

---

## Honest scope

**What this is:** A descriptive intelligence substrate — structured profiles that encode player-level behavioral patterns deterministically from public data. It feeds the prop models and in-play projection heads as feature inputs, not as standalone predictions.

**What's validated:** The pregame prop stack reads these profiles as feature inputs and delivers competitive **leak-free prop accuracy** (WF MAE PTS ~4.58 / REB ~1.90 / AST ~1.34 / FG3M ~0.88). Vs real closing lines the market is efficient (break-even-minus-vig; AST ~+4–5% the one durable edge). We **cannot** attribution-test individual intelligence artifacts cleanly at this scale, and CV-derived features currently carry SHAP ≈ 0 in the production models — the layer is a credible, fully-plumbed substrate, **not yet a measured edge**. *(An earlier "+18.38% ROI" attribution here was a market-follow grading artifact, retracted — see [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).)*

**In-game player head:** The per-player behavioral signal (quarter shape, clutch split, fatigue trajectory) improves projections **early-to-mid-game** (endQ1 / endQ2). It degrades late: single-game shadows at endQ3 do not lift whole-game prediction reliably. Team-score / win-probability simulation holds up game-wide. This is validated offline on 550-game retroactive data; the live shadow daemon (`/api/shadow`) is running but no real money has been staked against live in-game lines yet (live CLV collection starts Oct 2026).

**What's not here yet:** Officials per-player sensitivity (0 rows — significance gate not passed), absence-effect beneficiaries (5 rows — confounded by simultaneous injuries), compound signal candidates (10 rows — broadening queued). Row counts per artifact are documented in [INTELLIGENCE.md](INTELLIGENCE.md) so gaps are legible at a glance.

---

## Regenerating

```bash
# Full player dossier rebuild
python scripts/build_player_cv_profiles.py

# Full team scheme card rebuild  
python scripts/build_officials_per_team_date.py  # includes scheme builder

# Intelligence layer (80 artifacts)
python scripts/intelligence/build_all.py  # ~25 min on dev box
```

Data inputs required: `data/tracking/*` (CV tracking), `data/nba/*` (gamelogs), `data/cache/profiles/PLAYER_REPORTS.json`, `data/cache/profiles/TEAM_REPORTS.json`.

The per-player vault notes (1,249 `.md` files) are gitignored — regenerable from `PLAYER_REPORTS.json`. See [vault/Intelligence/Players_Index.md](../vault/Intelligence/Players_Index.md) for the full browsable index (grouped by team and by archetype) in the local Obsidian vault.
