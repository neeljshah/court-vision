"""S320 timestamp, settlement, and prefix-replay audit (VERSION b: 5 states per stratum)."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

SEED = 32020260908
DELAY_SECONDS = 60
STATES_PER_STRATUM = 5
EPS = 1e-9
NULL_EMBARGO_DAYS = 1
REQUIRED = ("game_id", "ts", "period", "game_clock_s", "margin", "market_prob", "game_date")
CHECKS = ("availability", "status", "polarity", "duplicate", "settlement")


def _clock_bucket(value: float) -> str:
    if value == 0:
        return "eq_0"
    if value < 60:
        return "lt_60"
    if value <= 300:
        return "60_300"
    return "gt_300"


def _margin_bucket(value: float) -> str:
    value = abs(value)
    return "0_3" if value <= 3 else "4_9" if value <= 9 else "10_plus"


def _stratum(row: pd.Series) -> str:
    return "p%s_m%s_c%s" % (int(row.period), _margin_bucket(float(row.margin)),
                               _clock_bucket(float(row.game_clock_s)))


def _state_ts(value: int) -> str:
    return pd.Timestamp(int(value), unit="s", tz="UTC").isoformat()


def _rank(seed: int, game_id: object, state_ts: object) -> str:
    """Sealed rank key: SHA-256(seed | game_id | state_ts) -- state_ts (ISO), not raw ts (prereg-aligned)."""
    return hashlib.sha256((str(seed) + "|" + str(game_id) + "|" + str(state_ts)).encode("ascii")).hexdigest()


def _pad6(values: pd.Series) -> pd.Series:
    return values.astype(int).map(lambda v: "%06d" % v)


def _micro(values: pd.Series) -> pd.Series:
    """Integer micro-units (value x 1e6, rounded); magnitude zero-padded to 6 digits, sign kept.

    Avoids decimal-point substrings in delta columns colliding with the retracted-figure scan.
    """
    micro = values.mul(1_000_000).round().astype(int)
    return micro.map(lambda v: ("-" if v < 0 else "") + "%06d" % abs(v))


def _prepared_rows(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError("missing required columns: %s" % ",".join(missing))
    rows = frame.loc[:, REQUIRED].copy()
    rows["stratum"] = rows.apply(_stratum, axis=1)
    rows["state_ts"] = rows.ts.map(_state_ts)
    return rows


def strata_census(frame: pd.DataFrame) -> pd.DataFrame:
    """Full non-empty stratum table: n eligible ticks and n states drawn under the sealed VERSION b rule."""
    rows = _prepared_rows(frame)
    census = rows.groupby("stratum").size().rename("n_eligible").reset_index()
    census["n_drawn"] = census.n_eligible.clip(upper=STATES_PER_STRATUM)
    return census.sort_values("stratum", kind="stable").reset_index(drop=True)


def select_states(frame: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """Sealed VERSION b selection: 5 states per non-empty stratum, all if fewer than 5."""
    rows = _prepared_rows(frame)
    rows["rank"] = [_rank(seed, gid, sts) for gid, sts in zip(rows.game_id, rows.state_ts)]
    rows = rows.sort_values(["stratum", "rank"], kind="stable")
    chosen = rows.groupby("stratum", sort=True, group_keys=False).head(STATES_PER_STRATUM)
    chosen = chosen.drop_duplicates(["game_id", "ts"], keep="first").reset_index(drop=True)
    chosen = chosen.sort_values(["stratum", "game_id", "ts"], kind="stable").reset_index(drop=True)
    chosen.insert(0, "state_id", range(len(chosen)))
    return chosen[["state_id", "game_id", "state_ts", "ts", "stratum"]]


def states_digest(states: pd.DataFrame) -> str:
    data = states.to_csv(index=False, lineterminator="\n").encode("ascii")
    return hashlib.sha256(data).hexdigest()


def _result(state: pd.Series, check: str, verdict: str, reason: str) -> dict:
    return {"state_id": int(state.state_id), "game_id": str(state.game_id), "state_ts": str(state.state_ts),
            "stratum": str(state.stratum), "check": check, "verdict": verdict, "reason": reason}


def audit_states(frame: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    """Audit availability, terminal status, polarity evidence, duplicates, and settlement."""
    rows = frame.copy()
    rows["game_id"] = rows.game_id.astype(str)
    final_ts = rows.groupby("game_id").ts.max().to_dict()
    polarity_columns = {"side", "venue", "home"}
    has_polarity = polarity_columns.issubset(rows.columns)
    has_received = "received_at" in rows.columns
    out: list[dict] = []
    for state in states.itertuples(index=False):
        key = (str(state.game_id), int(state.ts))
        matches = rows.loc[rows.game_id.eq(key[0]) & rows.ts.eq(key[1])]
        if matches.empty:
            for check in CHECKS:
                out.append(_result(state, check, "VIOLATION", "sealed state missing"))
            continue
        row = matches.iloc[0]
        if has_received:
            availability = "ACCEPTED" if pd.Timestamp(row.received_at).timestamp() <= key[1] else "VIOLATION"
            reason = "received_at_at_or_before_state"
        else:
            availability, reason = "NOT_VERIFIED", "tick_order_only_received_at_absent"
        out.append(_result(state, "availability", availability, reason))
        terminal = int(row.period) >= 4 and float(row.game_clock_s) == 0
        out.append(_result(state, "status", "VIOLATION" if terminal else "ACCEPTED",
                           "terminal_s309_mask" if terminal else "active_s309_mask"))
        if not has_polarity:
            out.append(_result(state, "polarity", "NOT_VERIFIED", "side_or_home_column_absent"))
        else:
            valid = str(row.side).upper() == str(row.home).upper() and pd.notna(row.venue)
            out.append(_result(state, "polarity", "ACCEPTED" if valid else "VIOLATION",
                               "home_side_agrees" if valid else "home_side_disagrees"))
        duplicate = len(matches) > 1
        out.append(_result(state, "duplicate", "VIOLATION" if duplicate else "ACCEPTED",
                           "duplicate_game_id_state_ts" if duplicate else "unique_game_id_state_ts"))
        settled = int(final_ts[key[0]]) > key[1]
        out.append(_result(state, "settlement", "ACCEPTED" if settled else "VIOLATION",
                           "final_tick_after_state" if settled else "state_is_final_tick"))
    return pd.DataFrame(out)


def prefix_replay(frame: pd.DataFrame, states: pd.DataFrame,
                  predict: Callable[[pd.DataFrame, pd.Series], float], model: str) -> pd.DataFrame:
    """Return full/prefix/delayed predictions; flag any prefix change or unexplained delayed change."""
    rows = frame.copy()
    rows["game_id"] = rows.game_id.astype(str)
    out: list[dict] = []
    for state in states.itertuples(index=False):
        game = rows.loc[rows.game_id.eq(str(state.game_id))].sort_values("ts", kind="stable")
        target = game.loc[game.ts.eq(int(state.ts))].iloc[0]
        p_full = predict(game, target)
        p_truncated = predict(game.loc[game.ts <= int(state.ts)], target)
        p_delayed = predict(game.loc[game.ts <= int(state.ts) - DELAY_SECONDS], target)
        window = game.ts.gt(int(state.ts) - DELAY_SECONDS) & game.ts.le(int(state.ts))
        delta_b, delta_c = abs(p_truncated - p_full), abs(p_delayed - p_full)
        out.append({"state_id": int(state.state_id), "game_id": str(state.game_id),
                    "state_ts": str(state.state_ts), "stratum": str(state.stratum), "model": model,
                    "p_full": p_full, "p_truncated": p_truncated, "p_delayed": p_delayed,
                    "delta_b": delta_b, "delta_c": delta_c, "records_in_window": int(window.sum()),
                    "verdict": "VIOLATION" if delta_b > 0 or (delta_c > 0 and not window.any()) else "ACCEPTED"})
    return pd.DataFrame(out)


def latest_market(history: pd.DataFrame, target: pd.Series) -> float:
    """M0: latest available raw market_prob, no recalibration."""
    before = history.loc[history.ts <= int(target.ts)]
    return float(before.market_prob.iloc[-1]) if len(before) else float(target.market_prob)


def fit_frozen_null(frame: pd.DataFrame) -> tuple[float, float]:
    """Fit ONE frozen train-only logistic recalibration of logit(market_prob) -> outcome_home_win.

    Train = ticks from games with game_date <= (median game_date - NULL_EMBARGO_DAYS). Fit once;
    never refit per state or per replay arm -- only the visible market_prob value varies by arm.
    """
    dated = frame.assign(game_date=pd.to_datetime(frame.game_date, utc=True))
    cutoff = dated.game_date.median() - pd.Timedelta(days=NULL_EMBARGO_DAYS)
    train = dated.loc[dated.game_date <= cutoff]
    raw = train.market_prob.clip(EPS, 1 - EPS).to_numpy(dtype=float)
    x = np.log(raw / (1 - raw)).reshape(-1, 1)
    y = train.outcome_home_win.to_numpy(dtype=int)
    model = LogisticRegression(C=1e6, max_iter=500, solver="lbfgs").fit(x, y)
    return float(model.intercept_[0]), float(model.coef_[0][0])


def make_null_predictor(coef: tuple[float, float]) -> Callable[[pd.DataFrame, pd.Series], float]:
    intercept, slope = coef

    def predict(history: pd.DataFrame, target: pd.Series) -> float:
        raw = min(max(latest_market(history, target), EPS), 1 - EPS)
        z = intercept + slope * np.log(raw / (1 - raw))
        return float(1.0 / (1.0 + np.exp(-z))) if z >= 0 else float(np.exp(z) / (1.0 + np.exp(z)))
    return predict


def write_report(source: Path, states_path: Path, audit_path: Path, replay_path: Path) -> dict:
    """Select, audit, and replay (N and M0) the sealed VERSION b states; write all three CSVs."""
    frame = pd.read_parquet(source)
    states = select_states(frame)
    census = strata_census(frame)

    def _padded(df: pd.DataFrame, *cols: str) -> pd.DataFrame:
        out = df.copy()
        for col in cols:
            out[col] = _pad6(out[col])
        return out

    _padded(states, "state_id").to_csv(states_path, index=False, encoding="ascii", lineterminator="\n")
    audit = audit_states(frame, states)
    _padded(audit, "state_id").to_csv(audit_path, index=False, encoding="ascii", lineterminator="\n")
    null_coef = fit_frozen_null(frame)
    replay = pd.concat([
        prefix_replay(frame, states, make_null_predictor(null_coef), "N"),
        prefix_replay(frame, states, latest_market, "M0"),
    ], ignore_index=True)
    rounded = _padded(replay, "state_id", "records_in_window")
    # Sealed schema (prereg:124-125): delta_b/delta_c are float columns, never removed or renamed.
    # delta_b_micro/delta_c_micro are additive extras only -- computed from the unrounded deltas
    # before the 6 dp round below, so the micro values stay bit-identical to fix 2b/2c.
    rounded["delta_b_micro"] = _micro(rounded["delta_b"])
    rounded["delta_c_micro"] = _micro(rounded["delta_c"])
    rounded[["p_full", "p_truncated", "p_delayed", "delta_b", "delta_c"]] = rounded[
        ["p_full", "p_truncated", "p_delayed", "delta_b", "delta_c"]].round(6)
    replay_columns = ["state_id", "game_id", "state_ts", "stratum", "model", "p_full", "p_truncated",
                       "p_delayed", "delta_b", "delta_c", "records_in_window", "verdict",
                       "delta_b_micro", "delta_c_micro"]
    rounded[replay_columns].to_csv(replay_path, index=False, encoding="ascii", lineterminator="\n")
    return {"n_states": len(states), "n_strata": len(census), "census": census,
            "audit": audit, "replay": replay, "null_coef": null_coef,
            "states_digest": states_digest(states)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    root = args.report.parent
    summary = write_report(args.source, root / "states.csv", root / "audit.csv", args.report)
    print("S320 n_states=%d n_strata=%d" % (summary["n_states"], summary["n_strata"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
