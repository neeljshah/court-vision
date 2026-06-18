# MLB ARCHETYPE PRIOR -- Contact / Pitch-to-Contact Pitcher (ROLE, not a person)
_Part of the edge-intelligence corpus (deep/actionable layer). Describes a ROLE/PLAYSTYLE, never an
individual -- binding graph rule. Grounds in the 30,411-row player_gamelogs.parquet (data/domains/mlb/,
2026-04-01..06-17), domains/mlb/player_rates_mlb.py, domains/mlb/exposure_mlb.py, and the MLB edge map
(../00-edge-map.md). Tier: HYPOTHESIS (priors sharpening the shrink baseline + flagging soft markets, not
$-edges). ASCII only. No $-edge claims._

## Who this role is (definition by signature, not by name)
A CONTACT / PITCH-TO-CONTACT PITCHER is a starter whose per-batter-faced strikeout rate sits in the
BOTTOM quartile of starters -- a soft-contact / ground-ball / command arm that retires hitters on batted
balls rather than the K, relying on the defense behind him. Classifier proxy for the profile below:
starters (mean outs/appearance >= 12 AND BF >= 80), K/BF in the bottom quartile. n=43 of 170 starters.

## Typical per-BF profile (measured, leak-free corpus means)
| Per-BF stat | Contact-pitcher | All starters | K-pitcher | Note |
|---|---|---|---|---|
| **Pitcher K / BF** | **0.1549** | 0.2154 | 0.2774 | the signature: -28% vs starter mean |
| Earned Runs / BF | 0.1237 | 0.1087 | 0.0878 | HIGHER ER -- more balls in play, BABIP risk |
| Hits Allowed / BF | 0.2405 | 0.2191 | 0.1952 | HIGHER -- contact allowed |
| Walks Allowed / BF | 0.0806 | 0.0812 | 0.0764 | ~average (command is NOT free of walks) |
| K / 9 IP | **6.07** | 8.19 | 10.18 | the headline number |
| Outs / start | 15.0 | 15.9 | 16.6 | mildly SHORTER (more contact -> more pitches/traffic) |
| BF / start | 21.8 | 22.4 | 22.5 | ~same exposure as any starter |

Read: a contact pitcher is LOW on Pitcher Ks, HIGH on Hits Allowed and Earned Runs, average on Walks
Allowed, and goes mildly SHORTER. The low-K and elevated-contact (H, ER) traits travel together -- the
mirror image of the strikeout-pitcher role.

## Exposure tendencies
- Starter: ~21.8 BF / ~15.0 outs (5.0 IP) per start -- mildly fewer outs than a K-pitcher (contact = more
  balls in play, more chances to extend an inning / get pulled). lam(Ks) = per_bf * E[BF] ~=
  0.1549 * 21.8 ~= 3.4 Ks/start (vs ~6.2 for a K-pitcher).
- Same `_DEFAULT_STARTER_BF = 24.0` cold-start over-statement applies (measured starter mean 22.4,
  exposure_mlb.py:32) -- inflates per-BF overs on no-history starters.

## Which prop markets this role is SOFT on (where the pocket is)
- **Pitcher Strikeouts UNDER** -- the role's signature divergence (-28% K/BF). A DFS Ks line set off the
  pooled league K/BF (0.215) is too HIGH for a true 0.155 K/BF arm -> the under is systematically live.
  Sound Bernoulli/Poisson shape (edge map PUSH-candidate). This is the role's strongest prop hypothesis,
  the mirror of the strikeout-pitcher's over.
- **Hits Allowed over** and **Earned Runs over** -- the role allows more contact (HA/BF +0.021, ER/BF
  +0.015 vs starter mean). Hits-Allowed is a sound per-BF success count (PUSH-candidate); ER is rough/
  sequence-dependent (model-view, edge map). Direction is right; bet only the sound shape (HA), and only
  after marginal calibration.
- **Outs under** -- mildly shorter starts; secondary, low-confidence (the outs delta is small, 15.0 vs
  15.9). Treat as flavor, not a bet.
- Sharp/efficient: liquid star contact arms at major books are sharp. The pocket is back-of-rotation
  contact starters on lazy DFS lines, and the cleanest single bet is the Ks UNDER.

## How this role should inform the shrink baseline + exposure model
1. **Role-conditioned K/BF baseline is wrong-direction without it.** The single global pitcher K/BF
   baseline (player_rates_mlb.py:133) shrinks a thin-history contact pitcher's K-rate UP toward 0.215 --
   exactly backwards for a 0.155 arm, biasing the Ks line too HIGH and killing the (live) under. PROPOSED
   (HYPOTHESIS): cluster the per-BF baseline by pitcher role so contact pitchers shrink toward ~0.155.
2. **ER / Hits-Allowed baselines too.** This role is HIGH on both; the pooled baseline under-states them.
   Role-conditioning the HA/BF and ER/BF baselines pulls the right way. (ER stays model-view -- rough shape.)
3. **Fix the BF default** (exposure_mlb.py:32 -> ~22.4) -- same leak-free cold-start correction as the
   K-pitcher file; it trims every per-BF over including this role's.
4. **Variance note.** Contact pitchers have HIGHER batted-ball/BABIP variance on ER and HA than K-pitchers
   (outcome depends on defense + luck); the unfit `dispersion` r (limitation #5) understates that tail.
   Inflate dispersion before any ER/HA over EV; the K-under is the safest shape because Ks are the
   pitcher's own action, least defense-dependent.

## Proof method before this prior is promoted past HYPOTHESIS
Per ../_framework/proof-standards.md: leak-free walk-forward; Pitcher-K (under) and Hits-Allowed Brier +
BSS vs devigged close (or P(over)-vs-realized + DFS line MOVEMENT); >=2 season-halves agree; demote ER
(sequence-dependent, leaky shape). Pre-commit the low-K-segment Ks-UNDER hypothesis (mirror of the K-pitcher
over) and test both together when the backfill lands -- if only one direction proves, suspect a selection
artifact. CALIBRATION-PROVEN only on a real props_eval_mlb segment run with BSS>0; CLV-PROVEN only on
forward paper CLV.
