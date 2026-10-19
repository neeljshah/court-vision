# PROPOSED (not applied): wire week_fill_accounting.py into forward_week_report.py

Status: PROPOSED only. `scripts/platformkit/ops/forward_week_report.py` is a
must-not-move module of the landed S427 row (its `_row()` is quoted verbatim
by S443's BINDING BEFORE-CONDITION (a), and S427's ACCEPTANCE RULE binds
"every landed module named above byte-identical to master"). This diff is
NOT applied anywhere; it is a proposal for a later, separately-verified row.

## Where

`scripts/platformkit/ops/forward_week_report.py`, `_row()` (currently
:163-183 on master `5d5c1b58d`):

```python
    return dict(iso_year=iso_year, iso_week=iso_week, family=declaration["family"],
                sport=declaration["sport"],
                game_ids=sorted(game["game_id"] for game in games),
                qualified_game_ids=qualified, fill_bearing_game_ids=[],
                qualified_games=len(qualified), fill_bearing_games=0, exclusions=exclusions,
                capture_gap_seconds=str(Decimal(widest) / Decimal(1000)),
                source_artifact_path=str(out), source_sha256=digest)
```

## Proposed shape

`_row()` would take one new optional parameter, `fill_summary: dict | None`
-- the JSON produced by `scripts.platformkit.execution.week_fill_accounting
.build()` / its `--out` artifact for the SAME `(iso_year, iso_week)` -- and,
when supplied, replace the two hardcoded fields:

```python
def _row(iso_year, iso_week, declaration, games, out, digest, fill_summary=None):
    ...
    if fill_summary is None:
        fill_bearing_game_ids, fill_bearing_games = [], 0
    else:
        fill_bearing_game_ids = sorted(
            game_id for game_id in (game["game_id"] for game in games)
            if fill_summary["per_game"].get(game_id, {}).get("qualified", 0) > 0)
        fill_bearing_games = len(fill_bearing_game_ids)
    return dict(iso_year=iso_year, iso_week=iso_week, family=declaration["family"],
                sport=declaration["sport"],
                game_ids=sorted(game["game_id"] for game in games),
                qualified_game_ids=qualified, fill_bearing_game_ids=fill_bearing_game_ids,
                qualified_games=len(qualified), fill_bearing_games=fill_bearing_games,
                exclusions=exclusions,
                capture_gap_seconds=str(Decimal(widest) / Decimal(1000)),
                source_artifact_path=str(out), source_sha256=digest)
```

`main()` would load `docs/evidence/forward/weeks/<iso_year>-W<iso_week>_fills
.json` (if present; absent stays `fill_summary=None`, preserving today's
empty-projection behavior byte-for-byte) and pass it through to `_row()`.
This keeps `family_week_ledger.py`'s exact 13-field `_validate` set
(:90-93) unchanged -- only the VALUES of two already-declared fields move,
nothing is added or renamed, matching S390's binding schema.

## Open gap this diff does NOT resolve (flag for the wiring row, not this one)

`week_fill_accounting.py`'s per-fill identity uses fill_realism's
`game_key` (STEP 0's receipt schema; see BINDING BEFORE-CONDITION (d)), but
`forward_week_report.py`'s `games` list is keyed by `game_id` (the
qualification pipeline's identity space). The codex lane's earlier memo for
this same row already flagged this exact seam ("confirming astra's premise
that ... game_key -> ticker linkage" -- `docs/evidence/harness/
S443_week_fill_accounting_2026-09-24.md`, pre-AMENDMENT-1 text). The sketch
above writes `fill_summary["per_game"].get(game_id, ...)` as if `game_key ==
game_id`; nothing in this row or in fill_receipts.py's schema proves that
holds across every sport/family. A wiring row must verify -- or add an
explicit game_key->game_id lookup for -- that identity before this sketch
can be applied and re-verified against S427's own contract.
