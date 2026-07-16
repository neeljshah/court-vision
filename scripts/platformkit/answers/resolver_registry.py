"""LANE D -- canonical resolver registry: every supported question TYPE maps
to exactly ONE resolver (source artifact + computation rule + units/rounding
+ as-of stamp). An unregistered question type returns NOT_SUPPORTED --
never improvised. This is the top of the answer-engine stack; it dispatches
to (never re-implements) the systems that already exist:

    player_stat / rating_attribute -> scripts.platformkit.profiles.ask (single
        attribute row: raw_value is the fact, rating_2k is presentation-only)
    concept_rating   -> scripts.platformkit.answers.contracts (scouting
        composite: superlative/comparison/explanation/fit)
    prediction_winprob -> scripts/platformkit/predict_matchup.py, invoked as a
        subprocess (never imported here -- contracts.py's own guard test
        proves the concept engine stays decoupled from forecast engines, and
        this module keeps the same separation)
    calibration_number -> the pinned scoreboard artifact
        vault/_Organized/_Index/_Calibration_Scoreboard.md (parsed, not
        recomputed live -- recomputation is calibration-report's job)
    historical_result -> data/domains/<sport>/{linescores,games}.parquet
        (final score / W-L, read directly, no derived number)
    mechanism_effect  -> domains/<sport>/knowledge/validation_ledger.jsonl
        ("does mechanism X hold up locally" -- verbatim ledger row(s):
        verdict/effect/n/p/corpus/note, LOCAL-only framing baked into the
        answer, never improvised for an unregistered mechanism)
    analytics_attribution / analytics_claim_survival / analytics_verification /
    analytics_contradictions -> scripts.platformkit.analytics_verify.answers
        (LANE E; fail-closed over data/cache/analytics_verify/*.json --
        no_data if the artifact is absent, refused if it isn't stamped
        edge_claimed:false or is older than the staleness bound)
    edge_language     -> always REFUSED (see .claude/rules/no-edge-claims.md)

Every resolve() call returns one envelope shape:
    {status: "ok"|"refused"|"not_supported"|"no_data",
     category, sport, source_artifact, as_of, ...category-specific fields}
"pinned" categories name a MTIME as_of; the answer is only as fresh as that file.
"""
from __future__ import annotations

import difflib
import json
import os
import re
from datetime import datetime, timezone

import pandas as pd

from scripts.platformkit.analytics_verify import answers as _analytics
from scripts.platformkit.answers import contracts as _contracts
from scripts.platformkit.answers import effect_graph as _eg
from scripts.platformkit.answers import leaderboard_resolver as _lb
from scripts.platformkit.answers.registry_loader import SPORTS as _CONCEPT_SPORTS
from scripts.platformkit.profiles import ask as _ask

# ---------------------------------------------------------------------------
# Retracted-number / edge-language guard (binding list, .claude/rules/no-edge-claims.md)
# ---------------------------------------------------------------------------
RETRACTED_NUMBERS = ("18.38", "0.119", "+54%", "54%", "78.11", "8.94", "54.57")
EDGE_KEYWORDS = ("edge", "roi", "beat the market", "beat the close", "profit",
                 "positive ev", "+ev", "bankroll", "win rate over market")


def _word_boundary_hit(text: str, keyword: str) -> bool:
    """True if `keyword` occurs in `text` as a whole word/phrase, not merely
    as a substring of a longer word (e.g. "edge" must not fire on "ledger",
    "ece" must not fire on "receipt"). A trailing '*' marks a deliberate stem
    match (e.g. "calibrat*" matches calibration/calibrated/calibrating) --
    only its left edge is boundary-checked."""
    stem = keyword.endswith("*")
    kw = keyword[:-1] if stem else keyword
    left = r"(?<![A-Za-z0-9])" if kw[0].isalnum() else ""
    right = "" if stem else (r"(?![A-Za-z0-9])" if kw[-1].isalnum() else "")
    return re.search(left + re.escape(kw) + right, text) is not None


def is_edge_language(text: str) -> str | None:
    """Returns the matched forbidden token, or None. Checked BEFORE
    classification so an edge-flavored question never reaches a resolver."""
    low = text.lower()
    for tok in RETRACTED_NUMBERS:
        if tok in low:
            return tok
    for tok in EDGE_KEYWORDS:
        if _word_boundary_hit(low, tok):
            return tok
    return None


# ---------------------------------------------------------------------------
# The registry: category name -> resolver metadata (deliverable 1)
# ---------------------------------------------------------------------------
RESOLVERS: dict[str, dict] = {
    "player_stat": {
        "resolver": "scripts.platformkit.profiles.ask.answer_lookup",
        "source_artifact": "data/cache/profiles/<sport>_{player,team,lineup}_profiles.parquet",
        "computation": "raw_value column for the fuzzy-matched entity+attribute+window row",
        "units": "attribute-native (see attribute_registry.py per sport)", "rounding": "as stored, no rounding",
    },
    "rating_attribute": {
        "resolver": "scripts.platformkit.profiles.ask.answer_lookup",
        "source_artifact": "data/cache/profiles/<sport>_{player,team,lineup}_profiles.parquet",
        "computation": "percentile + rating_2k (25 + percentile*0.74) for the same matched row",
        "units": "percentile 0-100; rating_2k 25-99 (presentation-only, never causal/predictive)",
        "rounding": "2 decimals",
    },
    "concept_rating": {
        "resolver": "scripts.platformkit.answers.contracts.answer_question",
        "source_artifact": "derived from the profiles parquet via domains/<sport>/concepts/concept_registry.py",
        "computation": "status-rank x n-shrinkage weighted composite across a concept's declared signals",
        "units": "composite score 0-100 (percentile-weighted, not a raw unit)", "rounding": "2 decimals",
    },
    "prediction_winprob": {
        "resolver": "scripts/platformkit/predict_matchup.py (subprocess CLI)",
        "source_artifact": "domains/<sport>/predictor.py via scripts.platformkit.predictor_jd._build_predictor",
        "computation": "calibrated pregame probability; in-game adds the validated repricer given a live score state",
        "units": "probability 0-1", "rounding": "4 decimals",
    },
    "calibration_number": {
        "resolver": "resolver_registry.calibration_number (parses the pinned scoreboard)",
        "source_artifact": "vault/_Organized/_Index/_Calibration_Scoreboard.md",
        "computation": "per-sport Brier/ECE baseline vs improved, from the last calibration-report run",
        "units": "Brier score / ECE, both 0-1 (lower is better calibrated)", "rounding": "5 decimals as printed",
    },
    "historical_result": {
        "resolver": "resolver_registry.historical_result",
        "source_artifact": "data/domains/basketball_nba/linescores.parquet | data/domains/mlb/games.parquet",
        "computation": "final score read directly off the boxscore/linescore row for the matched game",
        "units": "points (NBA) / runs (MLB), integers", "rounding": "none -- integer score",
    },
    "mechanism_effect": {
        "resolver": "resolver_registry.mechanism_effect",
        "source_artifact": "domains/<sport>/knowledge/validation_ledger.jsonl",
        "computation": "verbatim lookup of the matched hypothesis row(s) -- verdict/effect/n/p/corpus/note, "
                        "as written by the mechanism validators; never recomputed, never improvised",
        "units": "effect size + n + p as stored (sport/spec-native, see each row's 'note' for what was measured)",
        "rounding": "none -- verbatim from the ledger row",
    },
    "edge_language": {
        "resolver": None,
        "source_artifact": ".claude/rules/no-edge-claims.md",
        "computation": "ALWAYS REFUSED -- no resolver computes a dollar edge/ROI/beat-the-market number here",
        "units": "n/a", "rounding": "n/a",
    },
    "ranking": {
        "resolver": "scripts.platformkit.answers.leaderboard_resolver.resolve_query",
        "source_artifact": "data/cache/profiles/<sport>_{player,team,lineup}_profiles.parquet",
        "computation": "top-N by ONE registered attribute's raw_value, min_n volume floor on top of the "
                        "attribute's own baked-in floor, deterministic (raw_value,entity_id) tie-break -- a "
                        "fuzzy category word that matches 0 or 2+ attributes is REFUSED with candidates, never guessed",
        "units": "attribute-native (see attribute_registry.py per sport)", "rounding": "as stored, no rounding",
    },
    "analytics_attribution": {
        "resolver": "scripts.platformkit.analytics_verify.answers.attribution",
        "source_artifact": "data/cache/analytics_verify/attribution_rollup.json",
        "computation": "verbatim by_family[family] / by_card[card_id] CLV-attribution receipt -- never recomputed",
        "units": "receipt-native (mean/median CLV pct, beat-close pct, counts, as stored)",
        "rounding": "none -- verbatim from artifact",
    },
    "analytics_claim_survival": {
        "resolver": "scripts.platformkit.analytics_verify.answers.claim_survival",
        "source_artifact": "data/cache/analytics_verify/claim_survival.json",
        "computation": "verbatim card-decay scoreboard -- verdict counts + 7d/30d/60d survival fractions",
        "units": "counts + fractions, as stored", "rounding": "none -- verbatim from artifact",
    },
    "analytics_verification": {
        "resolver": "scripts.platformkit.analytics_verify.answers.verification",
        "source_artifact": "data/cache/analytics_verify/sentinel_report.json",
        "computation": "verbatim sentinel re-derivation check(s) -- served_value vs recomputed_value + verdict",
        "units": "stat-native served/recomputed values + verdict enum", "rounding": "none -- verbatim from artifact",
    },
    "analytics_contradictions": {
        "resolver": "scripts.platformkit.analytics_verify.answers.contradictions",
        "source_artifact": "data/cache/analytics_verify/contradiction_report.json",
        "computation": "verbatim conflict rows from the cross-claim consistency scan, optionally filtered by family",
        "units": "n/a -- structured conflict records", "rounding": "none -- verbatim from artifact",
    },
}

_CONCEPT_KEYWORDS = ("best", "who has", "vs ", " versus ", "why is", "fit team", "does ", "compare")
_PREDICTION_KEYWORDS = ("win probability", "who wins", "will win", "predict", "forecast", "project the",
                        "spread", "moneyline", "odds for")
_CALIBRATION_KEYWORDS = ("brier", "ece", "calibrat*")
_HISTORICAL_KEYWORDS = ("final score", "what happened", "box score", "result of", "score of the game",
                        "who won on", "final of")
_MECHANISM_KEYWORDS = ("evidence", "mechanism", "hypothesis", "folklore",
                       "hold up", "does the data support", "is it true that")
_ANALYTICS_ATTRIBUTION_KEYWORDS = ("attribution", "clv attribution", "link method", "join rate")
_ANALYTICS_SURVIVAL_KEYWORDS = ("claim survival", "card decay", "decayed card", "survival rate")
_ANALYTICS_VERIFICATION_KEYWORDS = ("sentinel", "verification check", "discrepant", "recomputed value")
_ANALYTICS_CONTRADICTION_KEYWORDS = ("contradiction", "conflicting claim", "inconsistent claim")
# "what affects Y" / "what does X affect" -- effect-graph queries (LANE C5),
# routed through the SAME mechanism_effect category (verbatim graph edges are
# just another ledger-backed receipt, not a new resolver family).
_AFFECTS_RE = re.compile(r"^\s*what affects\s+(.+?)\s*\??\s*$", re.I)
_WHAT_DOES_X_AFFECT_RE = re.compile(r"^\s*what does\s+(.+?)\s+affect\s*\??\s*$", re.I)


def classify(query: str) -> str | None:
    """category name, or None if no rule matches (-> NOT_SUPPORTED). Checked
    in priority order: edge language first (a refusal always wins), then
    prediction/calibration/historical (specific phrasing), then concept vs.
    plain stat (concept needs an explicit shape word; a bare "<entity>
    <attribute>" query is player_stat/rating_attribute, resolved by ask.py's
    own fuzzy matcher, not by this classifier)."""
    if is_edge_language(query):
        return "edge_language"
    low = query.lower()
    if any(_word_boundary_hit(low, k) for k in _CALIBRATION_KEYWORDS):
        return "calibration_number"
    if any(k in low for k in _PREDICTION_KEYWORDS):
        return "prediction_winprob"
    if any(k in low for k in _HISTORICAL_KEYWORDS):
        return "historical_result"
    if _lb.is_ranking_query(low):
        return "ranking"
    if any(k in low for k in _ANALYTICS_ATTRIBUTION_KEYWORDS):
        return "analytics_attribution"
    if any(k in low for k in _ANALYTICS_SURVIVAL_KEYWORDS):
        return "analytics_claim_survival"
    if any(k in low for k in _ANALYTICS_VERIFICATION_KEYWORDS):
        return "analytics_verification"
    if any(k in low for k in _ANALYTICS_CONTRADICTION_KEYWORDS):
        return "analytics_contradictions"
    if any(k in low for k in _MECHANISM_KEYWORDS) or _AFFECTS_RE.match(low) or _WHAT_DOES_X_AFFECT_RE.match(low):
        return "mechanism_effect"
    if any(k in low for k in _CONCEPT_KEYWORDS):
        return "concept_rating"
    if "rating" in low or "percentile" in low or "2k" in low:
        return "rating_attribute"
    return "player_stat"  # default shape: "<entity> <attribute>" fact lookup


# ---------------------------------------------------------------------------
# Resolvers not already owned by another module
# ---------------------------------------------------------------------------
_SCOREBOARD_PATH = os.path.join("vault", "_Organized", "_Index", "_Calibration_Scoreboard.md")
_SCOREBOARD_ROW_RE = re.compile(
    r"^\|\s*(?P<sport>\w+)\s*\|\s*(?P<n>[\d,]+)\s*\|\s*(?P<base_brier>[\d.]+)\s*\|\s*"
    r"(?P<imp_brier>[\d.]+)\s*\|\s*(?P<d_brier>[+-]?[\d.]+)\s*\|\s*(?P<base_ece>[\d.]+)\s*\|\s*"
    r"(?P<imp_ece>[\d.]+)\s*\|\s*(?P<d_ece>[+-]?[\d.]+)\s*\|\s*(?P<method>[^|]+)\|\s*$",
    re.MULTILINE,
)


def calibration_number(sport: str) -> dict:
    """Parses the pinned scoreboard row for `sport` -- never recomputes.
    Absent artifact (fresh clone; vault/ is gitignored) -> honest no_data."""
    if not os.path.exists(_SCOREBOARD_PATH):
        return {"status": "no_data", "category": "calibration_number", "sport": sport,
                "source_artifact": _SCOREBOARD_PATH, "note": "scoreboard not built in this clone"}
    text = open(_SCOREBOARD_PATH, encoding="utf-8").read()
    as_of = datetime.fromtimestamp(os.path.getmtime(_SCOREBOARD_PATH), tz=timezone.utc).isoformat()
    for m in _SCOREBOARD_ROW_RE.finditer(text):
        if m.group("sport").lower() == sport.lower():
            return {"status": "ok", "category": "calibration_number", "sport": sport,
                     "source_artifact": _SCOREBOARD_PATH, "as_of": as_of,
                     "n": int(m.group("n").replace(",", "")),
                     "baseline_brier": float(m.group("base_brier")), "improved_brier": float(m.group("imp_brier")),
                     "baseline_ece": float(m.group("base_ece")), "improved_ece": float(m.group("imp_ece")),
                     "method": m.group("method").strip()}
    return {"status": "no_data", "category": "calibration_number", "sport": sport,
            "source_artifact": _SCOREBOARD_PATH, "note": f"no row for sport '{sport}' in current scoreboard"}


_HIST_PATHS = {
    "nba": ("data/domains/basketball_nba/linescores.parquet", "home_abbr", "away_abbr"),
    "mlb": ("data/domains/mlb/games.parquet", "home_team", "away_team"),
}


def historical_result(sport: str, team: str, opponent: str | None = None, date: str | None = None) -> dict:
    """Final score for one real game, read directly off the boxscore/linescore
    parquet -- zero-row honesty: no match -> no_data, never fabricated."""
    cfg = _HIST_PATHS.get(sport)
    if cfg is None:
        return {"status": "not_supported", "category": "historical_result", "sport": sport,
                "note": f"historical_result not wired for sport '{sport}'"}
    path, home_col, away_col = cfg
    if not os.path.exists(path):
        return {"status": "no_data", "category": "historical_result", "sport": sport, "source_artifact": path}
    df = pd.read_parquet(path)
    mask = (df[home_col] == team) | (df[away_col] == team)
    if opponent:
        mask &= (df[home_col] == opponent) | (df[away_col] == opponent)
    if date:
        mask &= df["date"].astype(str).str.startswith(date)
    hits = df[mask]
    if hits.empty:
        return {"status": "no_data", "category": "historical_result", "sport": sport, "source_artifact": path,
                "note": f"zero rows matched team={team!r} opponent={opponent!r} date={date!r} -- refusing, not guessing"}
    row = hits.sort_values("date").iloc[-1]
    as_of = str(row["date"])
    if sport == "nba":
        home_score = int(row[[c for c in df.columns if c.startswith("home_q")]].sum())
        away_score = int(row[[c for c in df.columns if c.startswith("away_q")]].sum())
    else:
        home_score, away_score = int(row["home_runs"]), int(row["away_runs"])
    return {"status": "ok", "category": "historical_result", "sport": sport, "source_artifact": path, "as_of": as_of,
            "home_team": row[home_col], "away_team": row[away_col],
            "home_score": home_score, "away_score": away_score,
            "winner": row[home_col] if home_score > away_score else row[away_col]}


_LEDGER_PATHS = {
    "nba": "domains/basketball_nba/knowledge/validation_ledger.jsonl",
    "mlb": "domains/mlb/knowledge/validation_ledger.jsonl",
    "soccer": "domains/soccer/knowledge/validation_ledger.jsonl",
    "tennis": "domains/tennis/knowledge/validation_ledger.jsonl",
}
# words that show up in a free-text question but never in a hypothesis name --
# stripped before matching so phrasing doesn't defeat the token-subset test.
_MECH_FILLER = {"what", "does", "the", "evidence", "say", "about", "is", "there", "for", "on",
                "local", "data", "support", "it", "true", "that", "hold", "up", "locally",
                "mechanism", "hypothesis", "folklore", "of", "a", "an", "in", "does"}


def _mech_tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _MECH_FILLER}


def _load_ledger(sport: str) -> list[dict]:
    """Fresh read every call -- a concurrent validation lane appends to these
    files live, so no row count or content is ever cached."""
    path = _LEDGER_PATHS.get(sport)
    if path is None or not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def effect_graph_query(sport: str, target: str, direction: str) -> dict:
    """'what affects <Y>' (direction="to") / 'what does <X> affect'
    (direction="from") -- verbatim edges from the pinned LANE C5 effect graph
    (scripts/platformkit/answers/effect_graph.py), never recomputed here."""
    graph = _eg.load_graph()
    if graph is None:
        return {"status": "no_data", "category": "mechanism_effect", "sport": sport,
                "source_artifact": _eg._OUT_PATH, "note": "effect graph not built in this clone"}
    hits = _eg.query_edges(sport, _mech_tokens(target), direction=direction, graph=graph)
    if not hits:
        return {"status": "not_supported", "category": "mechanism_effect", "sport": sport,
                "source_artifact": _eg._OUT_PATH,
                "note": f"no graph edge found for '{target}' ({direction}) in sport '{sport}'"}
    return {"status": "ok", "category": "mechanism_effect", "sport": sport,
            "source_artifact": _eg._OUT_PATH, "as_of": graph["as_of"], "query": target,
            "edges": [{"from": e["from"], "to": e["to"], "status": e["status"], "effect": e["effect"],
                       "n": e["n"], "p": e.get("p"), "corpus": e.get("corpus"), "artifact": e["artifact"],
                       "note": e.get("note", "")} for e in hits],
            "framing": "LOCAL single-corpus finding(s) -- not a market-beating or causal claim"}


def mechanism_effect(sport: str, mechanism: str) -> dict:
    """Matches free text / a mechanism name against the DISTINCT hypothesis
    names in this sport's validation ledger -- never against model memory.
    Multiple ledger rows for the SAME hypothesis (re-tested across corpora,
    e.g. tennis's 4-corpus rows) are all returned together, verbatim, under
    one answer. Multiple DIFFERENT matching hypotheses -> ambiguous with the
    candidate list (ask.py's existing convention). No match -> not_supported,
    never improvised. "what affects Y" / "what does X affect" queries are
    graph lookups (effect_graph_query), handled before the hypothesis-name
    match below."""
    m = _AFFECTS_RE.match(mechanism)
    if m:
        return effect_graph_query(sport, m.group(1), "to")
    m = _WHAT_DOES_X_AFFECT_RE.match(mechanism)
    if m:
        return effect_graph_query(sport, m.group(1), "from")
    path = _LEDGER_PATHS.get(sport)
    if path is None:
        return {"status": "not_supported", "category": "mechanism_effect", "sport": sport,
                "note": f"mechanism_effect not wired for sport '{sport}'. Available: {sorted(_LEDGER_PATHS)}"}
    rows = _load_ledger(sport)
    if not rows:
        return {"status": "no_data", "category": "mechanism_effect", "sport": sport, "source_artifact": path}
    by_name: dict[str, list[dict]] = {}
    for r in rows:
        by_name.setdefault(r["hypothesis"], []).append(r)
    names = sorted(by_name)
    key = mechanism.strip().lower().replace(" ", "_")
    if key in by_name:
        matches = [key]
    else:
        q_tokens = _mech_tokens(mechanism)
        matches = [n for n in names if q_tokens and q_tokens <= _mech_tokens(n)]
        if not matches:
            matches = difflib.get_close_matches(key, names, n=5, cutoff=0.6)
    if not matches:
        return {"status": "not_supported", "category": "mechanism_effect", "sport": sport,
                "note": f"no mechanism matched '{mechanism}' in {path}. Registered hypotheses: {names}"}
    if len(matches) > 1:
        return {"status": "ambiguous", "category": "mechanism_effect", "sport": sport, "candidates": matches}
    name = matches[0]
    as_of = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()
    findings = [{"verdict": r["verdict"], "effect_local": r["effect"], "n": r["n"], "p": r.get("p"),
                 "corpus": r["corpus"], "note": r["note"]} for r in by_name[name]]
    return {"status": "ok", "category": "mechanism_effect", "sport": sport, "source_artifact": path,
            "as_of": as_of, "hypothesis": name, "findings": findings,
            "framing": "LOCAL single-corpus finding(s) -- not a market-beating or causal claim"}


# ---------------------------------------------------------------------------
# Single dispatch entrypoint
# ---------------------------------------------------------------------------
def resolve(query: str, sport: str = "nba", category: str | None = None, **kwargs) -> dict:
    """The one function every consumer (human, CLI, or an LLM following
    docs/AI_CONSUMER_CONTRACT.md) calls. Never improvises past a registered
    resolver; an unclassified or unregistered category is NOT_SUPPORTED."""
    cat = category or classify(query)
    if cat is None or cat not in RESOLVERS:
        return {"status": "not_supported", "category": cat, "query": query,
                "note": f"no resolver registered for this question type. Registered: {sorted(RESOLVERS)}"}
    meta = RESOLVERS[cat]
    if cat == "edge_language":
        return {"status": "refused", "category": cat, "query": query, "source_artifact": meta["source_artifact"],
                "note": "edge/ROI/retracted-number language is out of scope for this engine -- "
                        "see .claude/rules/no-edge-claims.md"}
    if cat == "calibration_number":
        return calibration_number(sport)
    if cat == "historical_result":
        return historical_result(sport, kwargs.get("team", ""), kwargs.get("opponent"), kwargs.get("date"))
    if cat == "mechanism_effect":
        return mechanism_effect(sport, kwargs.get("mechanism") or query)
    if cat == "analytics_attribution":
        return _analytics.attribution(sport, kwargs.get("family"), kwargs.get("card_id"))
    if cat == "analytics_claim_survival":
        return _analytics.claim_survival(sport)
    if cat == "analytics_verification":
        return _analytics.verification(sport, kwargs.get("stat"))
    if cat == "analytics_contradictions":
        return _analytics.contradictions(sport, kwargs.get("family"))
    if cat == "ranking":
        return _lb.resolve_query(sport, query, top_n=kwargs.get("top_n"), min_n=kwargs.get("min_n", 0.0),
                                  window=kwargs.get("window"), kind=kwargs.get("kind"),
                                  ascending=kwargs.get("ascending", False), category=kwargs.get("attribute"))
    if cat == "prediction_winprob":
        return {"status": "not_supported", "category": cat, "sport": sport,
                "note": "prediction_winprob is resolved by the predict-matchup CLI/skill, not this "
                        "in-process registry -- run scripts/platformkit/predict_matchup.py"}
    if cat in ("player_stat", "rating_attribute"):
        if sport not in _ask.SPORTS:
            return {"status": "not_supported", "category": cat, "sport": sport,
                    "note": f"sport not wired for profile lookups. Available: {_ask.SPORTS}"}
        r = _ask.answer_lookup(query, sport, kwargs.get("window"))
        if r["status"] != "ok":
            return {"status": "no_data" if r["status"] in ("no_entity", "no_attribute", "no_data") else r["status"],
                     "category": cat, "sport": sport, "detail": r}
        row = r["row"]
        return {"status": "ok", "category": cat, "sport": sport,
                 "source_artifact": str(row["sources"]), "as_of": str(row["window"]),
                 "entity_name": row["entity_name"], "attribute": row["attribute"],
                 "raw_value": row["raw_value"], "percentile": round(float(row["percentile"]), 2),
                 "rating_2k": round(float(row["rating_2k"]), 2), "n": round(float(row["n"]), 1),
                 "status_label": row["status"]}
    if cat == "concept_rating":
        if sport not in _CONCEPT_SPORTS:
            return {"status": "not_supported", "category": cat, "sport": sport,
                    "note": f"no concept registry for sport '{sport}'. Available: {sorted(_CONCEPT_SPORTS)}"}
        result = _contracts.answer_question(query, sport, kwargs.get("window"), kwargs.get("concept"),
                                             kwargs.get("kind", "player"))
        if "error" in result:
            return {"status": "no_data", "category": cat, "sport": sport, "note": result["error"]}
        return {"status": "ok", "category": cat, "sport": sport,
                 "source_artifact": f"domains/{ 'basketball_nba' if sport=='nba' else sport }/concepts/concept_registry.py",
                 "as_of": result.get("window"), **result}
    return {"status": "not_supported", "category": cat, "note": "unreachable -- category registered but undispatched"}
