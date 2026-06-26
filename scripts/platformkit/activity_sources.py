"""activity_sources.py -- READ-ONLY loaders for the LIVE-system activity snapshot.

Collects what the AI is DOING RIGHT NOW from the on-disk stores under
``data/frontend/`` (+ the read-only signal registry under ``data/registry/``) into
ONE person-free, units-only dict that ``brain_activity.py`` renders into the brain's
``_Whats_Happening`` hub + per-sport ``_Activity`` notes.

PERSON-FREE: only COUNTS, sport keys, calibration metrics (Brier/ECE/CLV%), verdict
labels, and service names ever leave here -- never a player/team name or a matchup.
UNITS-ONLY: no $ figure is read or emitted; CLV is the honest yardstick, not edge.
DEFENSIVE: every store is optional; a missing/corrupt file degrades to an honest
empty section (never raises). Idempotent: stamps come from the stores' own
timestamps, not the wall clock, so an unchanged tree renders byte-identical.

This module NEVER writes anything (it is a pure read). The signal registry under
``data/registry/`` is read-only here; it is never modified.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from scripts.platformkit.clv_ledger_dedup import count_open_unsettled, open_unsettled_rows

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]

# Live sport-key -> vault sport folder. soccer_intl (World Cup) + soccer (club) both
# roll up under the "Soccer" brain folder; the others map one-to-one.
_SPORT_FOLDER = {"nba": "NBA", "mlb": "MLB", "soccer_intl": "Soccer",
                 "soccer": "Soccer", "tennis": "Tennis"}


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- any read/parse error -> honest absence
        return None


def _read_jsonl(path: Path, cap: int = 200000) -> List[dict]:
    out: List[dict] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i >= cap:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    except OSError:
        return out
    return out


def _services(fe: Path) -> Dict:
    rep = _read_json(fe / "ops" / "supervisor_status.json")
    if not rep:
        return {"present": False, "procs": []}
    procs = rep.get("procs", []) or []
    rows = [{"name": str(p.get("name", "?")), "ready": bool(p.get("ready")),
             "state": str(p.get("state", "?")), "restarts": int(p.get("restarts", 0) or 0)}
            for p in procs]
    return {
        "present": True,
        "profile": rep.get("profile"),
        "updated_at": rep.get("updated_at"),
        "all_ready": bool(rep.get("all_ready")),
        "n_total": len(rows),
        "n_ready": sum(1 for r in rows if r["ready"]),
        "n_failed": sum(1 for r in rows if r["state"].upper() == "FAILED"),
        "restarts_total": sum(r["restarts"] for r in rows),
        "procs": sorted(rows, key=lambda r: r["name"]),
    }


def _predicting(fe: Path) -> Dict:
    auto = _read_json(fe / "ops" / "autonomy_status.json") or {}
    hb = _read_json(fe / "ingame" / "_heartbeat.json") or {}
    hw = auto.get("high_water", {}) or {}
    per_sport = {}
    for sp, rec in hw.items():
        if not isinstance(rec, dict):
            continue
        per_sport[sp] = {"last_decision": rec.get("last_decision"),
                         "n_seen": rec.get("n_seen")}
    live = hb.get("per_sport", {}) or {}
    per_live = {sp: int((v or {}).get("n_live", 0) if isinstance(v, dict) else 0)
                for sp, v in live.items()}
    return {
        "present": bool(auto) or bool(hb),
        "overall": auto.get("overall"),
        "idle_reason": auto.get("idle_reason"),
        "ratchet_state": (auto.get("ratchet", {}) or {}).get("state"),
        "n_ships": (auto.get("ratchet", {}) or {}).get("n_ships"),
        "per_sport": per_sport,
        "n_live_now": int(hb.get("n_live", 0) or 0),
        "live_by_sport": {sp: n for sp, n in per_live.items() if n},
        "hb_as_of": hb.get("as_of"),
    }


def _calibration(fe: Path) -> Dict:
    g = _read_json(fe / "grade_summary.json")
    if not g:
        return {"present": False, "by_sport": {}}
    keep = ("n_settled", "n_clv", "mean_clv_pct", "pct_beat_close",
            "n_true_close", "n_proxy_close", "flat_unit_wins", "flat_unit_losses")
    by_sport = {}
    for sp, rec in (g.get("by_sport", {}) or {}).items():
        if isinstance(rec, dict):
            by_sport[sp] = {k: rec.get(k) for k in keep}
    return {"present": True, "as_of": g.get("as_of"),
            **{k: g.get(k) for k in keep}, "by_sport": by_sport}


def _latest_verdicts(rows: List[dict]) -> Dict[str, dict]:
    """Most-recent verdict record per sport (rows are append-only, ts-ordered)."""
    out: Dict[str, dict] = {}
    for r in rows:
        sp = r.get("sport")
        if sp:
            out[sp] = r  # later rows overwrite -> last (newest) wins
    return {sp: {"verdict": r.get("verdict"), "reason": r.get("reason"),
                 "n_settled": r.get("n_settled"), "ts": r.get("ts")}
            for sp, r in out.items()}


def _improvement(fe: Path) -> Dict:
    game = _latest_verdicts(_read_jsonl(fe / "improve_ledger.jsonl"))
    prop = _latest_verdicts(_read_jsonl(fe / "prop_improve_ledger.jsonl"))
    meta = _read_json(fe / "prop_history_meta.json") or {}
    groups = []
    for grp in meta.get("groups", []) or []:
        if isinstance(grp, dict):
            groups.append({"sport": grp.get("sport"), "stat": grp.get("stat"),
                           "n_folds": grp.get("n_folds"),
                           "replicated_verdict": grp.get("replicated_verdict"),
                           "median_delta_brier": grp.get("median_delta_brier"),
                           "any_planted_null_leak": grp.get("any_planted_null_leak")})
    return {"game_winprob": game, "props": prop,
            "history_meta": {"present": bool(meta),
                             "n_history_folds": meta.get("n_history_folds"),
                             "min_replication": meta.get("min_replication"),
                             "groups": groups}}


def _paper(fe: Path) -> Dict:
    rows = _read_jsonl(fe / "clv_ledger.jsonl")
    if not rows:
        return {"present": False, "n_total": 0, "by_sport": {}}
    chan = Counter()
    mkt = Counter()
    status = Counter()
    per_sport: Dict[str, Counter] = {}
    for r in rows:
        sp = str(r.get("sport") or "NOT_SET")
        c = str(r.get("channel") or "NOT_SET")
        m = str(r.get("market_type") or "NOT_SET")
        st = str(r.get("status") or "NOT_SET")
        chan[c] += 1
        mkt[m] += 1
        status[st] += 1
        d = per_sport.setdefault(sp, Counter())
        d["total"] += 1
        d[f"status:{st}"] += 1
        d[f"channel:{c}"] += 1
        d[f"market:{m}"] += 1
    # Overwrite per-sport "status:open" with twin-aware counts so it matches the
    # headline n_open.  Total, settled, channel, and market counts stay unchanged.
    truly_open = open_unsettled_rows(rows)
    open_per_sport: Dict[str, int] = {}
    for r in truly_open:
        sp = str(r.get("sport") or "NOT_SET")
        open_per_sport[sp] = open_per_sport.get(sp, 0) + 1
    for sp, d in per_sport.items():
        d["status:open"] = open_per_sport.get(sp, 0)
    return {
        "present": True,
        "n_total": len(rows),
        "n_open": count_open_unsettled(rows),
        "n_settled": status.get("settled", 0),
        "n_ingame": chan.get("paper_ingame", 0),
        "by_channel": dict(chan),
        "by_market": dict(mkt),
        "by_sport": {sp: dict(d) for sp, d in per_sport.items()},
    }


def _signals(repo_root: Path) -> Dict:
    """Counts ONLY from the read-only signal registry parquets (never written)."""
    reg = repo_root / "data" / "registry"
    out: Dict = {"present": False}
    try:
        import pandas as pd  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return out
    rp = reg / "signal_registry.parquet"
    lp = reg / "signal_lab_registry.parquet"
    try:
        if rp.exists():
            df = pd.read_parquet(rp)
            out["present"] = True
            out["n_signals"] = int(len(df))
            if "status" in df.columns:
                out["by_status"] = {str(k): int(v)
                                    for k, v in df["status"].value_counts().items()}
            if "ev_tier" in df.columns:
                out["by_tier"] = {str(k): int(v)
                                  for k, v in df["ev_tier"].value_counts().items()}
    except Exception:  # noqa: BLE001
        pass
    try:
        if lp.exists():
            dl = pd.read_parquet(lp)
            out["present"] = True
            out["n_lab"] = int(len(dl))
            if "verdict" in dl.columns:
                out["lab_verdicts"] = {str(k): int(v)
                                       for k, v in dl["verdict"].value_counts().items()}
    except Exception:  # noqa: BLE001
        pass
    return out


def collect_activity(repo_root: Optional[Path] = None) -> Dict:
    """One READ-ONLY snapshot of the live system for the brain activity hubs.

    Returns a person-free, units-only dict; every section is honest-empty when its
    store is missing. ``machinery_ready`` is always True (the renderer runs even with
    zero live data -> honest empties). ``sport_folder_map`` maps live sport keys to
    the vault sport folder so per-sport notes aggregate correctly.
    """
    repo_root = Path(repo_root) if repo_root else _REPO_ROOT
    fe = repo_root / "data" / "frontend"
    return {
        "machinery_ready": True,
        "sport_folder_map": dict(_SPORT_FOLDER),
        "services": _services(fe),
        "predicting": _predicting(fe),
        "calibration": _calibration(fe),
        "improvement": _improvement(fe),
        "paper": _paper(fe),
        "signals": _signals(repo_root),
    }


__all__ = ["collect_activity"]
