"""compose_matchup(sport, home, away, date=None) -> descriptive MATCHUP PREVIEW.

Assembles independently fail-closed blocks from already-shipped resolvers --
this module authors NO new predictive or descriptive number, it only quotes
each sub-resolver's own envelope verbatim under a named block:

  win_prob              -- answers.winprob_dispatch.dispatch() (subprocess over
                            predict_matchup.py, quoted verbatim)
  home_profile/away_profile -- team attribute-percentile summary read off
                            data/cache/profiles/<sport>_team_profiles.parquet
                            via profiles.ask's own loader/matcher (read-only reuse)
  style_matchup          -- VERIFIED sport-level style-pairing claim (soccer
                            style_matchup / tennis serve_return_matchup / NBA
                            lineup synergy+spacing families) via
                            intel_query.ask.load_verified_claims(). These
                            claims key on abstract style-pairing categories
                            (e.g. "High_vs_Low"), not on specific team/player
                            identity, so this block cites the family's own
                            ranking rows rather than filtering to home/away
                            (no team/player -> style-category resolver is
                            wired anywhere in this platform yet -- said so
                            honestly in the block's note).
  home_injury_report/away_injury_report -- answers.edge_facts_resolver.injury_report()
  home_schedule_context/away_schedule_context -- answers.schedule_context_resolver.resolve()

Each block is a full standard envelope in its own right (status/category/
sport/source_artifact/as_of/...). A block's own no_data/refused/not_supported
NEVER fails the overall preview -- the assembly always returns status "ok"
if it ran at all; blocks_ok / blocks_absent name which sub-answers actually
landed. This mirrors resolver_registry.py's contract and ask.py's honest-
UNANSWERABLE pattern, just fanned out over N independent sources instead of one.

CLI:
    python -m scripts.platformkit.intel_query.compose_matchup mlb NYY BOS
    python -m scripts.platformkit.intel_query.compose_matchup nba LAL BOS --date 2025-11-01
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from scripts.platformkit.answers.edge_facts_resolver import injury_report
from scripts.platformkit.answers.schedule_context_resolver import resolve as schedule_resolve
from scripts.platformkit.answers.winprob_dispatch import dispatch as winprob_dispatch
from scripts.platformkit.intel_query.ask import load_verified_claims, pairs_for_claim_stores
from scripts.platformkit.profiles import ask as _profiles_ask

CATEGORY = "matchup_preview"
SOURCE_ARTIFACT = "scripts/platformkit/intel_query/compose_matchup.py"

# NBA lineup families key on team_id + lineup_key (no team-name filter wired
# here -- see module docstring); soccer/tennis families key on abstract
# pairing_key style categories only. Sport not listed here -> not_supported.
_STYLE_FAMILY_PREFIXES: dict[str, tuple[str, ...]] = {
    "soccer": ("soccer_style_matchup",),
    "tennis": ("tennis_serve_return_matchup",),
    "nba": ("nba_lineup_synergy", "nba_lineup_spacing"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(stamp: str) -> datetime | None:
    """A block as_of ranges from a bare "2026-07-26" to a full offset stamp --
    compare them as datetimes, never as strings (S71/F4)."""
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _mtime_iso(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()


def _team_profile_block(sport: str, team: str, top_n: int = 10) -> dict[str, Any]:
    """Team attribute-percentile summary -- reuses profiles.ask's own loader
    (load_profiles) and fuzzy entity matcher (_match_entities), never a new
    resolution path. kind == "team" only (players are out of scope here)."""
    category = "team_profile_summary"
    path = os.path.join(_profiles_ask.PROFILES_DIR, f"{sport}_team_profiles.parquet")
    as_of = _mtime_iso(path)
    if not os.path.exists(path):
        return {"status": "no_data", "category": category, "sport": sport, "team": team,
                "source_artifact": path, "note": "no team profile parquet built for this sport"}
    df = _profiles_ask.load_profiles(sport)
    df = df[df["kind"] == "team"] if not df.empty else df
    if df.empty:
        return {"status": "no_data", "category": category, "sport": sport, "team": team,
                "source_artifact": path, "as_of": as_of, "note": "team profile parquet has zero rows"}
    _best, hits = _profiles_ask._match_entities(df, _profiles_ask._norm(team).split())
    uniq = {(e, n) for e, n, _sp in hits}
    if len(uniq) != 1:
        return {"status": "no_data", "category": category, "sport": sport, "team": team,
                "source_artifact": path, "as_of": as_of,
                "note": f"team name did not resolve to exactly one entity ({len(uniq)} candidates)"}
    eid, ename, _sp = hits[0]
    sub = df[df["entity_id"] == eid]
    latest = sub.sort_values("window").groupby("attribute", as_index=False).tail(1)
    top = latest.sort_values("percentile", ascending=False).head(top_n)
    attrs = [
        {"attribute": r["attribute"], "percentile": (round(float(r["percentile"]), 1)
                                                       if r["percentile"] == r["percentile"] else None),
         "raw_value": r["raw_value"], "window": r["window"], "status": r["status"]}
        for _, r in top.iterrows()
    ]
    return {"status": "ok", "category": category, "sport": sport, "team": ename,
            "source_artifact": path, "as_of": as_of, "top_n": top_n, "attributes": attrs}


def _style_matchup_block(sport: str) -> dict[str, Any]:
    category = "style_matchup"
    prefixes = _STYLE_FAMILY_PREFIXES.get(sport, ())
    if not prefixes:
        return {"status": "not_supported", "category": category, "sport": sport,
                "note": f"no VERIFIED style-matchup claim family wired for sport {sport!r} "
                        f"-- available: {sorted(_STYLE_FAMILY_PREFIXES)}"}
    # Scope the load to just this sport's small style stores -- a bare
    # load_verified_claims() whole-loads every *.jsonl under intel_claims/
    # (nba_player_box_rate is 2.8GB / 59k VERIFIED rows), the 6.1GB-RSS
    # incident on resolve('matchup preview ...'). Each store is <prefix>_claims
    # .jsonl (mirrors compose_best/_profile + schedule_context 75a44d8c).
    stores = tuple(f"{p}_claims.jsonl" for p in prefixes)
    verified = load_verified_claims(pairs_for_claim_stores(stores))
    matched = [row for cid, row in verified.items() if cid.startswith(prefixes)]
    if not matched:
        return {"status": "no_data", "category": category, "sport": sport,
                "note": f"no VERIFIED claim currently matches claim_id prefixes {prefixes}"}
    row = max(matched, key=lambda r: r.get("computed_at", ""))
    return {"status": "ok", "category": category, "sport": sport, "claim_id": row["claim_id"],
            "metric": row.get("criteria", {}).get("metric"), "window": row.get("criteria", {}).get("window"),
            "source_artifact": row.get("_producer_source"), "as_of": row.get("computed_at"),
            "ranking": row.get("ranking", [])[:10],
            "note": "sport-level style-pairing statistics (abstract pairing_key categories), not "
                    "filtered to these two specific teams -- no team/player-to-style-category "
                    "resolver is wired in this composer"}


def compose_matchup(sport: str, home: str, away: str, date: str | None = None) -> dict[str, Any]:
    """Assemble the standard matchup-preview envelope -- see module docstring."""
    sport = sport.lower()
    blocks: dict[str, Any] = {
        "win_prob": winprob_dispatch(sport, home, away),
        "home_profile": _team_profile_block(sport, home),
        "away_profile": _team_profile_block(sport, away),
        "style_matchup": _style_matchup_block(sport),
        "home_injury_report": injury_report(sport, team=home),
        "away_injury_report": injury_report(sport, team=away),
        "home_schedule_context": schedule_resolve(sport, home, date=date),
        "away_schedule_context": schedule_resolve(sport, away, date=date),
    }
    blocks_ok = [k for k, v in blocks.items() if v.get("status") == "ok"]
    blocks_absent = [k for k in blocks if k not in blocks_ok]
    # S71/F4: the preview is only as fresh as its freshest input -- the outer
    # `as_of` is the max of the blocks' own as_of stamps, never the wall clock.
    # The call time keeps its own key (`computed_at`) instead of impersonating a
    # data date (the S38(d) pattern).
    computed_at = _now_iso()
    stamps = sorted((p, s) for v in blocks.values()
                    if isinstance(v, dict) and v.get("as_of")
                    and (p := _parse_iso(s := str(v["as_of"]))) is not None)
    return {
        "status": "ok", "category": CATEGORY, "sport": sport, "source_artifact": SOURCE_ARTIFACT,
        "as_of": stamps[-1][1] if stamps else computed_at, "computed_at": computed_at,
        "home": home, "away": away, "date": date,
        "blocks": blocks, "blocks_ok": blocks_ok, "blocks_absent": blocks_absent,
        "note": ("DESCRIPTIVE matchup preview assembled from independently fail-closed "
                 "sub-resolvers -- each block carries its own source_artifact/as_of; a block's "
                 "own no_data/refused/not_supported marks it absent without failing the overall "
                 "preview. No forecast/$ edge claim beyond win_prob's own quoted probability."),
        "edge_claimed": False,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Descriptive matchup preview over the shipped resolver fan-out.")
    ap.add_argument("sport")
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD, default today (UTC)")
    a = ap.parse_args(argv)
    result = compose_matchup(a.sport, a.home, a.away, date=a.date)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
