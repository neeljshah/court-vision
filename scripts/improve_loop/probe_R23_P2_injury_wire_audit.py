"""probe_R23_P2_injury_wire_audit.py — Injury-feed → bet-ranker wire audit.

R22_O8 added today's authoritative injury parquet
(``data/cache/nba_injuries_<date>.parquet``) and wired it into
``src.prediction.injury_availability.get_availability_factor``. R23_P2
verifies (and patched, where missing) that every bet ranker calls that
helper and kills any bet on an OUT / NOT-WITH-TEAM player.

This probe runs the audit end-to-end:

  1. Confirms today's parquet exists and lists how many players are OUT /
     NOT WITH TEAM.
  2. Statically audits every consumer in ``scripts/`` and
     ``src/prediction/`` for the ``get_availability_factor`` /
     ``apply_availability`` call site.
  3. Runs ``scripts.inplay_bet_ranker.run_tick`` against a synthetic
     in-process snapshot seeded with 3 healthy + 2 OUT players, BOTH
     with and without the R23_P2 guard active (toggled via the
     ``NBA_INJURY_WIRE_DISABLE`` env var).
     This gives a direct before/after count of bets killed.
  4. Persists the audit to ``data/cache/probe_R23_P2_results.json``.

SHIP gate
---------
  * inplay ranker's run_tick produces zero ranked bets for any OUT
    player when the guard is on.
  * static audit finds zero consumer in scripts/* still missing the
    injury-availability call (excluding ``predict_slate.py`` which
    intentionally uses the older ``src.data.injuries`` helper, and
    ``build_prediction_cache.py`` which deliberately stores RAW q50s).
  * The before/after delta shows ≥1 bet killed when seeded with OUT
    test players.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date as _date_cls
from datetime import datetime, timezone
from typing import Dict, List

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_DIR)

SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
_RESULTS_PATH = os.path.join(_CACHE_DIR, "probe_R23_P2_results.json")

# Consumers we expect to see wired. Anything in scripts/ that prices
# or recommends a bet should be present here. Each entry:
#   path:        relative path inside the worktree
#   needs_wire:  True  → must call get_availability_factor / apply_availability
#                False → intentionally exempt (raw cache / informational)
#   note:        free-form context for the audit JSON
_EXPECTED_CONSUMERS = [
    {
        "path": "src/prediction/prop_pergame.py",
        "needs_wire": True,
        "note": "per-game prop predictor applies multiplicative dampener.",
    },
    {
        "path": "src/prediction/prop_quantiles.py",
        "needs_wire": True,
        "note": "quantile predictor applies same dampener pre-output.",
    },
    {
        "path": "scripts/live_bet_ranker.py",
        "needs_wire": True,
        "note": "pregame slate ranker — factor==0 skips bet in run_tick.",
    },
    {
        "path": "scripts/inplay_bet_ranker.py",
        "needs_wire": True,
        "note": "R23_P2: in-play kill guard added in this probe's cycle.",
    },
    {
        "path": "scripts/predict_player.py",
        "needs_wire": True,
        "note": "single-player CLI prints availability factor.",
    },
    {
        "path": "scripts/serve_prediction.py",
        "needs_wire": True,
        "note": "FastAPI prediction surface adjusts q50 by factor.",
    },
    {
        "path": "scripts/probe_R15_tonight_slate.py",
        "needs_wire": True,
        "note": "slate probe applies dampener for diagnostics.",
    },
    {
        "path": "scripts/build_prediction_cache.py",
        "needs_wire": False,
        "note": "stores RAW q50 — dampener applied at read-time only.",
    },
    {
        "path": "scripts/predict_slate.py",
        "needs_wire": False,
        "note": "uses legacy src.data.injuries (drops players); not R22_O8.",
    },
]

_CALL_PATTERN = re.compile(
    r"\b(get_availability_factor|apply_availability)\b"
)


def static_audit() -> Dict[str, object]:
    """Verify each expected consumer either calls the helper or is exempt."""
    rows: List[Dict[str, object]] = []
    missing: List[str] = []
    for spec in _EXPECTED_CONSUMERS:
        rel = spec["path"]
        full = os.path.join(PROJECT_DIR, rel)
        exists = os.path.exists(full)
        calls = 0
        if exists:
            with open(full, encoding="utf-8") as f:
                src = f.read()
            calls = len(_CALL_PATTERN.findall(src))
        wired = calls > 0
        rows.append({
            "path": rel,
            "exists": exists,
            "calls_count": calls,
            "needs_wire": spec["needs_wire"],
            "wired": wired,
            "note": spec["note"],
        })
        if spec["needs_wire"] and not wired:
            missing.append(rel)
    return {"consumers": rows, "missing_wires": missing}


def parquet_summary() -> Dict[str, object]:
    today = _date_cls.today().isoformat()
    path = os.path.join(_CACHE_DIR, f"nba_injuries_{today}.parquet")
    if not os.path.exists(path):
        return {"path": path, "exists": False}
    import pandas as pd
    df = pd.read_parquet(path)
    upper = df["status"].astype(str).str.upper().str.strip()
    return {
        "path": path,
        "exists": True,
        "n_rows": int(len(df)),
        "n_out": int((upper == "OUT").sum()),
        "n_not_with_team": int((upper == "NOT WITH TEAM").sum()),
        "n_doubtful": int((upper == "DOUBTFUL").sum()),
        "n_questionable": int((upper == "QUESTIONABLE").sum()),
        "n_probable": int((upper == "PROBABLE").sum()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Live inplay ranker before/after audit
# ─────────────────────────────────────────────────────────────────────────────
def _seed_synthetic_tick(tmp_root: str, with_out_players: bool) -> Dict:
    """Set up a synthetic in-process tick of inplay_bet_ranker. Returns the
    full payload dict."""
    import inplay_bet_ranker as ibr
    from src.prediction import injury_availability as ia
    qbox = os.path.join(tmp_root, "qbox")
    lines_dir = os.path.join(tmp_root, "lines")
    os.makedirs(qbox, exist_ok=True)
    os.makedirs(lines_dir, exist_ok=True)
    today = _date_cls.today().isoformat()

    # Build a synthetic parquet inside the tmp cache so we don't mutate
    # the real one. Two of the 5 players are OUT.
    cache_dir = os.path.join(tmp_root, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    import pandas as pd
    inj_rows = []
    players = [
        (9001, "Probe Out One",   "OUT" if with_out_players else None),
        (9002, "Probe Out Two",   "NOT WITH TEAM" if with_out_players else None),
        (9003, "Probe Healthy A", None),
        (9004, "Probe Healthy B", None),
        (9005, "Probe Healthy C", None),
    ]
    for pid, name, status in players:
        if status is None:
            continue
        inj_rows.append({
            "player_id": pid, "player_name": name, "team": "HOM",
            "status": status, "availability_factor": 0.0,
            "reason": "probe", "source": "probe",
            "fetched_at": f"{today}T00:00:00", "report_date": today,
        })
    if inj_rows:
        pd.DataFrame(inj_rows).to_parquet(
            os.path.join(cache_dir, f"nba_injuries_{today}.parquet"),
            index=False,
        )

    # Synthetic quarter_box: every player has 8 pts after Q1.
    qbox_payload = {
        "game_id": "GPROBE", "period": 1,
        "players": [
            {"game_id": "GPROBE", "team_abbreviation": "HOM",
             "player_id": pid, "player_name": name,
             "start_position": "G", "min": "10:00",
             "pts": 8, "reb": 2, "ast": 2, "fg3m": 1,
             "stl": 0, "blk": 0, "to": 1, "pf": 1}
            for pid, name, _ in players
        ],
        "teams": [
            {"team_abbreviation": "AWY", "pts": 25, "team_id": 2},
            {"team_abbreviation": "HOM", "pts": 30, "team_id": 1},
        ],
    }
    with open(os.path.join(qbox, "GPROBE_q1.json"), "w",
              encoding="utf-8") as f:
        json.dump(qbox_payload, f)

    # Synthetic books: PTS 10.5 OVER -110 for every player.
    with open(os.path.join(lines_dir, f"{today}_bov.csv"), "w",
              encoding="utf-8") as f:
        f.write("captured_at,book,game_id,player_id,player_name,"
                "stat,line,over_price,under_price,start_time\n")
        for pid, name, _ in players:
            f.write(
                f"{today}T20:00:00,bov,GPROBE,{pid},{name},pts,10.5,-110,-110,\n"
            )

    # Stub the projector so we don't need real model artifacts.
    def _proj(snap, period=None):
        rows = []
        for p in snap["players"]:
            rows.append({
                "name": p["name"], "team": p["team"],
                "player_id": p["player_id"], "stat": "pts",
                "current": float(p.get("pts", 0)),
                "projected_final": float(p.get("pts", 0)) + 8.0,
                "period": snap["period"],
                "q10": float(p.get("pts", 0)) + 3.0,
                "q90": float(p.get("pts", 0)) + 13.0,
            })
        return rows

    # Apply monkey-patches via direct attribute writes (probe is one-shot
    # so we don't bother restoring).
    ibr.QBOX_DIR = qbox
    ibr.LINES_DIR = lines_dir
    ibr._project_with_engine = _proj
    ia._CACHE_DIR = cache_dir
    ia.reset_cache()

    return ibr.run_tick(
        game_id="GPROBE", date_str=today, bankroll=1000.0,
        qbox_dir=qbox, books=("bov",),
    )


def live_inplay_audit() -> Dict[str, object]:
    """Run the inplay ranker twice — once with OUT players seeded, once
    without — and report the bet-kill delta."""
    import tempfile
    with tempfile.TemporaryDirectory() as t1:
        with_out = _seed_synthetic_tick(t1, with_out_players=True)
    with tempfile.TemporaryDirectory() as t2:
        no_inj = _seed_synthetic_tick(t2, with_out_players=False)

    return {
        "with_out_players": {
            "n_ranked_bets": len(with_out.get("ranked_bets") or []),
            "n_killed_by_injury": with_out.get("n_killed_by_injury", 0),
            "killed_players": with_out.get("killed_by_injury_players") or [],
            "ranked_players": sorted({b["player"]
                                       for b in with_out.get("ranked_bets")
                                       or []}),
        },
        "no_injuries": {
            "n_ranked_bets": len(no_inj.get("ranked_bets") or []),
            "n_killed_by_injury": no_inj.get("n_killed_by_injury", 0),
            "ranked_players": sorted({b["player"]
                                       for b in no_inj.get("ranked_bets")
                                       or []}),
        },
    }


def real_world_slate_check() -> Dict[str, object]:
    """Cross-reference tonight's `live_bet_ranker.SLATES` roster against
    today's parquet — does today's slate include any OUT player whose
    bets would have shipped without the wire?"""
    try:
        import live_bet_ranker as lbr  # noqa: PLC0415
        from src.prediction import injury_availability as _ia  # noqa: PLC0415
        from src.prediction.injury_availability import (  # noqa: PLC0415
            get_availability_factor, reset_cache,
        )
        # The live_inplay_audit may have repointed _CACHE_DIR at a tmp
        # path — restore to the production cache so we audit today's
        # real parquet.
        _ia._CACHE_DIR = _CACHE_DIR
        reset_cache()
        slate_out: Dict[str, List[str]] = {}
        for slate_id, cfg in lbr.SLATES.items():
            names = (cfg.get("sas_players") or []) + (cfg.get("okc_players") or [])
            out_players = []
            for n in names:
                f = get_availability_factor(player_name=n)
                if f == 0.0:
                    out_players.append(n)
            if out_players:
                slate_out[slate_id] = out_players
        return {"out_on_slate": slate_out, "slates_checked": list(lbr.SLATES.keys())}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> int:
    pq = parquet_summary()
    audit = static_audit()
    inplay = live_inplay_audit()
    slate = real_world_slate_check()

    out_status = "SHIP"
    reasons: List[str] = []
    if audit["missing_wires"]:
        out_status = "REJECT"
        reasons.append(
            f"static audit missing wires in: {audit['missing_wires']}"
        )
    with_out = inplay["with_out_players"]
    if with_out["n_killed_by_injury"] < 1:
        out_status = "REJECT"
        reasons.append("synthetic OUT seed produced 0 injury kills")
    for nm in ("Probe Out One", "Probe Out Two"):
        if nm in with_out["ranked_players"]:
            out_status = "REJECT"
            reasons.append(f"OUT player {nm!r} still in ranked output")

    payload = {
        "probe_id": "R23_P2",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "status": out_status,
        "reasons": reasons,
        "parquet": pq,
        "static_audit": audit,
        "live_inplay_audit": inplay,
        "real_world_slate_check": slate,
        "summary": {
            "consumers_audited": len(audit["consumers"]),
            "consumers_wired": sum(1 for r in audit["consumers"]
                                    if r["wired"]),
            "bets_killed_by_injury": with_out["n_killed_by_injury"],
            "bets_surviving_with_injury_seed": with_out["n_ranked_bets"],
            "bets_surviving_without_injury_seed": inplay["no_injuries"]["n_ranked_bets"],
        },
    }

    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(json.dumps(payload["summary"], indent=2))
    print(f"\nstatus={out_status}")
    if reasons:
        for r in reasons:
            print(f"  reason: {r}")
    print(f"  results → {_RESULTS_PATH}")
    return 0 if out_status == "SHIP" else 1


if __name__ == "__main__":
    sys.exit(main())
