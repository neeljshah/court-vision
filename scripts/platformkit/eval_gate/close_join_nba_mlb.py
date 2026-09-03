"""S112 -- attach a market close to the NBA and MLB gate corpora (NEW files, never in place).

The nba and mlb gate corpora carry `p_base` = Elo as the incumbent (S98: `p_base == p_elo`
byte-identically), so every pregame result on those two sports is Elo-relative and says
nothing about the market.  This module attaches a `p_close` and writes NEW corpora
`data/cache/combo/gate_corpus_{nba,mlb}_close.parquet` plus build_gate_corpus-compatible
sidecars.  The LIVE `gate_corpus_{nba,mlb}.parquet` the pod runner reads are never touched.

CLOSE RULES, stated per sport:

* **mlb -- `pre_first_pitch_two_sided`.**  The LAST TRADED two-sided Kalshi quote strictly
  before the ticker's own first-pitch clock, devigged once (`ts_utc < start_utc`).  S133: the
  0.500 placeholder rule is applied to the RAW 0.500/0.500 listing BEFORE the devig -- a 0.500
  that comes OUT of an asymmetric quote is a genuine pick'em and is kept.
* **nba -- two sources, ranked.**  (1) `nba_close_corpus.parquet`, the polymarket last tick
  before `commence_time` -- genuinely PREGAME.  (2) the FIRST traded tick of
  `nba_checkpoints_full.parquet`, but S132: only when it is genuinely PRE-SCORING
  (`margin == 0`, `close_score_on_board == 0`, `close_sec_after_tip <= 30`).  Anything else
  already knows part of the answer (43.5 pct of those ticks carry points, up to 37, up to
  408 s after tip) and becomes `close_source = inplay_contaminated`, `p_close = NaN`.
  `allow_contaminated=True` reproduces the pre-S132 behaviour for A2 comparisons only.  Both
  nba sources are a SINGLE venue probability: `close_kind = VENUE_PROB_ONE_SIDED`, never a
  devigged fair close.
* **ambiguity never downgrades (S133).**  Two venue events naming one corpus event yield ONE
  row, `close_source = ambiguous`, `p_close = NaN`, ranked ABOVE the in-play tick.

Calibration evidence only.  No charge, no seal, no ledger read or write.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/eval_gate/test_close_join_nba_mlb.py -q
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from scripts.platformkit.combo import corpus_cache
from scripts.platformkit.eval_gate import close_join_mlb as cjm

_ROOT = Path(__file__).resolve().parents[3]
CHECKPOINTS = _ROOT / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
NBA_PREGAME_CLOSE = _ROOT / "data" / "cache" / "venue_history" / "nba_close_corpus.parquet"
GAMES_NBA = _ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"

PLACEHOLDER_PROB = 0.5          # the untraded venue listing quote (S81); never a real close
TIP_WINDOW_S = 30.0             # the WITHIN-30-S-OF-TIP rule, stated not hidden
PERIOD_LENGTH_S = 720.0         # one NBA period, to turn game_clock_s into seconds after tip
CLOSE_COLUMNS = ("p_close", "close_ts", "close_source", "close_kind",
                 "close_sec_after_tip", "close_within_30s", "close_score_on_board")
_DROP_KEYS = ("placeholder_half", "ambiguous_event_id", "unbridged_game",
              "first_tick_not_period_1", "no_spine_match", "not_in_gate_corpus",
              "inplay_contaminated")
# S133: nba source priority. `ambiguous` outranks the in-play tick so a dropped pregame
# close can never fall through to it silently.
_SOURCE_RANK = {"pregame_last_tick_before_commence": 3, "ambiguous": 2,
                "first_inplay_tick": 1, "inplay_contaminated": 0}


def _drops() -> Dict[str, int]:
    return {k: 0 for k in _DROP_KEYS}


def _drop_placeholder(frame: pd.DataFrame, drops: Dict[str, int]) -> pd.DataFrame:
    """An exactly-0.500 ONE-SIDED venue quote is the listing placeholder, not a price (B9).

    Never applied to a devigged two-sided value -- see `mlb_close` (S133).
    """
    keep = frame["p_close"].astype(float).to_numpy() != PLACEHOLDER_PROB
    drops["placeholder_half"] += int((~keep).sum())
    return frame.loc[keep]


def _mark_ambiguous(frame: pd.DataFrame, drops: Dict[str, int]) -> pd.DataFrame:
    """Two venue events naming one corpus event: keep ONE priceless row that says so (S133)."""
    dup = frame["event_id"].duplicated(keep=False).to_numpy()
    drops["ambiguous_event_id"] += int(dup.sum())
    if not dup.any():
        return frame
    marked = frame.loc[dup].drop_duplicates("event_id").assign(p_close=np.nan,
                                                              close_source="ambiguous")
    return pd.concat([frame.loc[~dup], marked], ignore_index=True)


# --- NBA ------------------------------------------------------------------- #

def nba_pregame_close(path: Path | str = NBA_PREGAME_CLOSE,
                      drops: Dict[str, int] | None = None) -> pd.DataFrame:
    """The polymarket last tick before commence_time -- a real pregame close (663 games)."""
    drops = _drops() if drops is None else drops
    raw = pd.read_parquet(path)
    out = pd.DataFrame({
        "event_id": raw["game_id"].astype(str),
        "p_close": raw["close_prob_home"].astype(float),
        "close_ts": raw["close_ts"].astype(str),
        "close_source": "pregame_last_tick_before_commence",
        "close_kind": "VENUE_PROB_ONE_SIDED",
        # BEFORE the tip, so seconds-after-tip is negative by construction.
        "close_sec_after_tip": -raw["seconds_before_tip"].astype(float),
        "close_score_on_board": 0.0,      # before the tip by construction
    })
    out["close_within_30s"] = out["close_sec_after_tip"].abs() <= TIP_WINDOW_S
    return _mark_ambiguous(_drop_placeholder(out, drops), drops).reset_index(drop=True)


def nba_first_inplay_tick(path: Path | str = CHECKPOINTS,
                          drops: Dict[str, int] | None = None,
                          allow_contaminated: bool = False) -> pd.DataFrame:
    """Each priced game's FIRST traded tick, bridged to the nba-stats game_id.

    The bridge is the incumbent's own crosswalk (`nba_mechanism_ladder.build_crosswalk`:
    market-ticker tricode pair + date within +/-1 day, kept only when the venue outcome agrees
    with games.parquet), exactly as S84 and S98 used it -- not a new identity join.
    """
    from scripts.platformkit.ingame.nba_mechanism_ladder import build_crosswalk

    drops = _drops() if drops is None else drops
    ticks = pd.read_parquet(path, columns=[
        "game_id", "game_date", "ts", "period", "game_clock_s", "market_prob", "traded",
        "market_ticker", "outcome_home_win", "score_home", "score_away", "margin"])
    ticks = ticks.loc[ticks["traded"].astype(bool)].copy()
    ticks["game_id"] = ticks["game_id"].astype(str)
    crosswalk = build_crosswalk(ticks[["game_id", "game_date", "market_ticker", "outcome_home_win"]])
    crosswalk["game_id"] = crosswalk["game_id"].astype(str)
    crosswalk["nba_game_id"] = crosswalk["nba_game_id"].astype(str)

    first = ticks.sort_values("ts").groupby("game_id", sort=False).head(1).copy()
    in_period_1 = first["period"].astype(int) == 1
    drops["first_tick_not_period_1"] += int((~in_period_1).sum())
    first = first.loc[in_period_1]
    n_priced = int(len(first))
    first = first.merge(crosswalk[["game_id", "nba_game_id"]], on="game_id", how="left")
    drops["unbridged_game"] += int(first["nba_game_id"].isna().sum())
    first = first.loc[first["nba_game_id"].notna()]

    out = pd.DataFrame({
        "event_id": first["nba_game_id"].astype(str).to_numpy(),
        "p_close": first["market_prob"].astype(float).to_numpy(),
        "close_ts": pd.to_datetime(first["ts"], unit="s").dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(),
        "close_source": "first_inplay_tick",
        "close_kind": "VENUE_PROB_ONE_SIDED",
        "close_sec_after_tip": (PERIOD_LENGTH_S - first["game_clock_s"].astype(float)).to_numpy(),
        "close_score_on_board": (first["score_home"].astype(float)
                                 + first["score_away"].astype(float)).to_numpy(),
    })
    out["close_within_30s"] = out["close_sec_after_tip"].abs() <= TIP_WINDOW_S
    out["_margin"] = first["margin"].astype(float).abs().to_numpy()
    out = _mark_ambiguous(_drop_placeholder(out, drops), drops).reset_index(drop=True)
    # S132: only a genuinely PRE-SCORING tick is a close. Everything else is labelled and
    # carries no price -- it already knows part of the answer it is used to score.
    is_tick = (out["close_source"] == "first_inplay_tick").to_numpy()
    clean = (is_tick & (out["close_score_on_board"].to_numpy() == 0.0)
             & (out["_margin"].to_numpy() == 0.0) & out["close_within_30s"].to_numpy())
    if not allow_contaminated:
        bad = is_tick & ~clean
        drops["inplay_contaminated"] += int(bad.sum())
        out.loc[bad, "close_source"] = "inplay_contaminated"
        out.loc[bad, "p_close"] = np.nan
    out = out.drop(columns="_margin")
    out.attrs["n_priced_games"] = n_priced
    return out


def nba_close(drops: Dict[str, int] | None = None,
              allow_contaminated: bool = False) -> pd.DataFrame:
    """Both nba sources, ranked by `_SOURCE_RANK` -- a priceless higher-ranked row still wins."""
    drops = _drops() if drops is None else drops
    # Module globals read at CALL time so a caller (and the per-file test) can repoint them.
    pregame = nba_pregame_close(NBA_PREGAME_CLOSE, drops=drops)
    tick = nba_first_inplay_tick(CHECKPOINTS, drops=drops,
                                 allow_contaminated=allow_contaminated)
    both = pd.concat([pregame, tick], ignore_index=True)
    both["rank"] = both["close_source"].map(_SOURCE_RANK).fillna(0.0)
    both = both.sort_values("rank", ascending=False, kind="stable")
    return both.drop_duplicates("event_id").drop(columns="rank").reset_index(drop=True)


# --- MLB ------------------------------------------------------------------- #

def mlb_close(series_path: Path | str = None, spine: pd.DataFrame | None = None,
              drops: Dict[str, int] | None = None) -> pd.DataFrame:
    """Last TRADED two-sided Kalshi quote strictly before first pitch, devigged.

    Mirrors `s81_market_move._mlb_open_close`'s close leg (the per-file test asserts the two
    agree event-for-event) and adds the quote's own timestamp, which that helper drops.
    """
    drops = _drops() if drops is None else drops
    series = pd.read_parquet(cjm.SERIES_PATH if series_path is None else series_path)
    series = series.loc[(series["market_type"].astype(str) == "moneyline")
                        & series["traded"].astype(bool)
                        & (series["venue"].astype(str) == "kalshi")].copy()
    series["ts_utc"] = pd.to_datetime(series["ts"], unit="s")
    events = cjm._kalshi_events(series, {"unparsed_ticker": 0, "unknown_team_token": 0})
    if not len(events):
        return pd.DataFrame(columns=list(("event_id",) + CLOSE_COLUMNS))
    ticks = series.merge(events[["event_key", "start_utc"]], on="event_key", how="inner")
    pre = ticks.loc[ticks["ts_utc"] < ticks["start_utc"]].sort_values("ts")
    home = events.set_index("event_key")["home"]
    seat = np.where(pre["side"].map(lambda s: cjm._spine_code(str(s))).to_numpy()
                    == pre["event_key"].map(home).to_numpy(), "prob_home", "prob_away")
    last = pre.assign(seat=seat).groupby(["event_key", "seat"], sort=False).tail(1)
    wide = last.pivot_table(index="event_key", columns="seat", values="prob", aggfunc="last")
    for column in ("prob_home", "prob_away"):
        if column not in wide:
            wide[column] = np.nan
    wide = wide.dropna(subset=["prob_home", "prob_away"])
    # S133: the placeholder is the RAW 0.500/0.500 listing. A 0.500 that comes OUT of the
    # devig of an asymmetric quote is a genuine pick'em, so the rule runs BEFORE the devig.
    raw_half = ((wide["prob_home"].astype(float) == PLACEHOLDER_PROB)
                & (wide["prob_away"].astype(float) == PLACEHOLDER_PROB))
    drops["placeholder_half"] += int(raw_half.sum())
    wide = wide.loc[~raw_half.to_numpy()]
    devig = cjm._devig(wide)
    stamp = last.groupby("event_key")["ts"].max().reindex(wide.index)

    frame = pd.DataFrame({
        "event_key": wide.index.to_numpy(),
        "p_close": devig.to_numpy(dtype=float),
        "close_ts": pd.to_datetime(stamp, unit="s").dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(),
        "close_source": "pre_first_pitch_two_sided",
        "close_kind": "DEVIG_TWO_SIDED",
        "close_sec_after_tip": (
            stamp.to_numpy(dtype=float)
            - events.set_index("event_key")["start_utc"].reindex(wide.index)
            .astype("int64").to_numpy() / 1e9),
    })
    frame["close_within_30s"] = False   # a pre-first-pitch quote is never a tip-window quote
    frame["close_score_on_board"] = 0.0  # before first pitch by construction
    frame = frame.loc[np.isfinite(frame["p_close"].to_numpy(dtype=float))]

    spine = pd.read_parquet(cjm.SPINE_PATH) if spine is None else spine.copy()
    spine["date"] = pd.to_datetime(spine["date"])
    keys = ["date", "home_team", "away_team"]
    lookup = spine.loc[~spine.duplicated(keys, keep=False), keys + ["event_id"]].rename(
        columns={"home_team": "home", "away_team": "away"})
    bridged = events.merge(lookup, on=["date", "home", "away"], how="left").set_index("event_key")
    frame["event_id"] = bridged["event_id"].reindex(frame["event_key"]).to_numpy()
    drops["no_spine_match"] += int(pd.isna(frame["event_id"]).sum())
    frame = frame.loc[frame["event_id"].notna()].drop(columns="event_key")
    frame["event_id"] = frame["event_id"].astype(str)
    return _mark_ambiguous(frame, drops).reset_index(drop=True)


# --- The new corpora ------------------------------------------------------- #

CLOSE_BUILDERS = {"nba": nba_close, "mlb": mlb_close}
SOURCES = {"nba": (CHECKPOINTS, NBA_PREGAME_CLOSE, GAMES_NBA),
           "mlb": (cjm.SERIES_PATH, cjm.SPINE_PATH)}


def close_corpus_path(sport: str) -> Path:
    return corpus_cache._CACHE_DIR / ("gate_corpus_%s_close.parquet" % sport)


def _close_sidecar_path(sport: str) -> Path:
    return corpus_cache._CACHE_DIR / ("gate_corpus_%s_close.sources.json" % sport)


def build_close_corpus(sport: str, allow_contaminated: bool = False) -> Dict[str, Any]:
    """Write gate_corpus_<sport>_close.parquet + a portable sidecar; ADDITIVE only.

    Every column of the live corpus is carried through byte-for-byte and the seven close
    columns are appended, so a reader of the live corpus reads the same values here.  The
    live `gate_corpus_<sport>.parquet` is opened read-only and never rewritten (the pod
    runner reads it through the S68 sidecars).
    """
    if sport not in CLOSE_BUILDERS:
        raise ValueError("no close rule for %r; nba and mlb only" % sport)
    drops = _drops()
    base = corpus_cache.load_gate_corpus(sport).copy()
    base["event_id"] = base["event_id"].astype(str)
    extra = {"allow_contaminated": allow_contaminated} if sport == "nba" else {}
    close = CLOSE_BUILDERS[sport](drops=drops, **extra)
    drops["not_in_gate_corpus"] += int((~close["event_id"].isin(set(base["event_id"]))).sum())
    merged = base.merge(close, on="event_id", how="left", validate="one_to_one")
    if list(merged.columns[:len(base.columns)]) != list(base.columns):
        raise ValueError("close attach reordered the live corpus columns (B2)")

    path = close_corpus_path(sport)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path, index=False)
    sources = [Path(p) for p in SOURCES[sport] if Path(p).exists()]
    sources.append(corpus_cache._corpus_path(sport))
    manifest = {
        "sport": "%s_close" % sport, "built_at": time.time(), "n_rows": len(merged),
        "corpus_sha256": corpus_cache._file_sha256(path),
        "sources": corpus_cache._source_manifest(sources),
        "provenance": {c: {"lane": "S112", "rule": str(close["close_source"].iloc[0])
                           if len(close) else "none"} for c in CLOSE_COLUMNS},
    }
    _close_sidecar_path(sport).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    covered = merged["p_close"].notna()
    return {
        "sport": sport, "path": path.as_posix(), "sidecar": _close_sidecar_path(sport).as_posix(),
        "corpus_sha256": manifest["corpus_sha256"], "n_rows": int(len(merged)),
        "n_base_rows": int(len(base)), "n_close": int(covered.sum()),
        "coverage": float(covered.mean()) if len(merged) else 0.0,
        "by_source": merged.loc[covered, "close_source"].value_counts().to_dict(),
        # every attached row, priced or not -- so the S132/S133 labels are visible
        "by_source_attached": merged["close_source"].value_counts(dropna=True).to_dict(),
        "by_kind": merged.loc[covered, "close_kind"].value_counts().to_dict(),
        "n_within_30s": int(merged.loc[covered, "close_within_30s"].fillna(False).sum()),
        "by_corpus_unit": merged.loc[covered, "corpus_unit"].astype(str).value_counts().to_dict(),
        "date_min": str(merged.loc[covered, corpus_cache.DATE_COL].min()),
        "date_max": str(merged.loc[covered, corpus_cache.DATE_COL].max()),
        "drops": dict(drops),
    }


def load_close_corpus(sport: str, portable: bool | None = None) -> pd.DataFrame:
    """Read the close corpus through corpus_cache's own loader (same staleness contract)."""
    return corpus_cache.load_gate_corpus("%s_close" % sport, portable=portable)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="S112 nba/mlb close attach")
    ap.add_argument("--sports", default="nba,mlb")
    ap.add_argument("--allow-contaminated", action="store_true",
                    help="S132: reproduce the pre-fix nba behaviour (A2 comparison only)")
    args = ap.parse_args(argv)
    for sport in [s for s in args.sports.split(",") if s]:
        report = build_close_corpus(sport, allow_contaminated=args.allow_contaminated)
        print(json.dumps(report, indent=1, sort_keys=True, default=str))
    return 0


__all__ = ["nba_close", "nba_pregame_close", "nba_first_inplay_tick", "mlb_close",
           "build_close_corpus", "load_close_corpus", "close_corpus_path", "CLOSE_COLUMNS"]

if __name__ == "__main__":
    raise SystemExit(main())
