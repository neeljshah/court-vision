"""LANE A -- fail-closed resolvers over the edge_engine fact stores (injury +
news JSONL, scripts/platformkit/edge_engine/facts_store.py). Mirrors
resolver_registry.py's envelope contract exactly:
    {status: "ok"|"refused"|"not_supported"|"no_data", category, sport,
     source_artifact, as_of, ...category-specific fields}

Every field returned is read verbatim off the fact-store rows -- never
recomputed or inferred here (that is injury_facts.py / news_facts.py's job).
Fails closed three ways, in order:
  1. store file absent for this sport (edge_engine daemon hasn't run in this
     clone / a fresh clone where data/ is gitignored)   -> status "no_data"
  2. entity (team/player) not supplied, or matches zero rows (exact then
     fuzzy)                                              -> status "no_data"
  3. newest matched row's timestamp is older than the staleness bound
     (default 7d -- injuries and news both churn weekly) -> status "refused"

Run: python -m scripts.platformkit.answers.edge_facts_resolver injury_report --sport nba --player "Trae Young"
     python -m scripts.platformkit.answers.edge_facts_resolver news_context --sport nba --team "Atlanta Hawks"
"""
from __future__ import annotations

import argparse
import difflib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # package import
    from scripts.platformkit.edge_engine import facts_store as FS  # type: ignore
except ImportError:  # direct-script / per-file-test fallback
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.edge_engine import facts_store as FS  # type: ignore
from scripts.platformkit.odds_provider.team_resolver import canonical as _team_canonical

STALE_DAYS = 7.0  # both injury and news facts churn weekly -- same bound for both categories
_FUZZY_CUTOFF = 0.6
_REPO = Path(__file__).resolve().parents[3]


def _rel(p) -> str:
    """Repo-relative POSIX string for the envelope -- never leak a box-local
    absolute path (C:/Users/...) into source_artifact. Falls back to the raw
    string only for paths outside the repo (e.g. a test tmp_path)."""
    p = Path(p)
    try:
        return str(p.resolve().relative_to(_REPO)).replace("\\", "/")
    except ValueError:
        return str(p)


def _parse_dt(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _row_ts(row: dict) -> str | None:
    """Injury rows carry fetched_at; news rows only carry published (no
    per-fetch timestamp is recorded) -- same fallback facts_store.store_summary
    already uses."""
    return row.get("fetched_at") or row.get("published")


def _canon_match(entity: str, candidates: list[str], sport: str | None) -> str | None:
    """Nickname->full-name bridge for TEAM fields only (never player names):
    fact-store rows carry the full display name ("Los Angeles Dodgers",
    "Boston Celtics") but real queries name the bare nickname ("Dodgers",
    "Celtics") -- difflib's whole-string ratio scores that pair too low
    (length mismatch) to ever fuzzy-match. Reuses the SAME cross-repo
    canonicalizer schedule_context_resolver already relies on for this exact
    problem (scripts.platformkit.odds_provider.team_resolver.canonical) --
    no new alias table. sport=None (player-field calls) skips this step."""
    if not sport:
        return None
    target = _team_canonical(sport, entity)
    if not target or target.endswith(":"):
        return None
    for c in candidates:
        if _team_canonical(sport, c) == target:
            return c
    return None


def _match_rows(rows: list[dict], field: str, entity: str, sport: str | None = None) -> tuple[list[dict], str | None]:
    """Exact (case-insensitive) match first; canonical nickname match (team
    fields only, via `sport`); fuzzy fallback over the distinct values
    actually present. Returns (matched_rows, matched_value_or_None)."""
    needle = entity.strip().lower()
    exact = [r for r in rows if str(r.get(field, "")).strip().lower() == needle]
    if exact:
        return exact, entity
    candidates = sorted({str(r.get(field)) for r in rows if r.get(field)})
    if field == "team":
        canon = _canon_match(entity, candidates, sport)
        if canon is not None:
            return [r for r in rows if str(r.get(field)) == canon], canon
    close = difflib.get_close_matches(entity, candidates, n=1, cutoff=_FUZZY_CUTOFF)
    if not close:
        return [], None
    matched_value = close[0]
    return [r for r in rows if str(r.get(field)) == matched_value], matched_value


def _match_list_field(rows: list[dict], field: str, entity: str, sport: str | None = None) -> tuple[list[dict], str | None]:
    """Same as _match_rows but `field` holds a list per row (news teams/players)."""
    needle = entity.strip().lower()
    exact = [r for r in rows if any(str(v).strip().lower() == needle for v in r.get(field) or [])]
    if exact:
        return exact, entity
    candidates = sorted({str(v) for r in rows for v in (r.get(field) or [])})
    if field == "teams":
        canon = _canon_match(entity, candidates, sport)
        if canon is not None:
            return [r for r in rows if canon in (r.get(field) or [])], canon
    close = difflib.get_close_matches(entity, candidates, n=1, cutoff=_FUZZY_CUTOFF)
    if not close:
        return [], None
    matched_value = close[0]
    return [r for r in rows if matched_value in (r.get(field) or [])], matched_value


def _gate_and_sort(rows: list[dict], category: str, sport: str, path: Path):
    """Newest-first sort + staleness gate on the newest matched row. Returns
    (failure_envelope, None) or (None, (sorted_rows, as_of_iso))."""
    dated = [(r, _parse_dt(_row_ts(r))) for r in rows]
    dated = [(r, dt) for r, dt in dated if dt is not None]
    if not dated:
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": _rel(path),
                "note": "matched rows carry no parseable timestamp"}, None
    dated.sort(key=lambda rd: rd[1], reverse=True)
    newest_dt = dated[0][1]
    age_days = (datetime.now(timezone.utc) - newest_dt).total_seconds() / 86400.0
    if age_days > STALE_DAYS:
        return {"status": "refused", "category": category, "sport": sport, "source_artifact": _rel(path),
                "as_of": newest_dt.isoformat(),
                "note": f"newest matched row is {age_days:.1f}d old, exceeds the {STALE_DAYS:.0f}d staleness bound"}, None
    return None, ([r for r, _ in dated], newest_dt.isoformat())


def injury_report(sport: str, team: str | None = None, player: str | None = None) -> dict:
    """edge_facts.injury_report -- latest injury-status rows for a team or
    player, newest-first, off data/cache/edge_engine/injury_facts_<sport>.jsonl."""
    category = "edge_facts_injury_report"
    path = FS.path_for("injury", sport)
    if not path.is_file():
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": _rel(path),
                "note": "injury facts store not built in this clone"}
    if not team and not player:
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": _rel(path),
                "note": "supply team or player"}
    rows = FS.read_rows(path)
    matched, matched_value = rows, None
    if player:
        matched, matched_value = _match_rows(matched, "player_name", player)
    if team and matched:
        matched, matched_value = _match_rows(matched, "team", team, sport=sport)
    if not matched:
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": _rel(path),
                "note": f"no injury row matched team={team!r} player={player!r}"}
    fail, ctx = _gate_and_sort(matched, category, sport, path)
    if fail:
        return fail
    sorted_rows, as_of = ctx
    fields = ("player_name", "team", "status", "detail", "report_date", "source", "source_url", "fetched_at")
    return {"status": "ok", "category": category, "sport": sport, "source_artifact": _rel(path), "as_of": as_of,
            "team": team, "player": player, "matched_entity": matched_value, "n": len(sorted_rows),
            "rows": [{k: r.get(k) for k in fields} for r in sorted_rows[:50]]}


def news_context(sport: str, team: str | None = None, player: str | None = None) -> dict:
    """edge_facts.news_context -- news items mentioning a team or player,
    newest-first, off data/cache/edge_engine/news_facts_<sport>.jsonl."""
    category = "edge_facts_news_context"
    path = FS.path_for("news", sport)
    if not path.is_file():
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": _rel(path),
                "note": "news facts store not built in this clone"}
    if not team and not player:
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": _rel(path),
                "note": "supply team or player"}
    rows = FS.read_rows(path)
    matched, matched_value = rows, None
    if player:
        matched, matched_value = _match_list_field(matched, "players", player)
    if team and matched:
        matched, matched_value = _match_list_field(matched, "teams", team, sport=sport)
    if not matched:
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": _rel(path),
                "note": f"no news row matched team={team!r} player={player!r}"}
    fail, ctx = _gate_and_sort(matched, category, sport, path)
    if fail:
        return fail
    sorted_rows, as_of = ctx
    fields = ("headline", "url", "published", "source", "categories", "teams", "players")
    return {"status": "ok", "category": category, "sport": sport, "source_artifact": _rel(path), "as_of": as_of,
            "team": team, "player": player, "matched_entity": matched_value, "n": len(sorted_rows),
            "rows": [{k: r.get(k) for k in fields} for r in sorted_rows[:50]]}


def resolve(category: str, sport: str, team: str | None = None, player: str | None = None) -> dict:
    """Dispatch by category name -- 'injury_report' or 'news_context'."""
    fn = {"injury_report": injury_report, "news_context": news_context}.get(category)
    if fn is None:
        return {"status": "not_supported", "category": category, "sport": sport,
                "note": "category must be injury_report or news_context"}
    return fn(sport, team=team, player=player)


def main(argv=None):
    p = argparse.ArgumentParser(description="Query the edge_engine fact-store resolvers directly.")
    p.add_argument("category", choices=["injury_report", "news_context"])
    p.add_argument("--sport", default="nba")
    p.add_argument("--team")
    p.add_argument("--player")
    a = p.parse_args(argv)
    print(json.dumps(resolve(a.category, a.sport, team=a.team, player=a.player), indent=2, default=str))


if __name__ == "__main__":
    main()
