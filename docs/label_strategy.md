# GitHub Label Strategy

Purpose: reduce triage friction and make execution status obvious.

## Label Set

### Domain labels
- `domain:cv`
- `domain:modeling`
- `domain:data`
- `domain:simulation`
- `domain:api`
- `domain:infra`
- `domain:risk`
- `domain:docs`

### Priority labels
- `prio:p0`
- `prio:p1`
- `prio:p2`

### State labels
- `state:blocked`
- `state:needs-decision`
- `state:ready`
- `state:in-progress`

### Gate labels (map to PLAN)
- `gate:drift`
- `gate:leakage`
- `gate:calibration`
- `gate:contracts`
- `gate:execution-risk`
- `gate:reproducibility`

## Usage Rules

1. Every issue must have:
   - one `domain:*` label,
   - one `prio:*` label,
   - at least one `gate:*` label if it affects investor-facing quality.
2. If work cannot move due to dependency, add `state:blocked` and note blocker in issue body.
3. Only use `prio:p0` for tasks that block release gates or data integrity.
4. Close issue only when evidence artifact path is added in the issue comment.

## Weekly Triage

In weekly triage, review all open issues by:
1. `prio:p0` first,
2. then `gate:*` coverage gaps,
3. then unblock `state:blocked` items.

---

# Prediction Labeling (Reliable / Thin / Reject) and CLV Tiering

Separate from GitHub triage, the *prediction* layer labels every candidate so the
execution layer can act on quality, not just a point estimate. The honest stance
throughout: a **REJECT is a success** (a measured null result), and the only
money-adjacent label is CLV (holding a better number than the close). No dollar
edge is labelled or claimed anywhere.

## Prop reliability tiers

A candidate is first labelled by how trustworthy its evaluation is, *before* any
sizing:

| Label | Meaning | Action |
|---|---|---|
| `reliable` | leak-free, walk-forward, holds on >= 2 independent corpora; line is consensus-quoted | eligible for the EV tier floors |
| `thin` | passes leak/WF checks but single-corpus, thin sample, or proxy-only close | sized only if it clears the **proxy-bumped** floor (+0.01); CLV flagged `clv_is_proxy` |
| `reject` | fails a leak/null/consensus check, or is a zero-edge direction (e.g. BLK OVER) | dropped before sizing -- recorded as an honest reject, never bet |

`thin` exists because a single good fold of four is usually a selection artifact;
promoting it would manufacture a fake edge. Reliability gating lives in the
policy filters of `src/prediction/bet_selector.py`
(`src/prediction/bet_policy.py`) and the three-book consensus filter in
`src/prediction/decision_engine.py`.

## EV / CLV tiers (the bet bucket)

A `reliable` (or floor-clearing `thin`) candidate is then bucketed by EV against
the best Shin-devigged price (`frontend/exec_decision.py`):

| Tier | EV floor (true close) | EV floor (proxy close) |
|---|---|---|
| A | >= 0.08 | >= 0.09 |
| B | >= 0.04 | >= 0.05 |
| C | >= 0.02 | >= 0.03 |
| no-bet | below the C floor | below the proxy C floor |

The in-game ranker (`decision_engine.classify_tier`) uses its own, lower
floors, not the frontend table above: `S` requires EV >= 0.08 plus a
projection delta >= 1.0 stat units, `A` requires EV >= 0.04, and `B` shares
the same 0.04 floor as `A` (calibrated 2026-05-26, raised from a 0.01
pre-calibration floor to drop Tier C emissions -- see
`src/prediction/decision_engine.py` TIER_S_EV/TIER_A_EV/TIER_B_EV). **Below
the C floor is `no_bet`, not a weaker bet** -- see [decisions](decisions.md)
DEC-015.

## Why label this way

- It keeps the *quality* judgement (reliable/thin/reject) separate from the
  *sizing* judgement (A/B/C/no-bet), so a reliable-but-low-EV prop and a
  thin-but-high-EV prop are treated differently and on purpose.
- It makes the no-bet outcome first-class: an efficient market means most
  candidates land in `reject` or `no_bet`, and that is the correct, honest result.
- CLV is the only forward scoreboard; tiers exist to decide *what to track*, not
  to assert a profit.

See also: [decisions](decisions.md) (tier floors, no-bet policy)  - 
[BETTING](BETTING.md) (edge/EV/CLV math)  -  [EXECUTION_GUIDE](EXECUTION_GUIDE.md)
(select -> ledger -> CLV)  -  [risk-framework](risk-framework.md) (sizing, live gate).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
