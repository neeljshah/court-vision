"""Per-team sections: rest/schedule, injuries (+usage-redistribution
implication for an OUT top-3-FGA player), and recent news. Every function
premise-checks its own inputs and returns {"status": "ok"|"not_available", ...}
rather than raising -- callers render the not_available case as one line.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.gamebrief import sources, team_ids
from scripts.platformkit.odds_provider.team_resolver import canonical

_NA = {"status": "not_available"}


def rest_and_schedule(games_df: Optional[pd.DataFrame], home: str, away: str, date: Any) -> Dict:
    if games_df is None:
        return dict(_NA, reason="games.parquet not found")
    df = games_df
    target = pd.Timestamp(date)
    row = df[(df["date"] == target) & (df["home_team"] == home) & (df["away_team"] == away)]
    if row.empty:
        return dict(_NA, reason="game not found for this home/away/date")
    r = row.iloc[0]
    return {
        "status": "ok",
        "rest_days_home": None if pd.isna(r["rest_days_home"]) else float(r["rest_days_home"]),
        "rest_days_away": None if pd.isna(r["rest_days_away"]) else float(r["rest_days_away"]),
        "home_b2b": bool(r["home_b2b"]) if pd.notna(r["home_b2b"]) else None,
        "away_b2b": bool(r["away_b2b"]) if pd.notna(r["away_b2b"]) else None,
    }


def top3_fga(box_df: Optional[pd.DataFrame], team: str, asof_date: Any) -> List[Dict]:
    """Top-3 season-to-date FGA players for `team`, using only games strictly
    before `asof_date` (leak-free: pregame state, not the game itself)."""
    if box_df is None:
        return []
    d = box_df[box_df["team"] == team].copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d[d["date"] < pd.Timestamp(asof_date)]
    if d.empty:
        return []
    agg = (
        d.groupby(["player_id", "player_name"])["fga"]
        .sum()
        .reset_index()
        .sort_values("fga", ascending=False)
        .head(3)
    )
    return [
        {"player_id": int(r.player_id), "player_name": r.player_name, "fga_season_to_date": float(r.fga)}
        for r in agg.itertuples()
    ]


def _usage_implication(team: str, out_player_id: int, out_player_name: str) -> Optional[str]:
    """'X out -> Y historically +Z FGA share, eFG delta', from the direct
    with/without minutes split -- no re-derivation of the store's own delta
    column, just the with/without values it already carries."""
    ur = sources.usage_redistribution()
    tid = team_ids.team_id_for(team)
    if ur is None or tid is None:
        return None
    rows = ur[(ur["team_id"] == tid) & (ur["teammate_id"] == out_player_id) & (ur["player_id"] != out_player_id)]
    if rows.empty:
        return None
    rows = rows.assign(share_gain=rows["fga_share_without"] - rows["fga_share_with"],
                        efg_gain=rows["efg_without"] - rows["efg_with"])
    top = rows.sort_values("share_gain", ascending=False).head(2)
    parts = [
        f"{r.player_name} {r.share_gain:+.1%} FGA share, eFG {r.efg_gain:+.3f}"
        for r in top.itertuples()
    ]
    return f"{out_player_name} out -> " + "; ".join(parts)


def injury_section(team: str, asof_date: Any, top3: List[Dict]) -> Dict:
    rows = sources.injury_rows()
    if not rows:
        return dict(_NA, reason="injury_facts_nba.jsonl empty or absent")
    full = team_ids.fullname_for(team)
    cutoff = pd.Timestamp(asof_date)
    top3_ids = {p["player_id"] for p in top3}
    top3_names = {p["player_id"]: p["player_name"] for p in top3}

    latest: Dict[str, Dict] = {}
    for r in rows:
        if canonical("nba", r.get("team", "")) != canonical("nba", full or team):
            continue
        rd = r.get("report_date")
        try:
            rd_ts = pd.Timestamp(rd)
        except Exception:  # noqa: BLE001
            continue
        if rd_ts > cutoff:
            continue  # do not use a future-dated report for a past game (leak-free)
        name = r.get("player_name", "")
        if name not in latest or rd_ts > pd.Timestamp(latest[name]["report_date"]):
            latest[name] = r

    if not latest:
        return dict(_NA, reason=f"no injury report on file as of {asof_date} for {team}")

    reports = []
    for name, r in sorted(latest.items()):
        pid = next((p["player_id"] for p in top3 if p["player_name"].lower() == name.lower()), None)
        usage_note = None
        if pid is not None:
            usage_note = _usage_implication(team, pid, name)
        reports.append({
            "player": name, "status": r.get("status"), "detail": r.get("detail"),
            "report_date": r.get("report_date"), "is_top3_fga": pid is not None,
            "usage_redistribution_note": usage_note,
        })
    return {"status": "ok", "reports": reports}


def news_section(team: str, asof_date: Any, limit: int = 3) -> Dict:
    rows = sources.news_rows()
    if not rows:
        return dict(_NA, reason="news_facts_nba.jsonl empty or absent")
    full = team_ids.fullname_for(team)
    cutoff = pd.Timestamp(asof_date)
    hits = []
    for r in rows:
        teams = r.get("teams") or []
        if not any(canonical("nba", t) == canonical("nba", full or team) for t in teams):
            continue
        try:
            pub = pd.Timestamp(r.get("published"))
        except Exception:  # noqa: BLE001
            continue
        pub_naive = pub.tz_localize(None) if pub.tzinfo else pub
        if pub_naive > cutoff:
            continue
        hits.append((pub, r.get("headline", "")))
    if not hits:
        return dict(_NA, reason=f"no news on file as of {asof_date} for {team}")
    hits.sort(key=lambda t: t[0], reverse=True)
    return {"status": "ok", "headlines": [h for _, h in hits[:limit]]}
