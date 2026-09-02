"""S10 -- modern (2022+) MLB close derived from the local price series.

data/domains/mlb/odds.parquet stops at 2021-11-02 while games_current.parquet runs
to 2026-07-12, so no decimal close exists for the modern spine.  The only local
modern quote source is data/cache/inplay_odds/mlb_price_series.parquet (13,473,591
rows, game_date 2023-03-30..2026-07-09).  Its ``ts`` is EPOCH SECONDS (median
1760842744 -> 2025-10-19 UTC) and its ``prob`` is already a probability, so a
two-sided quote is devigged by feeding 1/prob as a decimal price through the
EXISTING close_join.close_column (which calls devig2) -- no second devig here.

FIRST PITCH: the only local first-pitch clock is the Kalshi event key
(KXMLBGAME-<yy><MON><dd><hhmm><away><home>, hhmm in ET).  Verified against
close_time: median(close_time - start_ET) = 2.85 h, a normal MLB game length,
where the UTC reading gives 6.85 h.  Polymarket rows carry NO close_time and no
start clock, so a Polymarket game with no Kalshi twin has NO certified
pre-first-pitch tick and is dropped with reason ``no_first_pitch_time``.

CLOSE KINDS: ``DEVIG_TWO_SIDED`` (both sides present, devigged -- the only kind
counted in the headline join rate) and ``PROXY_ONE_SIDED`` (a single-side last
pre-start tick, reported separately and labelled on every row; it carries the
venue's vig and is NOT a fair close).  Neither is a settled exchange close: both
are the LAST TICK STRICTLY BEFORE first pitch.

Calibration evidence only.  Read-only: nothing under data/ is written.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/eval_gate/test_close_join_mlb.py -q
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.close_join import JoinSpec, close_column

_ROOT = Path(__file__).resolve().parents[3]
SPINE_PATH = _ROOT / "data" / "domains" / "mlb" / "games_current.parquet"
SERIES_PATH = _ROOT / "data" / "cache" / "inplay_odds" / "mlb_price_series.parquet"
CORPUS_PATH = _ROOT / "data" / "cache" / "combo" / "gate_corpus_mlb.parquet"

MLB_SPEC = JoinSpec(
    sport="mlb", spine="event_id", date_col="date",
    side_a="ml_close_home_dec", side_b="ml_close_away_dec",
    fallback_a="ml_close_home_dec", fallback_b="ml_close_away_dec",
    name_a="home_win", name_b="away_win",
)

# Kalshi/Polymarket team tokens -> the games_current.parquet code alphabet.
# EXACT match only (the 2026-06-25 prop-settler bug): an unmapped token is an
# honest drop, never a fuzzy guess.  Unlisted tokens pass through upper-cased.
_TOKEN_TO_SPINE = {
    "AZ": "ARI", "ATH": "OAK", "CHC": "CUB", "KC": "KAN",
    "SD": "SDG", "SF": "SFO", "TB": "TAM", "WSH": "WAS",
}
_SPINE_CODES = frozenset(
    "ARI ATL BAL BOS CIN CLE COL CUB CWS DET HOU KAN LAA LAD MIA MIL MIN NYM "
    "NYY OAK PHI PIT SDG SEA SFO STL TAM TEX TOR WAS".split()
)
# The 30 venue-side tokens: the identity codes plus the 8 renamed ones.
_VENUE_TOKENS = frozenset(
    (_SPINE_CODES - set(_TOKEN_TO_SPINE.values())) | set(_TOKEN_TO_SPINE)
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
_TICKER = re.compile(r"^KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})([A-Z]+)$")
_SLUG = re.compile(r"^mlb-([a-z0-9]+)-([a-z0-9]+)-(\d{4}-\d{2}-\d{2})$")
# ponytail: the MLB regular season (Apr-Oct) is entirely EDT, so one fixed
# UTC-4 offset is exact here; add a tz table only if a March/November game
# with a Kalshi ticker ever appears.
_ET_OFFSET_H = 4


def _spine_code(token: str) -> str | None:
    code = _TOKEN_TO_SPINE.get(token.upper(), token.upper())
    return code if code in _SPINE_CODES else None


def _split_blob(blob: str, sides: list[str]) -> tuple[str, str] | None:
    """Split a Kalshi away+home blob; require exactly one valid token split.

    Ambiguity is resolved only by the event's OWN observed side tokens -- never
    by picking the first split, which is how a mis-bind manufactures a close for
    the wrong game.
    """
    hits = [(blob[:i], blob[i:]) for i in range(2, len(blob) - 1)
            if blob[:i] in _VENUE_TOKENS and blob[i:] in _VENUE_TOKENS]
    if len(hits) > 1:
        seen = {s.upper() for s in sides}
        hits = [h for h in hits if set(h) <= seen] or hits
    return hits[0] if len(hits) == 1 else None


def _kalshi_events(frame: pd.DataFrame, drops: dict[str, int]) -> pd.DataFrame:
    """One row per Kalshi event: first-pitch UTC plus the spine team codes."""
    rows = []
    for key, block in frame.groupby("event_key", sort=False):
        match = _TICKER.match(str(key))
        if match is None:
            drops["unparsed_ticker"] += 1
            continue
        yy, mon, dd, hh, mi, blob = match.groups()
        split = _split_blob(blob, sorted(block["side"].astype(str).unique()))
        if split is None:
            drops["unknown_team_token"] += 1
            continue
        away, home = (_spine_code(split[0]), _spine_code(split[1]))
        if away is None or home is None:
            drops["unknown_team_token"] += 1
            continue
        start = pd.Timestamp(2000 + int(yy), _MONTHS[mon], int(dd), int(hh), int(mi))
        rows.append({"event_key": key, "start_utc": start + pd.Timedelta(hours=_ET_OFFSET_H),
                     "home": home, "away": away,
                     "date": pd.Timestamp(start.date())})
    return pd.DataFrame(rows, columns=["event_key", "start_utc", "home", "away", "date"])


def _last_pre_start(ticks: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Last tick strictly before first pitch, per key + side."""
    pre = ticks.loc[ticks["ts_utc"] < ticks["start_utc"]]
    return pre.sort_values("ts").groupby(keys + ["side"], sort=False).tail(1)


def _devig(wide: pd.DataFrame) -> pd.Series:
    """Devig a two-sided probability pair by reusing close_join.close_column."""
    prices = pd.DataFrame({
        MLB_SPEC.side_a: 1.0 / wide["prob_home"].to_numpy(float),
        MLB_SPEC.side_b: 1.0 / wide["prob_away"].to_numpy(float),
    }, index=wide.index)
    return close_column(prices, MLB_SPEC)


def derive_modern_close(series_path: Path | str = SERIES_PATH,
                        spine: pd.DataFrame | None = None) -> pd.DataFrame:
    """Reduce the price series to <=1 pre-first-pitch quote per spine event_id.

    Returns event_id, close_prob, close_kind, venue.  Drop counts by reason ride
    on ``.attrs`` -- every candidate game is either joined or counted, never
    silently lost.
    """
    if spine is None:
        spine = pd.read_parquet(SPINE_PATH)
    spine = spine.copy()
    spine["date"] = pd.to_datetime(spine["date"])
    drops = {k: 0 for k in (
        "unparsed_ticker", "unknown_team_token", "no_pre_start_quote",
        "one_sided_proxy", "no_first_pitch_time", "ambiguous_spine_key",
        "no_spine_match", "bad_price_drop_count", "null_close_count")}

    series = pd.read_parquet(series_path)
    series = series.loc[series["market_type"].astype(str) == "moneyline"].copy()
    series["ts_utc"] = pd.to_datetime(series["ts"], unit="s")
    kal = series.loc[series["venue"].astype(str) == "kalshi"]
    poly = series.loc[series["venue"].astype(str) == "polymarket"]

    events = _kalshi_events(kal, drops)
    quotes: list[pd.DataFrame] = []
    if len(events):
        ticks = kal.merge(events[["event_key", "start_utc"]], on="event_key", how="inner")
        last = _last_pre_start(ticks, ["event_key"])
        last["seat"] = np.where(
            last["side"].map(lambda s: _spine_code(str(s))).to_numpy()
            == last["event_key"].map(events.set_index("event_key")["home"]).to_numpy(),
            "prob_home", "prob_away")
        wide = last.pivot_table(index="event_key", columns="seat", values="prob", aggfunc="last")
        for col in ("prob_home", "prob_away"):
            if col not in wide:
                wide[col] = np.nan
        wide = wide.join(events.set_index("event_key")[["home", "away", "date"]], how="inner")
        drops["no_pre_start_quote"] += int(len(events) - len(wide))
        both = wide["prob_home"].notna() & wide["prob_away"].notna()
        two = wide.loc[both].copy()
        if len(two):
            close = _devig(two)
            drops["bad_price_drop_count"] += int(close.attrs["bad_price_drop_count"])
            drops["null_close_count"] += int(close.attrs["null_close_count"])
            two["close_prob"] = close.to_numpy(float)
            two["close_kind"] = "DEVIG_TWO_SIDED"
            quotes.append(two.loc[two["close_prob"].notna()])
        one = wide.loc[~both].copy()
        drops["one_sided_proxy"] += int(len(one))
        if len(one):
            one["close_prob"] = one["prob_home"].where(
                one["prob_home"].notna(), 1.0 - one["prob_away"])
            one["close_kind"] = "PROXY_ONE_SIDED"
            quotes.append(one)

    # Polymarket carries only the home side and no clock; it can only borrow a
    # first pitch from a Kalshi twin, and is always a one-sided PROXY.
    slugs = poly["ticker_or_slug"].astype(str).str.extract(_SLUG)
    poly = poly.assign(away=slugs[0].map(lambda t: _spine_code(str(t)) if pd.notna(t) else None),
                       home=slugs[1].map(lambda t: _spine_code(str(t)) if pd.notna(t) else None),
                       date=pd.to_datetime(slugs[2], errors="coerce"))
    poly = poly.loc[poly["home"].notna() & poly["away"].notna() & poly["date"].notna()]
    if len(poly):
        starts = events.drop_duplicates(["date", "home", "away"]) if len(events) else events
        poly = poly.merge(starts[["date", "home", "away", "start_utc"]],
                          on=["date", "home", "away"], how="left")
        missing = poly.loc[poly["start_utc"].isna(), "ticker_or_slug"].nunique()
        drops["no_first_pitch_time"] += int(missing)
        seen = poly.loc[poly["start_utc"].notna()]
        if len(seen):
            last = _last_pre_start(seen, ["ticker_or_slug", "home", "away", "date"])
            last = last.assign(close_prob=last["prob"].astype(float),
                               close_kind="PROXY_ONE_SIDED")
            quotes.append(last[["home", "away", "date", "close_prob", "close_kind"]])

    if not quotes:
        out = pd.DataFrame(columns=["event_id", "close_prob", "close_kind"])
        out.attrs = drops
        return out
    cand = pd.concat([q.reset_index()[["home", "away", "date", "close_prob", "close_kind"]]
                      for q in quotes], ignore_index=True)
    # A devigged two-sided quote always outranks a one-sided proxy for the same game.
    cand["rank"] = (cand["close_kind"] == "DEVIG_TWO_SIDED").astype(int)
    cand = cand.sort_values("rank", ascending=False).drop_duplicates(["home", "away", "date"])

    keys = ["date", "home_team", "away_team"]
    ambiguous = spine.duplicated(keys, keep=False)
    drops["ambiguous_spine_key"] += int(ambiguous.sum())
    lookup = spine.loc[~ambiguous, keys + ["event_id"]].rename(
        columns={"home_team": "home", "away_team": "away"})
    joined = cand.merge(lookup, on=["date", "home", "away"], how="left")
    drops["no_spine_match"] += int(joined["event_id"].isna().sum())
    out = joined.loc[joined["event_id"].notna(),
                     ["event_id", "close_prob", "close_kind"]].reset_index(drop=True)
    out.attrs = drops
    return out


def _brier(p: np.ndarray, y: np.ndarray) -> float | None:
    return float(np.mean((p - y) ** 2)) if len(y) else None


def coverage_report_mlb(series_path: Path | str = SERIES_PATH,
                        spine: pd.DataFrame | None = None) -> dict[str, Any]:
    """Join rate of a modern devigged close onto the FULL games_current spine.

    The denominator is every spine row, INCLUDING the 2022 and 2024 seasons no
    local source can cover -- restricting it to seasons that happen to hold
    quotes would be the circular metric B1 forbids.
    """
    if spine is None:
        spine = pd.read_parquet(SPINE_PATH)
    spine = spine.copy()
    spine["date"] = pd.to_datetime(spine["date"])
    close = derive_modern_close(series_path, spine)
    frame = spine[["event_id", "date", "target_home_win"]].merge(
        close, on="event_id", how="left", validate="one_to_one")
    frame["y"] = frame["target_home_win"].astype(float)
    if CORPUS_PATH.exists():
        corpus = pd.read_parquet(CORPUS_PATH)[["event_id", "p_base", "p_home_elo"]]
        frame = frame.merge(corpus.drop_duplicates("event_id"), on="event_id", how="left")
    else:  # pragma: no cover -- corpus is a read-only convenience, never required
        frame["p_base"] = np.nan
        frame["p_home_elo"] = np.nan

    def block(sub: pd.DataFrame) -> dict[str, Any]:
        strict = sub["close_kind"].eq("DEVIG_TWO_SIDED")
        fit = sub.loc[strict & sub["close_prob"].notna() & sub["y"].notna()]
        out = {
            "denominator": int(len(sub)),
            "joined_devig": int(strict.sum()),
            "joined_proxy": int(sub["close_kind"].eq("PROXY_ONE_SIDED").sum()),
            "join_rate": float(strict.sum() / len(sub)) if len(sub) else 0.0,
            "scored": int(len(fit)),
            "brier_devig_close": _brier(fit["close_prob"].to_numpy(float), fit["y"].to_numpy(float)),
        }
        for col in ("p_base", "p_home_elo"):
            ok = fit.loc[fit[col].notna()] if col in fit else fit.iloc[:0]
            out[f"brier_{col}"] = _brier(ok[col].to_numpy(float), ok["y"].to_numpy(float)) if len(ok) else None
        return out

    report = {"sport": "mlb", "spine_rows": int(len(spine)),
              "close_source": "mlb_price_series.parquet (last tick strictly before first pitch)",
              "vintage": "PRE_FIRST_PITCH_TICK (not a settled exchange close)",
              **block(frame),
              "by_season": {str(year): block(sub)
                            for year, sub in frame.groupby(frame["date"].dt.year, sort=True)},
              "drops": dict(close.attrs)}
    return report


__all__ = ["MLB_SPEC", "derive_modern_close", "coverage_report_mlb"]
