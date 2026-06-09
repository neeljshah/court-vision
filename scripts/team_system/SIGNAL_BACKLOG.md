# Signal Lab — backlog (the agent's queue)

Each row is a SIGNAL HYPOTHESIS to mine from the PBP/data and run through `signal_lab.validate_signal`
(leak-free OOS lift + split-half stability + orthogonality + material). The agent builds the as-of panel,
calls the lab, records the verdict to the registry, and (only if VALIDATED) flags it for gated wiring.
Discipline: surgical, never kitchen-sink; the right metric (rmse/logloss, never MAE-only); board stays green;
nothing auto-applied to the engine.

Status: `[ ]` untested · `[x]` in registry · grain in (possession / player-game / team-game / lineup).

## Possession-grain (target = pts on the possession, or scored binary; baseline = the §state features)
- [x] **origin_transition** — fromturnover/fastbreak + 2ndchance → PPP. **VALIDATED** (−0.76% rmse).
- [x] **shot_clock_leverage** — possession duration (shot-clock used) → PPP. **VALIDATED** (−2.86% rmse, split-half −0.14/−0.13, ortho 0.31; quick<7s 1.354 vs late≥16s 0.968 PPP). The xFG-by-clock curve = a real sim modulator (gated proposal in WIRING_PROPOSALS.md).
- [x] **after_timeout (ATO)** — first possession after a `timeout` → PPP. **REJECTED** (no lift, +0.00%; ATO PPP 1.047 ≈ half-court 1.035 — set plays are not more efficient at the possession level).
- [ ] **post_made_vs_live** — possession after opponent MADE FG (set defense) vs after a miss/steal → PPP. (`after_made` col now in pbp_possessions: 1.082 PPP set-D vs higher live-ball; next to test surgically)
- [ ] **bonus_state** — offense in the penalty (`inpenalty`) → FT rate / PPP. (col mined: 1.477 PPP but only 0.7% tagged — CDN `inpenalty` qualifier is under-populated; needs a derived bonus-state from team-foul count before it's testable)
- [ ] **lead_state** — possession while trailing big vs leading (score margin buckets) → PPP / shot selection.

## Player-game-grain (target = pts/reb/ast; baseline = recency-blend + role)
- [x] **same_day_availability** ⭐ — teammates OUT (box-absence as-of) → vacated load re-routes. **REJECTED (immaterial,
      but the effect is REAL+STABLE).** Built from box-absence (injury feed dates 2026-05-26+ don't overlap the
      regular-season gamelog; box-absence is the leak-free ground truth the feed predicts). Vacancy in 48% of
      rotation games; present players score **+0.30 vs −1.23** with/without a vacancy (~+1.5pt), corr +0.145, split-half
      +0.11/+0.07 (stable, right sign) — but OOS lift only −0.145% (< 0.2% floor) because **recency already absorbs it**.
      Independently re-derives the documented "minutes = 19% of variance, availability model is low-value" ceiling: even
      with perfect who's-out knowledge the point-prediction gain is immaterial. Availability's value is **same-day
      FRESHNESS/CLV** (bet before the line moves), NOT a point feature. Don't retry as a marginal-accuracy feature.
- [ ] **matchup_shot_diet_vs_rimD** — player rim-attack% × opponent rim_d (the floater-immune split) → pts.
- [ ] **opp_position_defense** — opponent's allowed pts to the player's position (as-of) → pts.
- [ ] **pace_matchup** — combined as-of pace → counting-stat volume (reb/ast/pts).
- [ ] **rest_x_age** — rest days × player age interaction → pts/min (older players rest-sensitive).
- [ ] **foul_trouble_carryover** — recent foul-out / high-PF games → minutes/usage next game.
- [ ] **revenge/back-to-back-opp** — 2nd game of a quick rematch → familiarity effect (likely REJECT).

## Team-game-grain (target = margin/total/win; baseline = net-diff composition)
- [x] **tov_force / ft_force** — split-half stable identities (0.84/0.72); double-count at team-total (M3).
- [ ] **oreb_matchup** — own OREB% × opp DREB% → second-chance points (orthogonal to net?).
- [ ] **transition_margin** — team transition-PPP edge × opp TO-proneness → margin (vs net-diff baseline).
- [ ] **rest_advantage** — rest-days differential → margin (as-of).

## Lineup-grain (target = lineup net / on-court PPP)
- [ ] **lineup_spacing** — # of catch-shoot shooters on floor → PPP (from pbp_attributes diet).
- [ ] **lineup_rim_protection** — best int_d on floor → opp rim PPP allowed.
- [ ] **two_creator_lineups** — ≥2 high-self-create players → assist rate / iso frequency.

## Defender-grain (already partly done)
- [x] **defender_suppression** — cross-season 0.63, mostly orthogonal; gated scouting/in-game (pair-level NOISE).

> When low, append more hypotheses from the PBP detail not yet mined (descriptors: putback/cutting/turnaround;
> qualifiers: defensivegoaltending; x/y shot coordinates; assist-network structure). Always one signal at a time.
