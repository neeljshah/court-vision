"""scripts.platformkit.tip_capture.ingame_features -- per-tick feature PLUMBING
over a day's ingame_capture.py output.

Turns data/cache/tip_capture/<sport>/ingame_<date>.jsonl (one row per
(game_id, capture_ts), schema documented in ingame_capture.py) into a flat
feature frame keyed by (game_id, capture_ts): score margin + margin velocity
(delta vs the previous tick for that game), our winprob vs a devigged market
probability, and pbp-tail-derived features (recent scoring run, foul count,
star-on-floor) where the feed provides them.

NO predictive claims here -- this is feature PLUMBING for a future leak-free
gate, not a signal. Any field the source feed omits is NaN/None, NEVER
silently imputed (mirrors ingame_capture.py's own honest-gap convention).

Run: python -m scripts.platformkit.tip_capture.ingame_features --sport nba --date 2026-07-18
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
DEFAULT_IN_DIR = _REPO_ROOT / "data" / "cache" / "tip_capture"
DEFAULT_OUT_DIR = DEFAULT_IN_DIR / "features"
DEFAULT_PROFILES_DIR = _REPO_ROOT / "data" / "cache" / "profiles"
DEFAULT_USAGE_ATTRIBUTE = "pts_per36"
NAN = float("nan")


def _norm_name(s: Any) -> str:
    """Lowercase + accent-fold (e.g. Jokic's c-acute) for name comparison."""
    folded = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in folded if not unicodedata.combining(c)).strip()


def _name_tokens(s: Any) -> Set[str]:
    return set(re.sub(r"[^a-z0-9\s]", "", _norm_name(s)).split())


# --------------------------------------------------------------------------- #
# I/O: a day's captured rows, tolerant of a torn trailing line (crash-safe
# append convention shared with store.py / ingame_capture.py).
# --------------------------------------------------------------------------- #

def load_day_rows(sport: str, date_str: str, *, in_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    base = Path(in_dir) if in_dir is not None else DEFAULT_IN_DIR
    path = base / sport.lower() / f"ingame_{date_str}.jsonl"
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_top_usage_names(sport: str, *, parquet_path: Optional[Path] = None,
                         top_n: int = 50, attribute: str = DEFAULT_USAGE_ATTRIBUTE,
                         pd_reader: Optional[Any] = None) -> Set[str]:
    """Top-*top_n* players by *attribute* (latest season window) from the
    long-format profiles parquet, lazy + column-pruned (4 cols of a 75k-row
    frame, not the whole thing). [] / missing attribute -> empty set (honest
    "no star list for this sport"), never a guess."""
    path = Path(parquet_path) if parquet_path is not None else (
        DEFAULT_PROFILES_DIR / f"{sport.lower()}_player_profiles.parquet")
    reader = pd_reader if pd_reader is not None else pd.read_parquet
    try:
        df = reader(path, columns=["entity_name", "attribute", "window", "raw_value"])
    except Exception:  # noqa: BLE001 -- missing/corrupt parquet is an honest empty list
        return set()
    sub = df[df["attribute"] == attribute].copy()
    if sub.empty:
        return set()
    sub["raw_value"] = pd.to_numeric(sub["raw_value"], errors="coerce")
    sub = sub.dropna(subset=["raw_value"])
    # latest window per entity == lexically-max window label (mirrors
    # profiles/ask.py's "latest" convention: season_2025_26 > season_2024_25)
    sub = sub.sort_values("window").groupby("entity_name", as_index=False).tail(1)
    top = sub.sort_values("raw_value", ascending=False).head(top_n)
    return {_norm_name(n) for n in top["entity_name"]}


# --------------------------------------------------------------------------- #
# Per-row feature extractors -- each returns NaN/None on any missing input,
# never a fabricated value.
# --------------------------------------------------------------------------- #

def score_margin(row: Dict[str, Any]) -> float:
    hs, as_ = row.get("score_home"), row.get("score_away")
    if hs is None or as_ is None:
        return NAN
    return float(hs) - float(as_)


def _devig_home_prob(event: Dict[str, Any]) -> Optional[float]:
    """First venue in a market event's two-way decimal prices -> devigged
    P(home). None if the event has no usable home+away price."""
    for venue_prices in (event.get("prices") or {}).values():
        dec_h, dec_a = venue_prices.get("home"), venue_prices.get("away")
        if not dec_h or not dec_a or dec_h <= 0 or dec_a <= 0:
            continue
        p_h, p_a = 1.0 / dec_h, 1.0 / dec_a
        total = p_h + p_a
        if total > 0:
            return p_h / total
    return None


def _match_market_event(events: Iterable[Dict[str, Any]], home: str, away: str) -> Optional[Dict[str, Any]]:
    """capture_market(sport) pulls every event for the WHOLE sport that
    tick -- find the one for THIS game by team-name token overlap (order-
    agnostic: a venue may list home/away swapped from our feed)."""
    h_tok, a_tok = _name_tokens(home), _name_tokens(away)
    for ev in events:
        eh_tok, ea_tok = _name_tokens(ev.get("home")), _name_tokens(ev.get("away"))
        if (h_tok & eh_tok) and (a_tok & ea_tok):
            return ev
        if (h_tok & ea_tok) and (a_tok & eh_tok):
            return ev
    return None


def market_home_prob(market_payload: Optional[Dict[str, Any]], home: str, away: str) -> Optional[float]:
    for venue in ("kalshi", "polymarket"):
        block = (market_payload or {}).get(venue) or {}
        if block.get("status") != "ok":
            continue
        ev = _match_market_event(block.get("events") or [], home, away)
        if ev is None:
            continue
        p = _devig_home_prob(ev)
        if p is not None:
            return p
    return None


def winprob_market_gap(row: Dict[str, Any]) -> float:
    wp = (row.get("payload") or {}).get("winprob") or {}
    if wp.get("status") != "ok" or "p_home_win" not in wp:
        return NAN
    p_mkt = market_home_prob((row.get("payload") or {}).get("market"),
                             row.get("home", ""), row.get("away", ""))
    if p_mkt is None:
        return NAN
    return float(wp["p_home_win"]) - float(p_mkt)


def _pbp_events(row: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    tail = (row.get("payload") or {}).get("pbp_tail") or {}
    if tail.get("status") != "ok":
        return None
    return tail.get("events") or []


def recent_scoring_run(row: Dict[str, Any]) -> float:
    """Net home-minus-away point swing across the captured pbp tail (signed:
    positive = home scored more over the tail window). Needs >=1 event with
    both cumulative scores at each end; else NaN."""
    events = _pbp_events(row)
    if not events:
        return NAN
    first, last = events[0], events[-1]
    hs0, as0 = first.get("home_score"), first.get("away_score")
    hs1, as1 = last.get("home_score"), last.get("away_score")
    if None in (hs0, as0, hs1, as1):
        return NAN
    return float((hs1 - hs0) - (as1 - as0))


def foul_count_tail(row: Dict[str, Any]) -> float:
    events = _pbp_events(row)
    if events is None:
        return NAN
    return float(sum(1 for e in events if "foul" in str(e.get("text") or "").lower()))


def star_on_floor(row: Dict[str, Any], star_names: Set[str]) -> Optional[bool]:
    """None (honest unknown) unless the pbp tail is available AND carries
    on_floor participants AND a usable star list exists for this sport."""
    events = _pbp_events(row)
    if not events or not star_names:
        return None
    names: List[str] = []
    for e in events:
        of = e.get("on_floor")
        if isinstance(of, list):
            names.extend(of)
    if not names:
        return None
    normed = {_norm_name(n) for n in names}
    return bool(normed & set(star_names))


# --------------------------------------------------------------------------- #
# Frame assembly
# --------------------------------------------------------------------------- #

def build_features_frame(rows: Sequence[Dict[str, Any]], *,
                         star_names: Optional[Set[str]] = None) -> pd.DataFrame:
    """Pure: rows -> one feature row per (game_id, capture_ts). margin_velocity
    is the only cross-row feature -- delta vs the PREVIOUS tick for the same
    game_id, once sorted by capture_ts (NaN on a game's first captured tick)."""
    star_names = star_names or set()
    records = []
    for row in rows:
        records.append({
            "game_id": row.get("game_id"), "sport": row.get("sport"),
            "capture_ts": row.get("capture_ts"),
            "home": row.get("home"), "away": row.get("away"),
            "score_home": row.get("score_home"), "score_away": row.get("score_away"),
            "score_margin": score_margin(row),
            "winprob_market_gap": winprob_market_gap(row),
            "recent_scoring_run": recent_scoring_run(row),
            "foul_count_tail": foul_count_tail(row),
            "star_on_floor": star_on_floor(row, star_names),
        })
    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df
    df = df.sort_values(["game_id", "capture_ts"]).reset_index(drop=True)
    df["margin_velocity"] = df.groupby("game_id")["score_margin"].diff()
    return df


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build a per-tick in-game feature frame from a day's tip_capture ingame file.")
    ap.add_argument("--sport", required=True)
    ap.add_argument("--date", required=True, help="capture date YYYY-MM-DD")
    ap.add_argument("--in-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--profiles-path", default=None)
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--attribute", default=DEFAULT_USAGE_ATTRIBUTE)
    a = ap.parse_args(argv)

    rows = load_day_rows(a.sport, a.date, in_dir=Path(a.in_dir) if a.in_dir else None)
    star_names = load_top_usage_names(a.sport, parquet_path=a.profiles_path,
                                      top_n=a.top_n, attribute=a.attribute)
    df = build_features_frame(rows, star_names=star_names)

    out_dir = Path(a.out_dir) if a.out_dir else DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{a.sport.lower()}_{a.date}.parquet"
    df.to_parquet(out_path, index=False)
    print(json.dumps({"rows_in": len(rows), "rows_out": len(df), "out_path": str(out_path)}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "DEFAULT_IN_DIR", "DEFAULT_OUT_DIR", "DEFAULT_PROFILES_DIR", "DEFAULT_USAGE_ATTRIBUTE",
    "load_day_rows", "load_top_usage_names", "score_margin", "market_home_prob",
    "winprob_market_gap", "recent_scoring_run", "foul_count_tail", "star_on_floor",
    "build_features_frame", "main",
]
