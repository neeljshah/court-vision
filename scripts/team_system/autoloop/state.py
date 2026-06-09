"""STATE + LEDGERS -- the loop cursor, written to disk after every step so the run survives context
resets and process restarts (MASTER_SYSTEM_BUILD sections 7.3 / 7.6 / 6A / 6B).

Single source of truth = data/registry/state.json (read on EVERY wake). The iteration_ledger is the
append-only history (dedups ATTEMPTS so a REJECTED idea is never re-tried). run_ledger.json tracks the
budget ceilings; proc_ledger.json tracks every spawned process so they can be reaped on STOP/PAUSE.

  from loop.state import read_state, write_state, append_ledger, lever_id, lever_barred, claim_lever
"""
from __future__ import annotations
import hashlib
import json
import os
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REG = os.path.join(ROOT, "data", "registry")
STATE_PATH = os.path.join(REG, "state.json")
LEDGER_PATH = os.path.join(REG, "iteration_ledger.parquet")
RUN_LEDGER = os.path.join(REG, "run_ledger.json")
PROC_LEDGER = os.path.join(REG, "proc_ledger.json")
STOP_PATH = os.path.join(REG, "STOP")

LEDGER_COLS = ["iter_id", "ts", "phase", "frontier", "lever_id", "agents_spawned", "tokens_est",
               "verdict", "metric_before", "metric_after", "delta", "board", "notes"]
TERMINAL = {"WIRED", "REJECTED", "BLOCKED"}     # a lever_id with one of these is permanently barred
RETRYABLE = {"NULL", "DEFERRED"}                # may retry ONLY if a named precondition changed


def _atomic_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- state.json
def read_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        return json.load(open(STATE_PATH, encoding="utf-8"))
    except Exception:
        return {}


def write_state(state: dict) -> None:
    _atomic_json(STATE_PATH, state)


def update_state(**fields) -> dict:
    s = read_state()
    s.update(fields)
    s["asof"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_state(s)
    return s


def default_state(tokens_cap_today: int = 4_000_000) -> dict:
    return dict(
        phase="BUILD", iter_id=0, asof=time.strftime("%Y-%m-%dT%H:%M:%S"),
        frontier_status={}, in_flight=None,
        metrics=dict(shapeErr_worst=None, brier=None, xseason_mae=None, n_survivors=5),
        budget=dict(day=time.strftime("%Y-%m-%d"), tokens_spent_today=0, tokens_cap_today=tokens_cap_today),
        last_board="unknown", next_wake_ts=None, status="RUNNING", notes="first boot",
    )


# --------------------------------------------------------------------------- iteration ledger
def ledger_df() -> pd.DataFrame:
    if os.path.exists(LEDGER_PATH):
        return pd.read_parquet(LEDGER_PATH)
    return pd.DataFrame(columns=LEDGER_COLS)


def _write_ledger(df: pd.DataFrame) -> None:
    tmp = LEDGER_PATH + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, LEDGER_PATH)


def append_ledger(row: dict) -> None:
    import warnings
    df = ledger_df()
    full = {c: row.get(c) for c in LEDGER_COLS}
    full.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
    new = pd.DataFrame([full])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)   # all-NA column dtype inference (cosmetic)
        _write_ledger(new if df.empty else pd.concat([df, new], ignore_index=True))


def lever_id(frontier: str, target: str, method: str) -> str:
    canon = json.dumps(dict(frontier=frontier, target=target, method=method),
                       sort_keys=True, separators=(",", ":"))
    return "lev_" + hashlib.blake2b(canon.encode(), digest_size=8).hexdigest()


def lever_barred(lid: str) -> bool:
    """True if this lever_id already has a TERMINAL verdict (WIRED/REJECTED/BLOCKED) -- never re-try it
    (section 7.3.1). NULL/DEFERRED are retryable only with a stated precondition change."""
    df = ledger_df()
    if df.empty:
        return False
    hits = df[df.lever_id == lid]
    return bool(len(hits) and hits.verdict.isin(TERMINAL).any())


def lever_in_flight(lid: str) -> bool:
    df = ledger_df()
    if df.empty:
        return False
    hits = df[df.lever_id == lid]
    return bool(len(hits) and (hits.verdict == "IN_FLIGHT").any())


def claim_lever(iter_id: int, phase: str, frontier: str, lid: str, agents: int = 0,
                tokens_est: int = 0, metric_before=None, notes: str = "") -> None:
    """The lock that stops duplicate work: append an IN_FLIGHT row BEFORE spawning agents (7.3.2)."""
    append_ledger(dict(iter_id=iter_id, phase=phase, frontier=frontier, lever_id=lid,
                       agents_spawned=agents, tokens_est=tokens_est, verdict="IN_FLIGHT",
                       metric_before=metric_before, metric_after=None, delta=None,
                       board="pending", notes=notes))
    update_state(in_flight=dict(lever_id=lid, agents=agents, started_ts=time.time()))


def close_lever(iter_id: int, verdict: str, metric_after=None, delta=None, board: str = "",
                notes: str = "") -> None:
    """Close the IN_FLIGHT row for this iter_id with a final verdict + delta."""
    df = ledger_df()
    mask = (df.iter_id == iter_id) & (df.verdict == "IN_FLIGHT")
    if mask.any():
        idx = df[mask].index[-1]
        df.loc[idx, "verdict"] = verdict
        if metric_after is not None:
            df.loc[idx, "metric_after"] = metric_after
        if delta is not None:
            df.loc[idx, "delta"] = delta
        if board:
            df.loc[idx, "board"] = board
        if notes:
            df.loc[idx, "notes"] = notes
        _write_ledger(df)
    else:
        append_ledger(dict(iter_id=iter_id, verdict=verdict, metric_after=metric_after,
                           delta=delta, board=board, notes=notes))
    update_state(in_flight=None)


def stuck_tripwire(window: int = 5) -> bool:
    """True if the last `window` iterations produced NO net-new knowledge (no WIRED/REJECTED, no metric
    move) -- the loop must STOP loud (section 7.3.4) rather than spin."""
    df = ledger_df()
    closed = df[df.verdict != "IN_FLIGHT"]
    if len(closed) < window:
        return False
    tail = closed.tail(window)
    knowledge = tail.verdict.isin({"WIRED", "REJECTED"}).any()
    moved = tail.delta.apply(lambda d: bool(d) and abs(float(d)) > 1e-9 if pd.notna(d) else False).any()
    return not (knowledge or moved)


def frontier_exhausted(frontier: str, window: int = 3) -> bool:
    """The last `window` iterations on this frontier are all NULL/BLOCKED -> EXHAUSTED (7.3.3)."""
    df = ledger_df()
    sub = df[(df.frontier == frontier) & (df.verdict != "IN_FLIGHT")]
    if len(sub) < window:
        return False
    return bool(sub.tail(window).verdict.isin({"NULL", "BLOCKED"}).all())


# --------------------------------------------------------------------------- run ledger (budget ceilings)
def read_run_ledger() -> dict:
    if os.path.exists(RUN_LEDGER):
        try:
            return json.load(open(RUN_LEDGER, encoding="utf-8"))
        except Exception:
            pass
    return dict(iters=0, wall_clock_start=time.time(), subagent_calls=0, candidates=0, history=[])


def bump_run_ledger(**fields) -> dict:
    rl = read_run_ledger()
    for k, v in fields.items():
        if k == "history":
            rl.setdefault("history", []).append(v)
        elif isinstance(v, (int, float)) and k in rl and isinstance(rl[k], (int, float)):
            rl[k] += v                       # accumulate counters
        else:
            rl[k] = v
    _atomic_json(RUN_LEDGER, rl)
    return rl


# --------------------------------------------------------------------------- proc ledger (reap on stop)
def read_proc_ledger() -> list:
    if os.path.exists(PROC_LEDGER):
        try:
            return json.load(open(PROC_LEDGER, encoding="utf-8"))
        except Exception:
            pass
    return []


def register_proc(pid: int, cmd: str, purpose: str) -> None:
    procs = read_proc_ledger()
    procs.append(dict(pid=int(pid), cmd=str(cmd)[:300], purpose=purpose, start=time.time()))
    _atomic_json(PROC_LEDGER, procs)


def unregister_proc(pid: int) -> None:
    procs = [p for p in read_proc_ledger() if int(p.get("pid", -1)) != int(pid)]
    _atomic_json(PROC_LEDGER, procs)


def stop_requested() -> bool:
    return os.path.exists(STOP_PATH)


if __name__ == "__main__":
    import sys
    if "--init" in sys.argv:
        if read_state():
            print("state.json already exists -- not overwriting (this is a RESUME, section 9).")
        else:
            write_state(default_state())
            if not os.path.exists(LEDGER_PATH):
                _write_ledger(pd.DataFrame(columns=LEDGER_COLS))
            bump_run_ledger(iters=0)
            _atomic_json(PROC_LEDGER, [])
            print("first-boot spine written: state.json + iteration_ledger + run_ledger + proc_ledger")
    else:
        s = read_state()
        print(json.dumps(s, indent=2)[:1500] if s else "no state.json (first boot)")
        df = ledger_df()
        print(f"\nledger: {len(df)} rows; STOP present: {stop_requested()}")
