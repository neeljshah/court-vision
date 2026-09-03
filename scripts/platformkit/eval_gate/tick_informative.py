"""S87 -- tick informativeness flags for in-game scored corpora.

Every published in-game CI is quoted against a raw tick count, but most ticks
repeat the previous quote: on `data/cache/ingame_grade_joined/mlb` roughly 70 pct
of ticks carry no new market AND no new model number.  This module adds the four
flags (`is_dup`, `is_held_market`, `is_held_model`, `is_informative`) and the
matching counts so a readout can quote n / n_informative / n_eff side by side.

Held is the complement of `ingame.quote_freshness.freshness_mask` (FRESH iff the
probability moved by more than eps), computed here frame-wise instead of per-game
sequence-wise.  ESS/ICC is NOT reimplemented -- it is
`ingame.gap_effective_n.effective_sample_size`.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

EPS = 1e-9
FLAG_COLUMNS = ("is_dup", "is_held_market", "is_held_model", "is_informative")
_TS_KEY = "_tick_ts_key"    # S130 scratch column, dropped before the frame is returned


def _ts_key(values: pd.Series) -> pd.Series:
    """The COMPARABLE form of a timestamp column: UTC datetimes when it parses as one.

    S130: `2026-09-03T00:00:00Z` and `2026-09-03T00:00:00+00:00` are the same instant,
    but as raw strings they are two ticks, so a duplicate read as informative. A column
    that is not a timestamp at all (a synthetic `t0`/`t1`, or an integer sequence number)
    falls back to its own values rather than becoming NaT -- a partial parse is not
    trusted, because half a column of NaT would collapse every unparsed row into one dup.
    """
    with warnings.catch_warnings():          # "could not infer format" is expected here
        warnings.simplefilter("ignore", UserWarning)
        parsed = pd.to_datetime(values, utc=True, errors="coerce")
    return parsed if parsed.notna().all() else values


def _held(frame: pd.DataFrame, game_col: str, value_col: str, eps: float) -> pd.Series:
    """True where value_col repeats the previous row of the same game within eps.

    The first tick of a game has no predecessor and is never held (it is new
    information), matching `quote_freshness.freshness_mask` row 0.  A non-numeric
    or missing value is conservatively treated as NOT held (it cannot be confirmed
    to repeat), so it never silently deletes a tick from the informative set.
    """
    values = pd.to_numeric(frame[value_col], errors="coerce")
    previous = values.groupby(frame[game_col].astype(str), sort=False).shift(1)
    return ((values - previous).abs() <= eps).fillna(False)


def flag_ticks(
    frame: pd.DataFrame,
    *,
    game_col: str = "game",
    ts_col: str = "timestamp",
    market_col: str = "market",
    model_col: str = "model",
    loss_col: Optional[str] = None,
    eps: float = EPS,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Return (frame + flag columns, summary counts).

    S130: the rows are normalised HERE, not by one of the two callers -- the frame is
    stably sorted by (game, ts) and `ts` is compared as a UTC instant, so the flags no
    longer depend on the order the writer happened to score in or on how it spelled a
    timezone.  The returned frame carries that sorted order (its index is preserved, so
    a caller can restore its own).  Pure: the input frame is not modified.

    `is_dup`      -- a later row with a (game_col, ts_col) pair already seen.
    `is_held_*`   -- the quote repeats the previous tick of the same game.
    `is_informative` -- not a duplicate AND market or model moved.

    `n_eff_icc` is the clustered ESS of the INFORMATIVE subset via
    `effective_sample_size`; it is None when `loss_col` is not supplied (an ESS
    needs a per-tick loss differential and this module does not invent one).
    """
    required = [game_col, ts_col, market_col, model_col]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError("missing required columns: %s" % ", ".join(missing))
    out = frame.copy()
    if _TS_KEY in out.columns:
        raise ValueError("column %r is reserved by flag_ticks" % _TS_KEY)
    out[_TS_KEY] = _ts_key(out[ts_col])
    out = out.sort_values([game_col, _TS_KEY], kind="mergesort")   # stable: ties keep input order
    out["is_dup"] = out.duplicated(subset=[game_col, _TS_KEY], keep="first")
    out["is_held_market"] = _held(out, game_col, market_col, eps)
    out["is_held_model"] = _held(out, game_col, model_col, eps)
    out["is_informative"] = ~out["is_dup"] & ~(out["is_held_market"] & out["is_held_model"])
    out = out.drop(columns=[_TS_KEY])

    n_eff_icc = None
    if loss_col is not None:
        informative = out[out["is_informative"]]
        if not informative.empty:
            n_eff_icc = float(
                effective_sample_size(informative, game_column=game_col, loss_column=loss_col)["n_eff"]
            )
    summary = {
        "n": int(len(out)),
        "n_dup": int(out["is_dup"].sum()),
        "n_held_market": int(out["is_held_market"].sum()),
        "n_held_model": int(out["is_held_model"].sum()),
        "n_held_both": int((out["is_held_market"] & out["is_held_model"]).sum()),
        "n_informative": int(out["is_informative"].sum()),
        "n_games": int(out[game_col].nunique()),
        "n_eff_icc": n_eff_icc,
    }
    return out, summary


def attach_informative_summary(
    artifact: Dict[str, Any],
    frame: pd.DataFrame,
    loss_col: str,
    *,
    game_col: str = "game",
    ts_col: str = "timestamp",
    market_col: str = "market",
    model_col: str = "model",
    eps: float = EPS,
    key: str = "tick_informative",
) -> Dict[str, Any]:
    """S87 bar: write the n / n_informative / n_eff triple into `artifact[key]`.

    The artifact's OWN CI is never touched -- this only ADDS a second CI,
    `ci95_informative`, computed from the SAME per-tick paired losses on the
    informative rows only, beside the full-series CI the writer already publishes.

    S130: the (game, ts) sort moved INTO `flag_ticks`, which is where it has to be --
    `requote` called the same function without it and got different flags on the same
    rows.  `ci95_informative` is None when the informative subset has fewer than two
    game clusters (a DM CI needs two).
    """
    flagged, summary = flag_ticks(
        frame, game_col=game_col, ts_col=ts_col, market_col=market_col, model_col=model_col,
        loss_col=loss_col, eps=eps,
    )
    informative = flagged[flagged["is_informative"]]
    block: Dict[str, Any] = dict(summary)
    block["n_games_informative"] = int(informative[game_col].nunique())
    if block["n_games_informative"] >= 2:
        dm = diebold_mariano(informative[loss_col].astype(float).tolist(),
                             informative[game_col].astype(str).tolist())
        block["ci95_informative"] = [float(dm.ci95[0]), float(dm.ci95[1])]
        block["dm_p_informative"] = float(dm.p_value)
        block["mean_loss_differential_informative"] = float(dm.mean_diff)
    else:
        block["ci95_informative"] = None
        block["ci95_informative_absent_because"] = "fewer than 2 informative game clusters"
    block["note"] = ("S87: the headline CI stays as published (all rows); ci95_informative "
                     "re-quotes the same paired losses on informative ticks only. No bar moved.")
    artifact[key] = block
    return artifact

def _demo() -> None:
    frame = pd.DataFrame(
        {
            "game": ["g1", "g1", "g1", "g1", "g2"],
            "timestamp": ["t0", "t1", "t2", "t2", "t0"],
            "market": [0.5, 0.5, 0.6, 0.6, 0.4],
            "model": [0.5, 0.5, 0.5, 0.5, 0.4],
            "loss_differential": [0.01, 0.0, -0.02, -0.02, 0.03],
        }
    )
    flagged, summary = flag_ticks(frame, loss_col="loss_differential")
    assert list(flagged["is_dup"]) == [False, False, False, True, False]
    assert list(flagged["is_held_market"]) == [False, True, False, True, False]
    assert list(flagged["is_held_model"]) == [False, True, True, True, False]
    assert list(flagged["is_informative"]) == [True, False, True, False, True]
    assert summary["n"] == 5 and summary["n_dup"] == 1 and summary["n_informative"] == 3
    assert summary["n_games"] == 2 and summary["n_eff_icc"] is not None
    print("tick_informative demo OK:", summary)


# --- S87 re-quote CLI -------------------------------------------------------
# ponytail: the three archived artifacts are named literally, not discovered --
# this is a one-shot re-quote of published CIs, not a general framework.
_REPO = Path(__file__).resolve().parents[3]
_CACHE = _REPO / "data" / "cache" / "eval_gate"

_ARTIFACTS: Dict[str, Dict[str, Any]] = {
    "s58_trialA_clamp": {
        "csv": "s58_trialA_clamp_family_series_2026-09-03.csv",
        "json": "s58_trialA_clamp_family_2026-09-03.json",
        "game": "game", "ts": "timestamp", "market": "market", "model": "candidate",
        "loss": lambda f: (f["incumbent_e4_gd"] - f["y"]) ** 2 - (f["candidate"] - f["y"]) ** 2,
        "published_ci": ("dm", "ci95"), "published_verdict": ("verdict",),
        "note": "model side = the inner-selected clamp candidate; d = loss(incumbent e4_gd) - loss(candidate)",
    },
    "s58_trialB_nba_halftime": {
        "csv": "s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv",
        "json": "s58_trialB_nba_halftime_asof_2026-09-03.json",
        "game": "game_id", "ts": "game_date", "market": "market", "model": "model",
        "loss": lambda f: f["d"],
        "published_ci": ("pooled", "dm_ci95"), "published_verdict": ("verdict",),
        "note": "ONE row per game at the halftime anchor -- no tick sequence, so no row can be held or duplicated",
    },
    "s80_player_grain": {
        "csv": "s80_player_grain_2026-09-03.csv",
        "json": "s80_player_grain_2026-09-03.json",
        "game": "game", "ts": "timestamp", "market": "market_prob", "model": "p_candidate",
        "loss": lambda f: f["loss_differential"],
        "published_ci": ("dm", "ci95"), "published_verdict": ("verdict",),
        "note": "d = loss(incumbent e4) - loss(e4+player); SCREEN tier, uncharged",
    },
}


def _dig(blob: Mapping[str, Any], path: tuple) -> Any:
    for key in path:
        blob = blob[key]
    return blob


def _quote(frame: pd.DataFrame, game_col: str, loss_col: str) -> Dict[str, Any]:
    """DM (cluster-robust, by game) + clustered ESS for one row set."""
    dm = diebold_mariano(frame[loss_col].astype(float).tolist(), frame[game_col].astype(str).tolist())
    ess = effective_sample_size(frame, game_column=game_col, loss_column=loss_col)
    return {
        "n": int(len(frame)), "n_games": int(ess["n_games"]), "rho": float(ess["rho"]),
        "design_effect": float(ess["design_effect"]), "n_eff": float(ess["n_eff"]),
        "mean_loss_differential": float(dm.mean_diff), "dm_stat": float(dm.dm_stat),
        "dm_p": float(dm.p_value), "dm_ci95": [float(dm.ci95[0]), float(dm.ci95[1])],
        "ci_excludes_zero_favouring_candidate": bool(dm.ci95[0] > 0.0),
    }


def requote(name: str, cache: Path = _CACHE) -> Dict[str, Any]:
    """Re-quote one archived artifact's headline CI on informative ticks only.

    Recomputes NOTHING model-side: the archived per-tick paired losses are read as
    written and only the ROW SET changes.  The published CI is reproduced from the
    same CSV first; if that reproduction fails the caller must not read the new CI.
    """
    spec = _ARTIFACTS[name]
    frame = pd.read_csv(cache / spec["csv"], comment="#")
    frame["_d"] = spec["loss"](frame)
    flagged, summary = flag_ticks(
        frame, game_col=spec["game"], ts_col=spec["ts"], market_col=spec["market"],
        model_col=spec["model"], loss_col="_d",
    )
    before = _quote(flagged, spec["game"], "_d")
    after = _quote(flagged[flagged["is_informative"]], spec["game"], "_d")
    published = json.loads((cache / spec["json"]).read_text())
    published_ci = [float(v) for v in _dig(published, spec["published_ci"])]
    reproduced = max(abs(a - b) for a, b in zip(published_ci, before["dm_ci95"])) < 1e-9
    same_conclusion = (
        before["ci_excludes_zero_favouring_candidate"] == after["ci_excludes_zero_favouring_candidate"]
    )
    return {
        "artifact": name, "note": spec["note"], "series_csv": spec["csv"], "summary_json": spec["json"],
        "published_verdict": _dig(published, spec["published_verdict"]),
        "published_ci95": published_ci, "published_ci_reproduced_from_series": bool(reproduced),
        "tick_flags": summary, "before_all_rows": before, "after_informative": after,
        "verdict_status": ("unchanged" if same_conclusion else "RE-LABEL REQUIRED"),
        "bars_not_recomputed": "no charge, no seal: multiplicity bars are NOT re-run, so a blocked verdict stays blocked",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="S87: re-quote archived in-game CIs on informative ticks")
    parser.add_argument("--out", default=str(_CACHE / "s87_requote_2026-09-03.json"))
    args = parser.parse_args(argv)
    results = [requote(name) for name in _ARTIFACTS]
    for row in results:
        flags, before, after = row["tick_flags"], row["before_all_rows"], row["after_informative"]
        print("%s | verdict %s | reproduced %s" % (row["artifact"], row["published_verdict"],
                                                   row["published_ci_reproduced_from_series"]))
        print("  n %d -> n_informative %d (dup %d, held market %d, held model %d, both %d)" % (
            flags["n"], flags["n_informative"], flags["n_dup"], flags["n_held_market"],
            flags["n_held_model"], flags["n_held_both"]))
        print("  n_eff %.2f -> %.2f | ci95 [%.6f, %.6f] -> [%.6f, %.6f] | %s" % (
            before["n_eff"], after["n_eff"], before["dm_ci95"][0], before["dm_ci95"][1],
            after["dm_ci95"][0], after["dm_ci95"][1], row["verdict_status"]))
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "gap": "S87",
               "tier": "RE-QUOTE (no charge, no seal, no model recomputed)", "results": results}
    Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True))
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        _demo()
    else:
        raise SystemExit(main())
