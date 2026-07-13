"""scripts.platformkit.interaction_factory.builders_soccer_setpiece -- B8 lane:
soccer set-piece xG as-of attrs, built from ON-DISK StatsBomb open-data event
caches (data/cache/statsbomb/events/*.json + match_meta_full.parquet, already
fetched by domains.soccer.ingest_statsbomb_events -- zero new network calls here)
bridged to the EXISTING soccer outcome corpus (domains.soccer.matches.parquet,
football-data.co.uk convention) by (date, div, home_team, away_team) after a
team-name normalize + small alias map.

PREMISE (why this rung, not rung (a)): the sibling in-game situation-labeled
signal, Understat, is BLOCKED_ROBOTS (data/cache/understat/status.json -- full-
site robots.txt Disallow, never scraped). StatsBomb shot events carry
`play_pattern.name` ('From Corner' / 'From Free Kick' = the set-piece/dead-ball
analogue of Understat's `situation` field), so this is rung (b): real event data,
gated on whether it joins the outcome corpus.

COVERAGE: only the 4 full 2015/16 seasons that are BOTH a complete StatsBomb
competition AND already a div/season combination on disk in matches.parquet --
Premier_League_2015_2016->E0, La_Liga_2015_2016->SP1, Serie_A_2015_2016->I1,
Ligue_1_2015_2016->F1 (data/cache/statsbomb/match_meta_full.parquet's
`competition` column x matches.parquet's `div`/`season` columns). Bundesliga
(D1) StatsBomb coverage is a 34-match partial slice (not a full season) --
excluded, not silently included. Any StatsBomb match whose team names don't
resolve to a matches.parquet (date, div, home, away) key drops out of the
bridge -- never fabricated (see build_soccer_setpiece_spine docstring).

LEAK-FREE: same walk_forward_asof (scripts.platformkit.asof_common) snapshot-
before-update primitive every as-of builder in this factory reuses -- strictly
PRIOR trailing per-team mean, state shared across home/away slots, debut = NaN
(assert_no_future_leak runs inside walk_forward_asof itself). The 3 STATIC_POOLS
attrs are home-minus-away trailing-mean diffs:
  setpiece_xg_share_asof -- trailing mean(setpiece_xg / total_xg) diff
  corner_xg_asof         -- trailing mean(corner-only xG) diff
  openplay_xg_asof       -- trailing mean(non-set-piece xG) diff
No soccer in-game state pool exists yet (checked builders_ingame_state.py /
builders_state_conditioner.py / generator.TEMPLATES -- only NBA has an
ingame_state_asof family), so this lane registers self_cross ONLY.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.asof_common import AsofSpec, ExpandingMean, walk_forward_asof

REPO = Path(__file__).resolve().parents[3]
_MATCH_META_FULL = REPO / "data" / "cache" / "statsbomb" / "match_meta_full.parquet"
_EVENTS_DIR = REPO / "data" / "cache" / "statsbomb" / "events"
_SOCCER_MATCHES = REPO / "data" / "domains" / "soccer" / "matches.parquet"
_SETPIECE_CORPUS = "soccer_setpiece_asof"

# StatsBomb `competition` -> matches.parquet `div` (both cover the same
# full 2015/16 season -- see module docstring COVERAGE section).
_LEAGUE_DIV = {
    "Premier_League_2015_2016": "E0",
    "La_Liga_2015_2016": "SP1",
    "Serie_A_2015_2016": "I1",
    "Ligue_1_2015_2016": "F1",
}

# Normalized (accent-stripped, lowercased) StatsBomb name -> normalized
# football-data name, ONLY where they differ structurally (abbreviation / word
# order); accent-only differences (Atletico, Malaga, Saint-Etienne, ...) are
# handled by _norm's diacritic strip and need no entry here.
_ALIAS = {
    # Premier League
    "afc bournemouth": "bournemouth", "leicester city": "leicester",
    "manchester city": "man city", "manchester united": "man united",
    "newcastle united": "newcastle", "norwich city": "norwich",
    "stoke city": "stoke", "swansea city": "swansea",
    "tottenham hotspur": "tottenham", "west bromwich albion": "west brom",
    "west ham united": "west ham",
    # La Liga
    "athletic club": "ath bilbao", "atletico madrid": "ath madrid",
    "celta vigo": "celta", "espanyol": "espanol", "levante ud": "levante",
    "rc deportivo la coruna": "la coruna", "rayo vallecano": "vallecano",
    "real betis": "betis", "real sociedad": "sociedad",
    "sporting gijon": "sp gijon",
    # Serie A
    "ac milan": "milan", "as roma": "roma", "hellas verona": "verona",
    "inter milan": "inter",
    # Ligue 1 (Gazelec Ajaccio == football-data's "Ajaccio GFCO" disambiguation
    # -- Gazelec Football Club Olympique de Ajaccio, distinct from AC Ajaccio)
    "as monaco": "monaco", "gazelec ajaccio": "ajaccio gfco",
    "olympique de marseille": "marseille", "ogc nice": "nice",
    "paris saint-germain": "paris sg", "saint-etienne": "st etienne",
    "stade malherbe caen": "caen", "stade de reims": "reims",
}

_SETPIECE_PATTERNS = ("From Corner", "From Free Kick")
_METRICS = (
    ("setpiece_xg_share_asof", "home_setpiece_share", "away_setpiece_share"),
    ("corner_xg_asof", "home_corner_xg", "away_corner_xg"),
    ("openplay_xg_asof", "home_openplay_xg", "away_openplay_xg"),
)


def _norm(name: object) -> str:
    """Lowercase, diacritic-stripped team name (both corpora funnel through this)."""
    n = unicodedata.normalize("NFKD", str(name))
    n = "".join(c for c in n if not unicodedata.combining(c))
    return n.lower().strip()


def _fd_key(sb_name: str) -> str:
    """StatsBomb team name -> its football-data join key (alias override, else
    the plain normalized name)."""
    n = _norm(sb_name)
    return _ALIAS.get(n, n)


def _match_xg_breakdown(events: List[dict]) -> Dict[str, Dict[str, float]]:
    """StatsBomb team name (as it appears in the event stream) -> summed shot
    statsbomb_xg bucketed by play_pattern: total / corner-only / setpiece
    (corner + free kick). Non-shot events and shots with no team are skipped."""
    acc: Dict[str, Dict[str, float]] = {}
    for e in events:
        if (e.get("type") or {}).get("name") != "Shot":
            continue
        tn = (e.get("team") or {}).get("name")
        if tn is None:
            continue
        xg = float((e.get("shot") or {}).get("statsbomb_xg") or 0.0)
        a = acc.setdefault(tn, {"total": 0.0, "corner": 0.0, "setpiece": 0.0})
        a["total"] += xg
        pp = (e.get("play_pattern") or {}).get("name")
        if pp == "From Corner":
            a["corner"] += xg
            a["setpiece"] += xg
        elif pp == "From Free Kick":
            a["setpiece"] += xg
    return acc


def build_soccer_setpiece_spine(match_meta: pd.DataFrame, matches: pd.DataFrame,
                                 events_dir: Path, cap: Optional[int] = None) -> pd.DataFrame:
    """StatsBomb match_meta rows (competition in _LEAGUE_DIV) bridged to
    matches.parquet's event_id via the team-name join key + (date, div). Reads
    ONLY cached events/<match_id>.json (zero network). A StatsBomb match with no
    cached event file, no shot data for either team, or no (date, div, home,
    away) match in `matches` simply does not appear in the output -- an honest
    coverage gap, never fabricated. Returns event_id, date, home_team, away_team
    (join keys) + the 6 raw per-match metrics _METRICS trails."""
    meta = match_meta[match_meta["competition"].isin(_LEAGUE_DIV)].copy()
    if cap is not None:
        meta = meta.head(cap)
    rows: List[dict] = []
    for _, m in meta.iterrows():
        ev_path = events_dir / f"{m['match_id']}.json"
        if not ev_path.exists():
            continue
        try:
            events = json.loads(ev_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        xg = _match_xg_breakdown(events)
        sh, sa = xg.get(m["home_team"]), xg.get(m["away_team"])
        if not sh or not sa:
            continue
        rows.append({
            "match_date": m["match_date"], "div": _LEAGUE_DIV[m["competition"]],
            "join_home": _fd_key(m["home_team"]), "join_away": _fd_key(m["away_team"]),
            "home_setpiece_share": sh["setpiece"] / sh["total"] if sh["total"] else np.nan,
            "away_setpiece_share": sa["setpiece"] / sa["total"] if sa["total"] else np.nan,
            "home_corner_xg": sh["corner"], "away_corner_xg": sa["corner"],
            "home_openplay_xg": sh["total"] - sh["setpiece"],
            "away_openplay_xg": sa["total"] - sa["setpiece"],
        })
    spine = pd.DataFrame(rows)
    if spine.empty:
        return spine
    spine["match_date"] = pd.to_datetime(spine["match_date"]).dt.normalize()
    m2 = matches.copy()
    m2["date"] = pd.to_datetime(m2["date"]).dt.normalize()
    m2["join_home"] = m2["home_team"].map(_norm)
    m2["join_away"] = m2["away_team"].map(_norm)
    bridged = spine.merge(
        m2[["event_id", "date", "div", "join_home", "join_away"]],
        left_on=["match_date", "div", "join_home", "join_away"],
        right_on=["date", "div", "join_home", "join_away"], how="inner")
    bridged = bridged.drop_duplicates(subset=["event_id"])
    keep = ["event_id", "date", "join_home", "join_away",
            "home_setpiece_share", "away_setpiece_share",
            "home_corner_xg", "away_corner_xg", "home_openplay_xg", "away_openplay_xg"]
    return bridged[keep].rename(columns={"join_home": "home_team", "join_away": "away_team"})


def build_soccer_setpiece_asof(spine: pd.DataFrame) -> pd.DataFrame:
    """Strictly-prior trailing home-minus-away diff, one column per _METRICS
    entry, via asof_common.walk_forward_asof + ExpandingMean -- same snapshot-
    before-update primitive every as-of builder in this factory reuses. State is
    per-team (join key), SHARED across the home/away slot; a fresh accumulator
    set is used per metric (no cross-metric bleed)."""
    if spine.empty:
        cols = {c: pd.Series(dtype="float64") for c, _h, _a in _METRICS}
        return pd.DataFrame({"event_id": pd.Series(dtype="object"), **cols})
    out = pd.DataFrame({"event_id": spine["event_id"].to_numpy()})
    for out_col, home_col, away_col in _METRICS:
        spec = AsofSpec(sort_keys=("date", "event_id"),
                         slots=(("home_team", home_col, "home"), ("away_team", away_col, "away")),
                         id_col="event_id")
        res = walk_forward_asof(spine, spec, lambda: ExpandingMean(min_prior=1))
        res = res.set_index("event_id").reindex(spine["event_id"])
        out[out_col] = (res["home_asof"] - res["away_asof"]).to_numpy()
    return out


def build_soccer_setpiece_match_frame(matches: pd.DataFrame, spine: pd.DataFrame,
                                       attrs: List[str]) -> pd.DataFrame:
    """Per-match frame: y=home_win (matches.parquet fthg>ftag), asof__<attr> =
    build_soccer_setpiece_asof's diff column, left-joined onto the FULL matches
    corpus (unbridged matches -> honest NaN, same precedent as
    builders_task39b.build_soccer_match_frame)."""
    asof = build_soccer_setpiece_asof(spine)
    m = matches[["event_id", "div", "fthg", "ftag"]].copy()
    m["y"] = (m["fthg"] > m["ftag"]).astype(float)
    f_cols = ["event_id"] + [c for c in attrs if c in asof.columns]
    out = m.merge(asof[f_cols], on="event_id", how="left") if len(f_cols) > 1 else m
    return out.rename(columns={a: "asof__" + a for a in attrs if a in out.columns})


def _soccer_setpiece_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (_MATCH_META_FULL.exists() and _SOCCER_MATCHES.exists() and _EVENTS_DIR.exists()):
        return None
    match_meta = pd.read_parquet(_MATCH_META_FULL)
    matches = pd.read_parquet(_SOCCER_MATCHES,
                               columns=["event_id", "date", "div", "season", "home_team", "away_team", "fthg", "ftag"])
    spine = build_soccer_setpiece_spine(match_meta, matches[matches["season"] == 2015], _EVENTS_DIR)
    if spine.empty:
        return {"frame": pd.DataFrame(), "cluster": "div", "corpus": _SETPIECE_CORPUS, "kind": "logit",
                "insufficient_train_history": True,
                "train_note": "0 StatsBomb matches bridged to matches.parquet via the team-name "
                              "join key + (date, div) -- honest coverage gap, not a code bug."}
    frame = build_soccer_setpiece_match_frame(matches, spine, attrs)
    return {"frame": frame, "cluster": "div", "corpus": _SETPIECE_CORPUS, "kind": "logit"}


__all__ = [
    "build_soccer_setpiece_spine", "build_soccer_setpiece_asof",
    "build_soccer_setpiece_match_frame", "_soccer_setpiece_builder",
]
