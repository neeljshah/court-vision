"""clutch_context.py -- NBA late-game (Q4 + OT / clutch) per-36 rate SHIFTS,
IF the boxscores parquet carried a period/clutch grain. It does NOT: the local
player_boxscores.parquet is FULL-GAME aggregate. So this module is the
HONEST-REFUSAL exhibit -- it probes the live schema, confirms the late-game
grain is absent, and emits status:not_buildable naming exactly the fields a
re-ingest would need. No fabricated late-game numbers, and NO chart.

SCOPE (DESCRIPTIVE_ONLY, only once/if buildable): partition each player-game box
line into full-game vs late-game (period >= 4, i.e. Q4 + OT) and report the
per-36 rate SHIFT (late minus full) per player. It would NOT be a predictor, NOT
a claim of clutch "skill", and NO market/ROI/$ edge -- purely a within-player
descriptive of where late-game rates sit relative to the full-game baseline.

WHY not buildable now (honest, not papered over): player_boxscores.parquet is
written by domains/basketball_nba/ingest_boxscores.py, which SUMS the per-quarter
cache data/cache/quarter_box/<game_id>_q<period>.json across quarters into ONE
full-game row per (player, game). The per-period grain EXISTS in that raw cache
but is discarded at ingest. Making this analytic buildable is an UPSTREAM
data-layer change (re-ingest keeping a `period` column) -- out of scope for a
read-only showcase module, which is why this emits a refusal instead of guessing
late-game splits off full-game totals.

FLOORS (declared; bind the analytic only once a late-game grain exists):
  - MIN_LATE_MIN: total late-game minutes a player needs before being ranked.
  - MIN_GAMES: qualifying games a player needs before being ranked.
  - per-36 computed over SUMMED minutes at the grain, never per-game averaged.

Truth source for claim discipline: docs/JOB_EVIDENCE_PACKET.md.
Output: out/clutch_context.json (status: not_buildable | no_data). NO chart.
CLI: python -m scripts.platformkit.analytics_showcase.clutch_context [--check]
"""
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "clutch_context.json"
PARQUET = REPO / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"

# Declared floors (apply only once/if a late-game grain exists; declared here so
# they are frozen before any result is seen, never tuned to an output).
MIN_LATE_MIN = 200   # total late-game minutes a player needs to be ranked
MIN_GAMES = 15       # qualifying games a player needs to be ranked

# Box counting stats we would rate per-36 at the late-game grain -- mirrors the
# full-game columns ingest_boxscores already writes.
BOX_STATS = ["pts", "reb", "ast", "stl", "blk", "tov", "fga", "fta", "pf"]

# The late-game grain this analytic needs but the FULL-GAME parquet lacks.
# Buildable iff the schema exposes EITHER a period discriminator (long/tidy grain)
# OR an explicit late-game/clutch stat block (wide grain). Presence of ANY of
# these flips the module OUT of the not_buildable refusal.
GRAIN_FIELDS_ANY = [
    "period",                 # long grain: one row per (player, game, period)
    "clutch", "is_clutch",    # a clutch-window flag / subset marker
    "q4_min", "clutch_min",   # wide grain: explicit late-game minutes column
]


def _rel(path: Path) -> str:
    """Repo-relative path string for the JSON (never leaks an absolute path)."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _read_columns(path: Path) -> list:
    """Column NAMES only -- reads the parquet FOOTER, ZERO data columns.

    The maximally column-selective read: no row groups are touched.
    """
    import pyarrow.parquet as pq  # standard parquet engine already in this repo
    return list(pq.read_schema(str(path)).names)


def build(path: Path = PARQUET) -> dict:
    """Probe the boxscores schema and return the honest verdict dict.

    Never raises: a missing file or unreadable schema fails CLOSED with
    status:no_data and a reason, in the same spirit as comeback_atlas.
    """
    stamp = datetime.now(timezone.utc).isoformat()
    base = {"label": "DESCRIPTIVE_ONLY", "edge_claimed": False,
            "as_of": stamp, "input": _rel(path), "chart": None}

    if not path.exists():
        return {**base, "status": "no_data",
                "note": "player_boxscores.parquet absent (data/ is gitignored / "
                        "not built in this clone) -- cannot probe schema. This is "
                        "not a modeling result; build the parquet, then re-run."}
    try:
        cols = _read_columns(path)
    except Exception as exc:  # noqa: BLE001 -- fail closed with the reason
        return {**base, "status": "no_data",
                "note": f"could not read parquet schema at {_rel(path)}: {exc}"}

    present_grain = [c for c in GRAIN_FIELDS_ANY if c in cols]
    if present_grain:
        # ponytail: gate opened -> surface it, don't silently keep refusing and
        # don't fabricate an unwritten analytic. Re-author against the real grain.
        return {**base, "status": "fields_present_analytic_not_implemented",
                "grain_fields_found": present_grain,
                "note": "A late-game/clutch grain APPEARED in the schema. The "
                        "per-36 shift analytic is intentionally NOT implemented in "
                        "this module (authored as the honest-refusal exhibit); "
                        "re-author it against the new grain rather than trusting "
                        "this stub to compute the shifts."}

    return {
        **base, "status": "not_buildable",
        "reason": "player_boxscores.parquet is FULL-GAME aggregate; it carries no "
                  "period/clutch grain, so late-game per-36 SHIFTS cannot be "
                  "computed from it without fabricating the split.",
        "fields_present": cols,
        "fields_needed": {
            "grain_discriminator_any_of": GRAIN_FIELDS_ANY,
            "explanation": "EITHER a `period` column (making the parquet one row "
                           "per player-game-period -- long/tidy) OR an explicit "
                           "late-game/clutch stat block (e.g. clutch_min + "
                           "clutch_<stat>). Given a `period` grain, late-game is "
                           "period >= 4 (Q4 + OT).",
            "plus_box_stats_at_that_grain": BOX_STATS,
            "minutes_field_at_that_grain": "min",
        },
        "where_the_grain_actually_lives": {
            "raw_cache": "data/cache/quarter_box/<game_id>_q<period>.json "
                         "(per-period player box lines DO exist here)",
            "why_absent_downstream": "domains/basketball_nba/ingest_boxscores.py "
                                     "SUMS those quarter files into ONE full-game "
                                     "row per (player, game); the period grain is "
                                     "discarded at ingest.",
            "fix_location": "upstream data layer (re-ingest keeping `period`); "
                            "out of scope for this read-only showcase module.",
        },
        "declared_floors_when_buildable": {
            "min_late_minutes_total": MIN_LATE_MIN,
            "min_qualifying_games": MIN_GAMES,
            "normalization": "per-36 over SUMMED minutes at the grain, not "
                             "per-game averaged",
        },
        "story": "Late-game per-36 SHIFT analytic NOT BUILT: the NBA boxscores "
                 "parquet is full-game aggregate with no period/clutch grain. "
                 "Honest refusal -- names the exact fields a re-ingest would need "
                 "(and where the grain already lives) rather than manufacturing "
                 "clutch numbers off full-game rows.",
    }


def main() -> int:
    out = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps({"status": out["status"], "json_out": str(OUT_JSON),
                      "story": out.get("story") or out.get("note")},
                     indent=2, ensure_ascii=True))
    return 0


def check() -> int:
    assert OUT_JSON.exists() and OUT_JSON.stat().st_size > 0, OUT_JSON
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    assert data.get("status") in {
        "not_buildable", "no_data", "fields_present_analytic_not_implemented",
    }, data.get("status")
    assert data.get("edge_claimed") is False, "must not claim an edge"
    assert data.get("chart") is None, "honest-refusal path emits NO chart"
    if data["status"] == "not_buildable":
        # the whole point: a refusal must NAME the fields it would need
        assert data["fields_needed"]["grain_discriminator_any_of"], "must name fields needed"
        assert data.get("fields_present"), "must report what the parquet actually has"
    print("OK: clutch_context self-check passed (status=%s)" % data["status"])
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(check() if "--check" in sys.argv else main())
