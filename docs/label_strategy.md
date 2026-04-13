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
