# MLB ARCHETYPE PRIOR -- Leadoff / Table-Setter (ROLE, not a person)
_Part of the edge-intelligence corpus (deep/actionable layer). Describes a ROLE/PLAYSTYLE defined by
LINEUP SLOT + on-base/speed function, never an individual -- binding graph rule. Grounds in the
30,411-row player_gamelogs.parquet (data/domains/mlb/, 2026-04-01..06-17), domains/mlb/exposure_mlb.py,
domains/mlb/player_rates_mlb.py, and the MLB edge map (../00-edge-map.md). Tier: HYPOTHESIS. ASCII only.
No $-edge claims._

## Who this role is (definition by SLOT, not by name)
The LEADOFF / TABLE-SETTER is defined by lineup slot 1 (and to a degree slot 2): the most plate
appearances of any spot, a function of getting on base and scoring rather than driving in runs. This is a
SLOT/exposure archetype -- the per-PA bat underneath can be contact (most common) or power (modern
"slug-leadoff"). The edge here is primarily EXPOSURE, not rate.

## The exposure signature (the defining trait -- measured, leak-free)
Real corpus PA/game by lineup slot (the exposure the prop engine multiplies by):

| Slot | PA/game (corpus) | exposure_mlb.py:28 default | Gap |
|---|---|---|---|
| **1 (leadoff)** | **4.23** | 4.6 | default too high by 0.37 |
| 2 | 4.16 | 4.5 | -0.34 |
| 3 | 4.04 | 4.4 | -0.36 |
| 4 | 3.94 | 4.2 | -0.26 |
| 9 | 3.00 | 3.7 | -0.70 |

Leadoff gets ~1.2 MORE PA/game than the 9-hole (4.23 vs 3.00) -- a ~40% exposure premium on every per-PA
counting stat. This is the largest, most reliable, fully leak-free lever in MLB props: it depends only on
the posted lineup, not on any rate estimate.

## Per-PA function tendencies by slot (measured)
| Per-PA stat | Slot 1 | Slot 2 | Slot 3-4 (driver) | Read |
|---|---|---|---|---|
| Runs / PA | 0.1332 | 0.1343 | 0.128 / 0.123 | top-2 score MOST (set the table, get driven in) |
| RBIs / PA | 0.1011 | 0.1129 | 0.130 / 0.131 | leadoff LOWEST RBI (bats with bases empty) |
| Stolen Bases / PA | 0.0241 | 0.0186 | 0.017 / 0.012 | leadoff HIGHEST SB (speed/table-setter) |

Read: relative to the lineup, the leadoff role is HIGH on Runs and Stolen Bases, LOW on RBIs.

## Which prop markets this role is SOFT on (where the pocket is)
- **Runs over** -- leadoff + slot-2 have the highest R/PA AND the highest PA. The compounding (high rate x
  high exposure) makes the Runs over the role's signature soft market on DFS pick'em. CAVEAT: Runs is
  context-driven (depends on teammates batting you in) -> teammate/context leak (edge map CUT 4, proof-
  standards trap); treat as model-view until the marginal is calibration-proven. Prefer it only when the
  TEAM total / opposing SP also points up.
- **Hits over** -- pure exposure play: more PA = more swings at a hit; sound Bernoulli shape. The leadoff
  PA premium is the cleanest reason a DFS Hits line is soft for a top-of-order bat.
- **Stolen Bases** -- highest for this role but very low rate and lumpy (edge map: SB display-only). Do not
  bet; flag as the role's flavor only.
- Sharp/efficient: nothing role-specific is sharp here -- the inefficiency IS the exposure the engine
  under-counts via the stale `_LINEUP_PA` defaults.

## How this role should inform the shrink baseline + exposure model
1. **Recalibrate `_LINEUP_PA` to the measured per-slot means** (exposure_mlb.py:28). This is the SINGLE
   MOST ACTIONABLE MLB-prop fix in this archetype set: the hardcoded ladder (4.6..3.7) is uniformly ~0.3-0.7
   PA too high vs the corpus (4.23..3.00). It is leak-free to derive (aggregate past rows only), affects
   EVERY per-PA prop, and is most consequential exactly where lineup-spot is the fallback (no-history
   call-ups, status "default" path expected_pa lines 64-66 / 75-77). Over-stated PA inflates every over.
2. **Prefer measured E[PA] over the slot default when history exists.** expected_pa already does this
   (status "ok" when n_games>0, exposure_mlb.py:70-73) -- keep the recency window (_RECENT_GAMES=15). The
   slot default is the COLD-START prior only; the fix in (1) matters most for cold starts.
3. **Do not role-condition the per-PA RATE off slot.** Slot drives EXPOSURE, not the bat's own rate; the
   rate prior should come from the contact/power role cluster (see those files), not the slot. Conflating
   them double-counts.

## Proof method before this prior is promoted past HYPOTHESIS
Per ../_framework/proof-standards.md: the `_LINEUP_PA` recalibration is a measurable, leak-free fix --
validate by comparing predicted-PA vs realized-PA MAE by slot on a held-out later window (must improve, not
regress). The Runs-over segment is HYPOTHESIS and demoted by the context-leak caveat; require BSS>0 vs
devigged close on >=2 season-halves before promoting, and never bet Runs as a same-game parlay leg (no
joint model, limitation #7).
