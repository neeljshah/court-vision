"""nba_q4_shift.py -- descriptive Q4-vs-Q1-Q3 per-36 rate SHIFT per player,
streamed from the local per-quarter player boxes at
data/cache/quarter_box/<game_id>_q<1..4>.json (q0 = full-game, ignored here).

This is the un-refusal companion to clutch_context.py, which honestly REFUSED
a late-game number because player_boxscores.parquet is full-game-only. That
per-period grain DOES exist raw in data/cache/quarter_box/ -- this module reads
it directly (bypassing the lossy full-game ingest) to compute a purely
DESCRIPTIVE historical Q4-vs-earlier per-36 scoring/rebounding/assist rate
shift. It is NOT a clutch metric (no score/time-margin context) and NOT
predictive. edge_claimed:false.

Streams one JSON file at a time (never holds the ~5,000-file cache in memory
at once) -- for each game: accumulate Q1+Q2+Q3 minutes/pts/reb/ast per player,
then accumulate Q4 separately, then discard the file.

Floor: q4_games>=25 and q13_min>=100 and q4_min>=25 (stable per-36 rates only).

Output: out/nba_q4_shift.json (this committed JSON IS the recorded artifact --
--check reloads it and does not require data/ locally, i.e. is clone-safe).
Usage:
  python -m scripts.platformkit.analytics_showcase.nba_q4_shift
  python -m scripts.platformkit.analytics_showcase.nba_q4_shift --check
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "nba_q4_shift.json"
QB_DIR = REPO / "data" / "cache" / "quarter_box"

Q4_GAMES_FLOOR = 25
Q13_MIN_FLOOR = 100.0
Q4_MIN_FLOOR = 25.0
TOP_N = 15

METHOD = (
    "Per-player Q4 vs Q1-Q3 per-36 rates from local per-quarter player boxes; a "
    "floor of >=25 Q4 appearances. Descriptive historical splits, not a clutch "
    "metric and not a prediction."
)
UN_REFUSAL_NOTE = (
    "The site's clutch_context module honestly REFUSED a clutch number because "
    "the grain was wrong. This is what it took to turn that refusal into an "
    "honest number: not 'clutch', just the measured Q4-vs-earlier per-36 shift. "
    "Published alongside the refusal."
)
CONFOUNDS = [
    "Q4 minutes are heavily lineup- and blowout-dependent: stars sit in "
    "blowouts, benches play garbage time -- this is NOT playing-time-neutral.",
    "per-36 on small Q4 minutes is noisy even at the floor; treat as "
    "descriptive, not a ranking of ability.",
    "NOT a clutch metric (clutch requires score/time context this does not "
    "have) and NOT predictive.",
    "fixed historical game set; not current-season.",
]
NARRATIVE_KEYS = ("method", "un_refusal_note", "confounds", "refusal_artifact")


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def _parse_min(s) -> float:
    if not s:
        return 0.0
    try:
        mm, ss = str(s).split(":")
        return int(mm) + int(ss) / 60.0
    except (ValueError, AttributeError):
        return 0.0


def _season_from_game_id(game_id: str) -> str:
    yy = int(game_id[3:5])
    start = 2000 + yy
    return f"{start}-{str(start + 1)[-2:]}"


def _record(store: dict, pid, name: str, team: str) -> dict:
    if pid not in store:
        store[pid] = {
            "name": name, "team": team,
            "q4_min": 0.0, "q13_min": 0.0, "q4_games": 0,
            "q4_pts": 0, "q13_pts": 0, "q4_reb": 0, "q13_reb": 0,
            "q4_ast": 0, "q13_ast": 0,
        }
    return store[pid]


def _per36(total: float, minutes: float) -> float:
    return total / minutes * 36.0 if minutes > 0 else 0.0


def _top_rows(rows: list, stat: str, n: int, reverse: bool) -> list:
    ordered = sorted(rows, key=lambda r: r[stat]["shift"], reverse=reverse)
    return [{
        "player_name": r["player_name"],
        f"q4_{stat}_per36": r[stat]["q4_per36"],
        f"q13_{stat}_per36": r[stat]["q13_per36"],
        "shift": r[stat]["shift"],
        "q4_games": r["q4_games"],
    } for r in ordered[:n]]


def build() -> dict:
    if not QB_DIR.exists():
        return {"status": "local_corpus_absent", "sport": "nba", "needed_artifacts": [_rel(QB_DIR)]}

    q4_files = sorted(QB_DIR.glob("*_q4.json"))
    store: dict = {}
    seasons: set = set()

    for q4_path in q4_files:
        game_id = q4_path.name[: -len("_q4.json")]
        seasons.add(_season_from_game_id(game_id))

        for q in (1, 2, 3):
            qp = QB_DIR / f"{game_id}_q{q}.json"
            if not qp.exists():
                continue
            with open(qp, "r", encoding="utf-8") as f:
                d = json.load(f)
            for p in d.get("players", []):
                mins = _parse_min(p.get("min", ""))
                if mins <= 0:
                    continue
                rec = _record(store, p["player_id"], p["player_name"], p["team_abbreviation"])
                rec["q13_min"] += mins
                rec["q13_pts"] += p.get("pts", 0)
                rec["q13_reb"] += p.get("reb", 0)
                rec["q13_ast"] += p.get("ast", 0)

        with open(q4_path, "r", encoding="utf-8") as f:
            d4 = json.load(f)
        for p in d4.get("players", []):
            mins = _parse_min(p.get("min", ""))
            if mins <= 0:
                continue
            rec = _record(store, p["player_id"], p["player_name"], p["team_abbreviation"])
            rec["q4_min"] += mins
            rec["q4_pts"] += p.get("pts", 0)
            rec["q4_reb"] += p.get("reb", 0)
            rec["q4_ast"] += p.get("ast", 0)
            rec["q4_games"] += 1

    n_considered = len(store)
    rows = []
    for rec in store.values():
        if rec["q4_games"] < Q4_GAMES_FLOOR or rec["q13_min"] < Q13_MIN_FLOOR or rec["q4_min"] < Q4_MIN_FLOOR:
            continue
        row = {"player_name": rec["name"], "q4_games": rec["q4_games"]}
        for stat in ("pts", "reb", "ast"):
            q4_v = _per36(rec[f"q4_{stat}"], rec["q4_min"])
            q13_v = _per36(rec[f"q13_{stat}"], rec["q13_min"])
            row[stat] = {
                "q4_per36": round(q4_v, 2),
                "q13_per36": round(q13_v, 2),
                "shift": round(q4_v - q13_v, 2),
            }
        rows.append(row)

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (
            "Descriptive Q4-vs-Q1-Q3 per-36 scoring, rebounding, and assist rate "
            "shift per player, from local per-quarter boxes -- not a late-game-"
            "skill or predictive claim."
        ),
        "method": METHOD,
        "un_refusal_note": UN_REFUSAL_NOTE,
        "refusal_artifact": "scripts/platformkit/analytics_showcase/out/clutch_context.json",
        "observation_window": {
            "n_games": len(q4_files),
            "seasons": ", ".join(sorted(seasons)) + " present in this cache",
            "note": "a fixed set of games in this cache, not the current season",
        },
        "floors": f"q4_games>={Q4_GAMES_FLOOR} and q13_min>={Q13_MIN_FLOOR:g} and q4_min>={Q4_MIN_FLOOR:g}",
        "n_considered": n_considered,
        "n_qualified": len(rows),
        "pts_shift": {
            "top_risers": _top_rows(rows, "pts", TOP_N, True),
            "top_fallers": _top_rows(rows, "pts", TOP_N, False),
        },
        "reb_shift": {"top_risers": _top_rows(rows, "reb", TOP_N, True)},
        "ast_shift": {"top_risers": _top_rows(rows, "ast", TOP_N, True)},
        "confounds": CONFOUNDS,
    }


def main() -> dict:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    return result


def _no_nan_inf(obj) -> bool:
    if isinstance(obj, float):
        return not (math.isnan(obj) or math.isinf(obj))
    if isinstance(obj, dict):
        return all(_no_nan_inf(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_nan_inf(v) for v in obj)
    return True


def _check():
    assert OUT_JSON.exists(), f"missing {OUT_JSON} -- run the module (no --check) first"
    assert OUT_JSON.stat().st_size > 0, f"{OUT_JSON} is empty"
    result = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert result["status"] in ("ok", "local_corpus_absent"), result["status"]

    if result["status"] == "ok":
        assert result["descriptive_only"] is True
        assert result["edge_claimed"] is False
        assert result["observation_window"]["n_games"] > 0
        assert 0 < result["n_qualified"] <= result["n_considered"]

        risers = result["pts_shift"]["top_risers"]
        assert 0 < len(risers) <= TOP_N
        for row in risers:
            assert row["q4_games"] >= Q4_GAMES_FLOOR, row
        shifts = [r["shift"] for r in risers]
        assert all(shifts[i] >= shifts[i + 1] - 1e-9 for i in range(len(shifts) - 1)), "top_risers not non-increasing"

        assert 0 < len(result["reb_shift"]["top_risers"]) <= TOP_N
        assert 0 < len(result["ast_shift"]["top_risers"]) <= TOP_N

        assert _no_nan_inf(result), "NaN/inf found in emitted numbers"

        narrative_blob = json.dumps({k: result[k] for k in NARRATIVE_KEYS}).lower()
        assert "clutch" in narrative_blob, "expected 'clutch' referenced in the un-refusal narrative"
        scrubbed = {k: v for k, v in result.items() if k not in NARRATIVE_KEYS}
        rest_blob = json.dumps(scrubbed).lower()
        assert "clutch" not in rest_blob, "'clutch' used as a metric label outside the narrative fields"
    else:
        assert "needed_artifacts" in result
    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _check()
    else:
        res = main()
        if res["status"] == "ok":
            top = res["pts_shift"]["top_risers"][0] if res["pts_shift"]["top_risers"] else None
            print(json.dumps({
                "status": "ok",
                "n_games": res["observation_window"]["n_games"],
                "seasons": res["observation_window"]["seasons"],
                "n_considered": res["n_considered"],
                "n_qualified": res["n_qualified"],
                "top_pts_riser": top,
            }, indent=2))
        else:
            print(json.dumps(res, indent=2))
        print(f"wrote {OUT_JSON}")
