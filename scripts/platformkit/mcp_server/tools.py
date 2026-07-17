"""CourtVision MCP tool table + handlers.

Every handler LAZY-imports its backing module inside the function body so the
resident server process stays light (no pandas at import time). Each returns
the standard fail-closed envelope dict:

    {status: ok|refused|not_supported|no_data|ambiguous,
     category, sport, source_artifact, as_of, ...category-specific fields}

Refusal semantics (mirrors docs/AI_CONSUMER_CONTRACT.md) -- the CALLER must
honor them, never soften into a hedge:
  ok            -> use the numbers verbatim; cite source_artifact + as_of.
  no_data       -> the backing artifact is absent/empty; say NO_DATA, do NOT
                   fill the gap from model memory.
  not_supported -> no resolver registered for this question type; stop.
  refused       -> edge/ROI/retracted-number language, or a stale receipt;
                   refuse, cite .claude/rules/no-edge-claims.md.
  ambiguous     -> multiple candidates; disambiguate before answering.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

_SPORT = {"type": "string", "description": "nba | mlb | soccer | tennis (default nba)"}


def _ask(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.platformkit.answers import resolver_registry as r
    kw = {k: v for k, v in args.items() if k not in ("query", "sport", "category")}
    envelope = r.resolve(args["query"], args.get("sport", "nba"), args.get("category"), **kw)
    # ponytail: some resolver branches (e.g. concept_rating no_data) omit
    # source_artifact even though the category's registry entry names one --
    # backfill it here so every envelope is equally self-explaining, without
    # touching resolver_registry.py's per-category return statements.
    if "source_artifact" not in envelope:
        meta = r.RESOLVERS.get(envelope.get("category"), {})
        if meta.get("source_artifact"):
            envelope["source_artifact"] = meta["source_artifact"]
    return envelope


def _scouting_report(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.platformkit.intel_query.compose_scout import compose_scout
    return compose_scout(args["sport"], args["player"],
                         kind=args.get("kind", "player"), top_n=args.get("top_n", 8))


def _comparables(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.platformkit.intel_query.compose_comparables import compose_comparables
    return compose_comparables(args["sport"], args["player"], k=args.get("k", 5))


def _matchup_preview(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.platformkit.intel_query.compose_matchup import compose_matchup
    return compose_matchup(args["sport"], args["home"], args["away"], date=args.get("date"))


def _win_probability(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.platformkit.answers import winprob_dispatch as w
    return w.dispatch(args["sport"], args["home"], args["away"],
                      ingame_state=args.get("ingame_state"))


def _injury_report(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.platformkit.answers import edge_facts_resolver as e
    # one arg: a team OR a player name -- pass to both, resolver filters verbatim.
    tp = args["team_or_player"]
    return e.injury_report(args["sport"], team=tp, player=args.get("player"))


_RECEIPTS: Dict[str, str] = {
    "attribution": "attribution",
    "claim_survival": "claim_survival",
    "verification": "verification",
    "contradictions": "contradictions",
    "system_map": "system_map",
}


def _analytics_receipts(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.platformkit.analytics_verify import answers as a
    kind = args["kind"]
    fn = getattr(a, _RECEIPTS.get(kind, ""), None)
    if fn is None:
        return {"status": "not_supported", "category": "analytics_receipts",
                "note": "kind must be one of %s" % sorted(_RECEIPTS)}
    return fn(args.get("sport", "all"))


def _run_burst(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.platformkit import burst_run
    steps = args.get("steps")
    if isinstance(steps, str):
        steps = [s.strip() for s in steps.split(",") if s.strip()]
    report = burst_run.run_burst(steps=steps, skip_slow=args.get("skip_slow", False))
    # ponytail: burst_run.py's own report shape has no top-level status (other
    # callers/tests pin that shape) -- add it here at the MCP boundary so this
    # is the only one of 9 tools that doesn't break the fail-closed contract.
    report.setdefault("status", "aborted" if report.get("aborted_reason") else "ok")
    return report


def _system_health(args: Dict[str, Any]) -> Dict[str, Any]:
    import json
    from pathlib import Path
    repo = Path(__file__).resolve().parents[3]

    def _load(rel: str) -> Any:
        p = repo / rel
        if not p.exists():
            return {"status": "no_data", "source_artifact": rel, "note": "absent"}
        try:
            return json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 -- report, never crash the server
            return {"status": "no_data", "source_artifact": rel, "note": str(exc)}

    burst = _load("data/cache/analytics_verify/burst_report.json")
    fresh = _load("data/frontend/ops/freshness_sla.json")
    live = _load(".bot_state/live_status.json")
    fleet_on = not (isinstance(live, dict) and live.get("stop_requested", True))
    return {
        "status": "ok",
        "category": "system_health",
        "fleet_on": fleet_on,
        "fleet_phase": live.get("phase") if isinstance(live, dict) else None,
        "burst_report": burst,
        "freshness": {k: fresh.get(k) for k in ("overall", "n_red", "n_daemons", "generated_at")}
        if isinstance(fresh, dict) and "overall" in fresh else fresh,
        "honest_note": "cheap reads only; no live probe. UNITS only, no $/edge.",
    }


# name -> (description, inputSchema, handler)
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "ask",
        "description": (
            "UNIVERSAL FRONT DOOR. Route any natural-language sports question through the "
            "fail-closed answer engine (resolver_registry.resolve). Covers 20 registered "
            "categories: player_stat, rating_attribute, concept_rating, prediction_winprob, "
            "calibration_number, historical_result, mechanism_effect, ranking, injury_report, "
            "news_context, schedule_context, scouting_report, comparables, matchup_preview, and "
            "the analytics receipts. Returns the standard envelope; status not_supported means "
            "no resolver is registered (stop, do not improvise), no_data means the artifact is "
            "absent (say NO_DATA), refused means edge/ROI language (refuse). Quote numbers "
            "verbatim and cite source_artifact + as_of. NEVER answer from model memory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "the natural-language question"},
                "sport": _SPORT,
                "category": {"type": "string", "description": "optional: force a category, bypassing classify()"},
            },
            "required": ["query"],
        },
        "handler": _ask,
    },
    {
        "name": "scouting_report",
        "description": (
            "Multi-axis descriptive scouting VECTOR for a player: per-concept rating+percentile, "
            "shooting facet, raw attributes -- never collapsed to one number. Returns no_data if "
            "the player resolves on zero axes. Descriptive only, no prediction."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sport": _SPORT, "player": {"type": "string"},
                           "top_n": {"type": "integer", "description": "axes to return (default 8)"}},
            "required": ["sport", "player"],
        },
        "handler": _scouting_report,
    },
    {
        "name": "comparables",
        "description": (
            "K nearest players to the given player by RMS-normalized Euclidean distance over "
            "shared attribute percentiles. Refused below the shared-attribute floor. Descriptive."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sport": _SPORT, "player": {"type": "string"},
                           "k": {"type": "integer", "description": "neighbors to return (default 5)"}},
            "required": ["sport", "player"],
        },
        "handler": _comparables,
    },
    {
        "name": "matchup_preview",
        "description": (
            "Descriptive matchup preview: fan-out envelope wrapping win_prob, both team profiles, "
            "style_matchup, both injury reports, and both schedule_context sub-blocks verbatim. "
            "Overall status stays ok even when individual blocks are no_data -- blocks_ok / "
            "blocks_absent name which landed. Not a betting recommendation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sport": _SPORT, "home": {"type": "string"}, "away": {"type": "string"},
                           "date": {"type": "string", "description": "optional YYYY-MM-DD"}},
            "required": ["sport", "home", "away"],
        },
        "handler": _matchup_preview,
    },
    {
        "name": "win_probability",
        "description": (
            "Calibrated pre-game (or in-game) win probability, quoted verbatim off predict_matchup "
            "-- authors no new number. Pass ingame_state for a live re-priced number, but it must "
            "be COMPLETE for the sport or it is silently ignored and pregame is returned instead "
            "(same p_home_win as omitting it -- check response 'ingame' vs 'ingame_note' to tell "
            "which happened). Required keys per sport, ALL must be present: "
            "nba/wnba/soccer = elapsed, home_score, away_score; "
            "mlb = inning, half ('top'|'bottom'), home_score, away_score; "
            "tennis = sets_home, sets_away (optionally games_home + games_away, surface). "
            "This is a CALIBRATED probability, NOT a dollar edge or beat-the-market claim."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sport": _SPORT, "home": {"type": "string"}, "away": {"type": "string"},
                           "ingame_state": {"type": "object",
                                            "description": "optional live state; see tool description for the exact required-key set per sport -- an incomplete state is silently dropped, not rejected"}},
            "required": ["sport", "home", "away"],
        },
        "handler": _win_probability,
    },
    {
        "name": "injury_report",
        "description": (
            "Newest-first injury-status rows for a team or player, verbatim off the fact store, "
            "with a 7-day staleness gate. Returns no_data when the fact store has no fresh rows."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sport": _SPORT,
                           "team_or_player": {"type": "string", "description": "a team name or a player name"}},
            "required": ["sport", "team_or_player"],
        },
        "handler": _injury_report,
    },
    {
        "name": "analytics_receipts",
        "description": (
            "The verified-analytics receipts. kind selects the ledger view: attribution "
            "(which card produced which claim), claim_survival (how many claims survive "
            "re-grading), verification (independent-corpus re-checks), contradictions (claims "
            "that disagree -- can be a LARGE payload, the full conflict dump, no paging), "
            "system_map (how the pieces connect). Fail-closed: absent artifact "
            "-> no_data; a claim missing edge_claimed:false -> refused; a receipt staler than "
            "48h -> refused. Cite source_artifact + as_of."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string",
                         "enum": ["attribution", "claim_survival", "verification", "contradictions", "system_map"]},
                "sport": {"type": "string", "description": "sport or 'all' (default all)"},
            },
            "required": ["kind"],
        },
        "handler": _analytics_receipts,
    },
    {
        "name": "run_burst",
        "description": (
            "EXECUTES A MAINTENANCE BURST -- TAKES MINUTES, hits the network, writes to disk. Not "
            "a query. Runs the one-shot burst in a single RSS-guarded process and returns the "
            "report: {status: ok|aborted, started, steps: [{name, status, secs, rss_mb_after}], "
            "edge_claimed, honest_note}. Steps, tagged by cost: line_snapshot (network), "
            "settle_sweep (network), feed_health (network) are SLOW; pnl_bestbets, "
            "analytics_verify, freshness_sla are cheap/local-only. skip_slow=true runs only the "
            "cheap three. Pass steps to run a specific subset instead. For a read that touches "
            "nothing (no network, no disk write), use system_health -- but note it only replays "
            "the LAST run_burst report, it does not refresh feed_health itself."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "steps": {"type": "string",
                          "description": "optional comma list: line_snapshot,settle_sweep,pnl_bestbets,analytics_verify,feed_health,freshness_sla (first three are network/slow)"},
                "skip_slow": {"type": "boolean", "description": "run only the cheap local-only steps (pnl_bestbets, analytics_verify, freshness_sla)"},
            },
        },
        "handler": _run_burst,
    },
    {
        "name": "system_health",
        "description": (
            "Cheap READ-ONLY status: last burst_report, freshness-SLA summary, and fleet on/off "
            "state (fleet_on=false is the by-design resident-server default). No network, no "
            "compute -- reads cached JSON only. UNITS only, no $/edge."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "handler": _system_health,
    },
]


def handler_for(name: str) -> Callable[[Dict[str, Any]], Dict[str, Any]] | None:
    for t in TOOLS:
        if t["name"] == name:
            return t["handler"]
    return None


def tool_specs() -> List[Dict[str, Any]]:
    """The tools/list payload -- name, description, inputSchema (no handler)."""
    return [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in TOOLS]
