# PROPOSED (not applied) -- S452: pass the real opponent through stitch_router's props endpoint

STATUS: PROPOSED DIFF ONLY. Nothing in this file has been applied to
`api/stitch_router.py` (human-gated -- this lane reads it, never edits it).
A human applies this outside the lane, per the S452 spec CHANGE item (iii).

## Before-condition this proposal responds to

`api/stitch_router.py:131-134` (unchanged at base sha cbe544697):

```python
@router.get("/player/{player_id}/props")
async def get_player_props(player_id: str, season: str = "2024-25"):
    """Get player prop predictions for a specific player"""
    try:
        props = predict_props(player_id, season)
```

`predict_props` (`src/prediction/player_props.py:2235-2242`):

```python
def predict_props(
    player_name: str,
    opp_team: str,
    season: str = "2025-26",
    n_games: int = 10,
    ref_names: Optional[list] = None,
    game_id: Optional[str] = None,
) -> dict:
```

Two positional arguments are passed (`player_id`, `season`) against six
parameters. Position 0 (`player_id`) binds to `player_name` -- a second,
pre-existing defect this row does not scope or fix. Position 1 (`season`)
binds to `opp_team` -- the defect this row scopes: the season STRING lands
in the opponent-team SLOT, so every downstream opponent-defence lookup keys
off a season string ("2024-25") instead of a team abbreviation.

The AST-derived construct that proves this binding (built by this row's
`scripts/platformkit/eval_gate/served_path_adjudication.py`,
`stitch_router_binding_proof`) reads the call site and the callee signature
from source text only -- no import, no execution -- and reports:

```
call_positional_args = ["player_id", "season"]
callee_params        = ["player_name", "opp_team", "season", "n_games", "ref_names", "game_id"]
bindings = [{"position": 0, "call_arg": "player_id", "param": "player_name"},
            {"position": 1, "call_arg": "season",    "param": "opp_team"}]
mismatch = True
```

A real precedent for the correct call shape already exists in this repo at
`api/main.py:365-383` (`def props(player_id, opp_team="GSW", season="2025-26")`,
which calls `_pp(player_id, opp_team, season=season)`) -- stitch_router.py's
props route is the one endpoint that skipped this pattern.

## Proposed change -- SKETCH, NOT APPLIED

```python
@router.get("/player/{player_id}/props")
async def get_player_props(player_id: str, opp_team: str = "GSW", season: str = "2024-25"):
    """Get player prop predictions for a specific player"""
    try:
        props = predict_props(player_id, opp_team, season=season)
        return {
            "player_id": player_id,
            "opp_team": opp_team,
            "season": season,
            "predictions": props,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Player props error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

Adds `opp_team` as a query parameter (default `"GSW"`, mirroring
`api/main.py`'s existing default) and passes `season` as a keyword so the
positional slot for `opp_team` is filled by a real team abbreviation instead
of the season string, matching the already-correct sibling endpoint. The
`player_id` -> `player_name` positional mismatch is intentionally NOT
touched here -- it is a second, unscoped defect (spec PREMISE (e)).

## Numerical impact -- NOT VERIFIED

Whether the season-string opponent produced materially different predictions
than a real opponent abbreviation is NOT VERIFIED by this row: measuring
that would require executing `_OpponentDefense.factors(...)`, a production
loader this row is barred from running, and the opponent-defence factors may
return identical neutral values for both inputs (spec AMENDMENT 1c). This
proposal is a structural correction, not a scored calibration claim.

## Note

This is the tracked twin of the gitignored
`docs/research/organization-sprint/PROPOSED_S452_stitch_router_opponent.md`
(docs/research/** is local-only per this repo's rules). Both copies carry
identical prose; this copy exists so a vocabulary scan and
`contract_preflight` can see it as a tracked, landable candidate file.
