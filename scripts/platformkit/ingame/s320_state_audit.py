"""Prepared S320 timestamp, settlement, and prefix-replay audit helpers."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

SEED = 32020260908
DELAY_SECONDS = 60
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


def _rank(seed: int, game_id: object, ts: object) -> str:
    return hashlib.sha256((str(seed) + "|" + str(game_id) + "|" + str(ts)).encode("ascii")).hexdigest()


def select_states(frame: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """Select the preregistered 100 pairs, or fail on an impossible stratum rail."""
    missing = sorted(set(REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError("missing required columns: %s" % ",".join(missing))
    rows = frame.loc[:, REQUIRED].copy()
    rows["stratum"] = rows.apply(_stratum, axis=1)
    rows["rank"] = [_rank(seed, gid, ts) for gid, ts in zip(rows.game_id, rows.ts)]
    rows = rows.sort_values(["stratum", "rank"], kind="stable")
    groups = [part for _, part in rows.groupby("stratum", sort=True)]
    if len(groups) > 20:
        raise ValueError("PARTIAL: %d non-empty strata require at least %d states" %
                         (len(groups), len(groups) * 5))
    chosen = pd.concat([part.head(5) for part in groups], ignore_index=True)
    remaining = [part.iloc[5:] for part in groups]
    turn = 0
    while len(chosen) < 100 and any(len(part) for part in remaining):
        index = turn % len(remaining)
        if len(remaining[index]):
            chosen = pd.concat([chosen, remaining[index].iloc[[0]]], ignore_index=True)
            remaining[index] = remaining[index].iloc[1:]
        turn += 1
    chosen = chosen.drop_duplicates(["game_id", "ts"], keep="first")
    if len(chosen) != 100:
        raise ValueError("PARTIAL: selection has %d unique states, not 100" % len(chosen))
    chosen["state_ts"] = chosen.ts.map(_state_ts)
    return chosen[["game_id", "state_ts", "ts", "stratum"]].sort_values(
        ["stratum", "game_id", "ts"], kind="stable").reset_index(drop=True)


def states_digest(states: pd.DataFrame) -> str:
    data = states.to_csv(index=False, lineterminator="\n").encode("ascii")
    return hashlib.sha256(data).hexdigest()


def _result(state: pd.Series, check: str, verdict: str, reason: str) -> dict:
    return {"game_id": str(state.game_id), "state_ts": str(state.state_ts),
            "stratum": str(state.stratum), "check": check, "verdict": verdict,
            "reason": reason}


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
        availability = ("ACCEPTED" if has_received and pd.Timestamp(row.received_at).timestamp() <= key[1]
                        else "ACCEPTED" if not has_received else "VIOLATION")
        reason = "received_at_at_or_before_state" if has_received else "tick_order_only_received_at_absent"
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
                  predict: Callable[[pd.DataFrame, pd.Series], float], arm: str) -> pd.DataFrame:
    """Return a/b/c predictions and flag unexplained 60-second delayed changes."""
    rows = frame.copy()
    rows["game_id"] = rows.game_id.astype(str)
    out: list[dict] = []
    for state in states.itertuples(index=False):
        game = rows.loc[rows.game_id.eq(str(state.game_id))].sort_values("ts", kind="stable")
        target = game.loc[game.ts.eq(int(state.ts))].iloc[0]
        full = predict(game, target)
        prefix = predict(game.loc[game.ts <= int(state.ts)], target)
        delayed = predict(game.loc[game.ts <= int(state.ts) - DELAY_SECONDS], target)
        window = game.ts.gt(int(state.ts) - DELAY_SECONDS) & game.ts.le(int(state.ts))
        changed = abs(delayed - full) > 0.0
        prefix_changed = abs(prefix - full) > 0.0
        out.append({"game_id": str(state.game_id), "state_ts": str(state.state_ts),
                    "stratum": str(state.stratum), "arm": arm, "p_a_full": full,
                    "p_b_prefix": prefix, "p_c_delayed": delayed,
                    "abs_b_minus_a": abs(prefix - full), "abs_c_minus_a": abs(delayed - full),
                    "delay_window_records": int(window.sum()),
                    "verdict": "VIOLATION" if prefix_changed or (changed and not window.any()) else "ACCEPTED"})
    return pd.DataFrame(out)


def latest_market(history: pd.DataFrame, target: pd.Series) -> float:
    """M0 probe used by the synthetic rail; production N is supplied by the finisher."""
    before = history.loc[history.ts <= int(target.ts)]
    return float(before.market_prob.iloc[-1]) if len(before) else float(target.market_prob)


def write_report(source: Path, states_path: Path, audit_path: Path, replay_path: Path) -> None:
    """Write audit and M0 replay CSVs; N requires the finisher's frozen evaluator callback."""
    frame = pd.read_parquet(source)
    states = select_states(frame)
    states.to_csv(states_path, index=False, encoding="ascii", lineterminator="\n")
    audit_states(frame, states).to_csv(audit_path, index=False, encoding="ascii", lineterminator="\n")
    prefix_replay(frame, states, latest_market, "M0").to_csv(
        replay_path, index=False, encoding="ascii", lineterminator="\n")
    raise RuntimeError("PREPARED_ONLY: add frozen N through cpcv_evaluate before claiming S320 completion")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    root = args.report.parent
    write_report(args.source, root / "states.csv", root / "audit.csv", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
