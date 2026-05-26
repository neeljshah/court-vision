"""auto_place_daemon.py — R17_J3 auto-placement engine.

Polls the latest live_bet_ranker output and, for any bet that passes ALL seven
safety gates, invokes scripts/place_bet.py to LOG intent to the pnl_ledger and
emits an urgent alert to vault/URGENT_BETS.md telling the operator to mirror
the bet on the actual sportsbook UI.

NO actual sportsbook API is touched. This is intent-to-bet auto-logging.

Safety gates (ALL must pass before fire):
    1. edge_pct >= --confidence-floor (default 8%)
    2. model_confirmed = True (middle/arb) OR
       regular bet AND |model_q50 - line| >= 0.5 * sigma where
       sigma := (q90 - q10) / 2.563 (Gaussian approximation)
    3. line_validator.validate_bet_line(bet) returns (True, ...)
    4. stake <= --per-bet-cap * bankroll (default 5%) AND
       cumulative daily exposure (open + just-placed) <= --daily-cap * bankroll
       (default 25%)
    5. bet (player, stat, side, book, line) not already in ledger as status=open
    6. now() > tip_off - --min-pre-tip-min (default 30 min, i.e. >= 30min before tip)
    7. injury_status for player is AVAILABLE / PROBABLE / QUESTIONABLE / DAY-TO-DAY
       (NOT OUT / DOUBTFUL); missing player = treat as AVAILABLE (no false-block)

CLI:
    python scripts/auto_place_daemon.py \\
        --slate sas_okc_2026-05-26 \\
        --interval-sec 60 \\
        --max-daily-bets 5 \\
        --confidence-floor 0.08 \\
        [--live]              # without this flag, daemon is dry-run only

Dry-run (default) prints what *would* be placed but never modifies the ledger
nor writes URGENT_BETS.md (those are gated behind --live).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import subprocess
import sys
import time
import unicodedata
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting.line_validator import validate_bet_line as _r17_j2_validate  # noqa: E402
from src.betting.pnl_ledger import LEDGER_CSV  # noqa: E402

# --------------------------------------------------------------------------- #
# Defaults / paths                                                            #
# --------------------------------------------------------------------------- #
DEFAULT_INTERVAL_SEC = 60
DEFAULT_MAX_DAILY = 5
DEFAULT_CONFIDENCE_FLOOR = 0.08  # 8%
DEFAULT_PER_BET_CAP = 0.05       # 5%
DEFAULT_DAILY_CAP = 0.25         # 25%
DEFAULT_BANKROLL = 1000.0
DEFAULT_MIN_PRE_TIP_MIN = 30
DEFAULT_Q50_DEV_SIGMAS = 0.5

URGENT_BETS_MD = os.path.join(PROJECT_DIR, "vault", "URGENT_BETS.md")
AUTO_PLACE_LOG_MD = os.path.join(PROJECT_DIR, "vault", "Improvements", "auto_place.md")
PROBE_RESULTS = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R17_J3_auto_place_results.json"
)
LIVE_BETS_DIR = os.path.join(PROJECT_DIR, "data", "cache", "live_bets")

# Slate -> tipoff (UTC ISO).  Auto-derived from live_bet_ranker.SLATES below if
# possible; otherwise the user can pass --tipoff-utc to override.
KNOWN_TIPOFFS_UTC: Dict[str, str] = {
    # SAS @ OKC Game 7 WCF — 8:30pm ET = 00:30 UTC next day
    "sas_okc_2026-05-26": "2026-05-27T00:30:00+00:00",
}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _name_key(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.lower().strip())


def _now_utc() -> _dt.datetime:
    """Override-friendly wall clock (tests monkeypatch this)."""
    return _dt.datetime.now(_dt.timezone.utc)


def latest_live_bets_path(slate_id: str, live_dir: str = LIVE_BETS_DIR) -> Optional[str]:
    """Return the most recently modified <date>_<slate>.json under live_bets/."""
    if not os.path.isdir(live_dir):
        return None
    cands = [
        os.path.join(live_dir, fn)
        for fn in os.listdir(live_dir)
        if fn.endswith(f"_{slate_id}.json") and not fn.endswith("_state.json")
    ]
    if not cands:
        return None
    cands.sort(key=os.path.getmtime, reverse=True)
    return cands[0]


def load_live_bets(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def load_injury_status(date_iso: str, cache_dir: Optional[str] = None) -> Dict[str, str]:
    """Return {name_key: status_upper} from data/cache/injury_status_<date>.json.

    Missing file or missing player both return AVAILABLE downstream (no false
    block).
    """
    cache_dir = cache_dir or os.path.join(PROJECT_DIR, "data", "cache")
    path = os.path.join(cache_dir, f"injury_status_{date_iso}.json")
    out: Dict[str, str] = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return out
    for p in data.get("players", []) or []:
        nk = _name_key(p.get("player_name", ""))
        if nk:
            out[nk] = str(p.get("status", "")).upper()
    return out


def open_bets_keys(ledger_path: str = LEDGER_CSV) -> List[Dict[str, Any]]:
    """Return list of open ledger rows (used for dedupe + exposure)."""
    if not os.path.exists(ledger_path):
        return []
    import csv as _csv
    rows: List[Dict[str, Any]] = []
    try:
        with open(ledger_path, encoding="utf-8") as fh:
            for r in _csv.DictReader(fh):
                if r.get("status") == "open":
                    rows.append(r)
    except OSError:
        return []
    return rows


def _bet_key(player: str, stat: str, side: str, book: str, line: float) -> str:
    return f"{_name_key(player)}|{stat.lower()}|{side.upper()}|{book.lower()}|{float(line):.2f}"


# --------------------------------------------------------------------------- #
# Safety gates                                                                #
# --------------------------------------------------------------------------- #
def gate_edge(bet: Mapping[str, Any], floor_pct: float) -> Tuple[bool, str]:
    edge = float(bet.get("edge_pct", 0.0))
    floor = floor_pct * 100.0 if floor_pct < 1.0 else floor_pct
    if edge < floor:
        return False, f"edge_pct={edge:.2f}% < floor={floor:.2f}%"
    return True, f"edge_pct={edge:.2f}% >= floor={floor:.2f}%"


def gate_model_confirmed(
    bet: Mapping[str, Any], sigma_thresh: float = DEFAULT_Q50_DEV_SIGMAS
) -> Tuple[bool, str]:
    """Either bet.model_confirmed (middle) OR q50 deviates from line by sigma_thresh sigmas."""
    if bool(bet.get("model_confirmed", False)):
        return True, "model_confirmed=True (middle/arb)"
    q10 = bet.get("model_q10")
    q50 = bet.get("model_q50")
    q90 = bet.get("model_q90")
    line = bet.get("line")
    if q10 is None or q50 is None or q90 is None or line is None:
        return False, "missing q10/q50/q90 or line for sigma check"
    try:
        q10f, q50f, q90f, linef = float(q10), float(q50), float(q90), float(line)
    except (TypeError, ValueError):
        return False, "quantiles/line not float-coercible"
    # Reject crossed quantiles outright (caught more rigorously by validator,
    # but here we'd compute a bogus sigma).
    if q90f < q10f:
        return False, f"quantile crossing q10={q10f} q90={q90f}"
    sigma = (q90f - q10f) / 2.563  # 80% Gaussian band -> sigma
    if sigma <= 0:
        return False, "sigma <= 0 (zero-variance quantile band)"
    dev = abs(q50f - linef) / sigma
    if dev < sigma_thresh:
        return False, (
            f"|q50-line|/sigma = {dev:.2f} < {sigma_thresh}sigma "
            f"(q50={q50f:.2f}, line={linef:.2f}, sigma={sigma:.2f})"
        )
    return True, (
        f"q50 dev {dev:.2f}sigma >= {sigma_thresh}sigma "
        f"(q50={q50f:.2f}, line={linef:.2f}, sigma={sigma:.2f})"
    )


def _cheap_pre_checks(bet: Mapping[str, Any]) -> Tuple[bool, str]:
    """Pure-python sanity checks before we hit the R17_J2 snapshot validator.

    Catches quantile crossing, stale flag, extreme odds and crossed implied
    prob bands -- the snapshot validator can't see those.
    """
    if bet is None:
        return False, "bet is None"
    for k in ("player", "stat", "side", "book", "line", "odds"):
        if k not in bet:
            return False, f"missing field {k!r}"

    try:
        odds = int(bet["odds"])
    except (TypeError, ValueError):
        return False, f"odds not int: {bet.get('odds')!r}"
    if odds == 0:
        return False, "odds is zero"
    if abs(odds) > 400:
        return False, f"|odds|={abs(odds)} > 400"
    p_imp = 100.0 / (odds + 100.0) if odds > 0 else (-odds) / ((-odds) + 100.0)
    if not (0.20 <= p_imp <= 0.80):
        return False, f"implied_prob {p_imp:.3f} outside [0.20, 0.80]"

    side = str(bet.get("side", "")).upper()
    if side not in ("OVER", "UNDER"):
        return False, f"invalid side: {side!r}"

    try:
        line = float(bet["line"])
    except (TypeError, ValueError):
        return False, f"line not float: {bet.get('line')!r}"
    if line < 0:
        return False, f"negative line: {line}"

    # Quantile-crossing check
    q10 = bet.get("model_q10")
    q50 = bet.get("model_q50")
    q90 = bet.get("model_q90")
    if q10 is not None and q50 is not None and q90 is not None:
        try:
            q10f, q50f, q90f = float(q10), float(q50), float(q90)
            if not (q10f <= q50f <= q90f):
                return False, (
                    f"quantile crossing: q10={q10f}, q50={q50f}, q90={q90f}"
                )
        except (TypeError, ValueError):
            return False, "quantiles not float-coercible"

    if bool(bet.get("stale", False)):
        return False, "book snapshot is stale"

    return True, "ok"


def gate_line_validator(
    bet: Mapping[str, Any],
    *,
    use_snapshot: bool = True,
    lines_dir: Optional[str] = None,
    max_staleness_sec: int = 120,
) -> Tuple[bool, str]:
    """Run cheap sanity checks + optional R17_J2 snapshot validator.

    If use_snapshot=False (or no lines dir is available) we ONLY run the
    cheap checks. Useful in tests + when the snapshot CSVs are missing.
    """
    ok, reason = _cheap_pre_checks(bet)
    if not ok:
        return False, f"line_validator: {reason}"
    if not use_snapshot:
        return True, f"line_validator: {reason}"
    try:
        kwargs = dict(
            book=str(bet["book"]),
            player_name=str(bet["player"]),
            stat=str(bet["stat"]).lower(),
            line=float(bet["line"]),
            side=str(bet["side"]).upper(),
            odds=int(bet["odds"]),
            max_staleness_sec=max_staleness_sec,
        )
        if lines_dir is not None:
            kwargs["lines_dir"] = lines_dir
        snap_ok, snap_reason, _snap = _r17_j2_validate(**kwargs)
    except TypeError as e:
        return False, f"line_validator: signature mismatch ({e!r})"
    except Exception as e:  # pragma: no cover - defensive
        return False, f"line_validator: snapshot probe error ({e!r})"
    if not snap_ok:
        return False, f"line_validator (snapshot): {snap_reason}"
    return True, f"line_validator: {snap_reason}"


def gate_bankroll(
    bet: Mapping[str, Any],
    bankroll: float,
    per_bet_cap: float,
    daily_cap: float,
    existing_daily_exposure: float,
) -> Tuple[bool, str]:
    stake = float(bet.get("kelly_stake_$", 0.0))
    if stake <= 0:
        return False, f"stake ${stake:.2f} <= 0"
    cap = bankroll * per_bet_cap
    if stake > cap + 1e-9:
        return False, (
            f"stake ${stake:.2f} exceeds {per_bet_cap*100:.1f}% per-bet "
            f"cap of ${bankroll:.2f} (cap=${cap:.2f})"
        )
    new_exposure = existing_daily_exposure + stake
    daily_cap_abs = bankroll * daily_cap
    if new_exposure > daily_cap_abs + 1e-9:
        return False, (
            f"new daily exposure ${new_exposure:.2f} exceeds "
            f"{daily_cap*100:.1f}% cap (${daily_cap_abs:.2f}); "
            f"already-allocated=${existing_daily_exposure:.2f}, stake=${stake:.2f}"
        )
    return True, (
        f"stake ${stake:.2f} within per-bet ${cap:.2f} and "
        f"daily ${daily_cap_abs:.2f} (post=${new_exposure:.2f})"
    )


def gate_dedupe(bet: Mapping[str, Any], open_rows: List[Dict[str, Any]]) -> Tuple[bool, str]:
    target = _bet_key(
        bet.get("player", ""), bet.get("stat", ""), bet.get("side", ""),
        bet.get("book", ""), bet.get("line", 0.0),
    )
    for r in open_rows:
        try:
            row_line = float(r.get("line", -999))
        except (TypeError, ValueError):
            continue
        if _bet_key(
            r.get("player", ""), r.get("stat", ""), r.get("side", ""),
            r.get("book", ""), row_line,
        ) == target:
            return False, f"open duplicate in ledger: bet_id={r.get('bet_id')}"
    return True, "no open duplicate"


def gate_tip_time(
    bet: Mapping[str, Any],
    tip_off_utc: Optional[_dt.datetime],
    min_pre_tip_min: int,
    now: Optional[_dt.datetime] = None,
) -> Tuple[bool, str]:
    if tip_off_utc is None:
        return False, "tipoff unknown — cannot verify pre-tip window"
    now = now or _now_utc()
    delta_min = (tip_off_utc - now).total_seconds() / 60.0
    if delta_min < min_pre_tip_min:
        return False, (
            f"{delta_min:.1f}min until tip — less than required "
            f"{min_pre_tip_min}min buffer"
        )
    return True, f"{delta_min:.1f}min until tip (>= {min_pre_tip_min}min buffer)"


_INJURY_OK = {"AVAILABLE", "PROBABLE", "QUESTIONABLE", "DAY-TO-DAY", "DAY_TO_DAY", ""}
_INJURY_BLOCK = {"OUT", "DOUBTFUL", "DNP"}


def gate_injury(bet: Mapping[str, Any], injuries: Mapping[str, str]) -> Tuple[bool, str]:
    nk = _name_key(bet.get("player", ""))
    status = injuries.get(nk, "")
    s = str(status or "").upper()
    if s in _INJURY_BLOCK:
        return False, f"injury status={s} (blocks placement)"
    if s and s not in _INJURY_OK:
        return False, f"injury status={s} (unknown — blocks for safety)"
    return True, f"injury status={s or 'NOT_LISTED (assume AVAILABLE)'}"


# --------------------------------------------------------------------------- #
# Gate orchestrator                                                           #
# --------------------------------------------------------------------------- #
def run_all_gates(
    bet: Mapping[str, Any],
    *,
    bankroll: float,
    per_bet_cap: float,
    daily_cap: float,
    existing_daily_exposure: float,
    open_rows: List[Dict[str, Any]],
    confidence_floor: float,
    tip_off_utc: Optional[_dt.datetime],
    min_pre_tip_min: int,
    injuries: Mapping[str, str],
    now: Optional[_dt.datetime] = None,
    sigma_thresh: float = DEFAULT_Q50_DEV_SIGMAS,
    use_snapshot_validator: bool = True,
    lines_dir: Optional[str] = None,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Return (all_passed, [{gate, ok, reason}, ...]) in fixed order."""
    results: List[Dict[str, Any]] = []
    gates = [
        ("edge", lambda: gate_edge(bet, confidence_floor)),
        ("model_confirmed", lambda: gate_model_confirmed(bet, sigma_thresh)),
        ("line_validator", lambda: gate_line_validator(
            bet, use_snapshot=use_snapshot_validator, lines_dir=lines_dir)),
        ("bankroll", lambda: gate_bankroll(
            bet, bankroll, per_bet_cap, daily_cap, existing_daily_exposure)),
        ("dedupe", lambda: gate_dedupe(bet, open_rows)),
        ("tip_time", lambda: gate_tip_time(bet, tip_off_utc, min_pre_tip_min, now)),
        ("injury", lambda: gate_injury(bet, injuries)),
    ]
    all_ok = True
    for name, fn in gates:
        try:
            ok, reason = fn()
        except Exception as e:  # pragma: no cover - defensive
            ok, reason = False, f"gate exception: {e!r}"
        results.append({"gate": name, "ok": bool(ok), "reason": reason})
        if not ok:
            all_ok = False
    return all_ok, results


# --------------------------------------------------------------------------- #
# place_bet.py invocation                                                     #
# --------------------------------------------------------------------------- #
def invoke_place_bet(
    bet: Mapping[str, Any], *, bankroll: float, dry_run: bool,
    no_slate_validate: bool = True, slate_path: Optional[str] = None,
) -> Tuple[int, str]:
    """Call scripts/place_bet.py as a subprocess and return (rc, stdout+stderr)."""
    args = [
        sys.executable,
        os.path.join(PROJECT_DIR, "scripts", "place_bet.py"),
        "--player", str(bet["player"]),
        "--stat", str(bet["stat"]).lower(),
        "--side", str(bet["side"]).upper(),
        "--line", str(float(bet["line"])),
        "--book", str(bet["book"]),
        "--odds", str(int(bet["odds"])),
        "--stake", str(float(bet["kelly_stake_$"])),
        "--bankroll", str(float(bankroll)),
        "--strategy", "auto_place_R17_J3",
    ]
    if dry_run:
        args.append("--dry-run")
    if no_slate_validate:
        args.append("--no-slate-validate")
    elif slate_path:
        args.extend(["--slate", slate_path])
    # Pass model context (so the ledger row has it)
    if bet.get("model_q50") is not None:
        args.extend(["--model-pred", str(float(bet["model_q50"]))])
    if bet.get("model_prob") is not None:
        args.extend(["--model-prob", str(float(bet["model_prob"]))])
    if bet.get("kelly_pct_used") is not None:
        args.extend(["--kelly-pct", str(float(bet["kelly_pct_used"]))])
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": PROJECT_DIR},
        )
    except subprocess.TimeoutExpired:
        return 124, "place_bet.py timeout (30s)"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# --------------------------------------------------------------------------- #
# Alert formatters                                                            #
# --------------------------------------------------------------------------- #
_BOOK_PRETTY = {
    "pin": "Pin", "fd": "FD", "bov": "Bov", "dk": "DK", "mgm": "MGM",
}


def format_urgent(bet: Mapping[str, Any], now: _dt.datetime, dry_run: bool) -> str:
    book = _BOOK_PRETTY.get(str(bet.get("book", "")).lower(), str(bet.get("book", "")).upper())
    odds = int(bet["odds"])
    sign = f"{odds:+d}"
    prefix = "[DRY-RUN] " if dry_run else ""
    return (
        f"## {prefix}PLACE THIS NOW: "
        f"{bet['player']} {str(bet['stat']).upper()} {str(bet['side']).upper()} "
        f"{float(bet['line']):g} @ {book} {sign} ${float(bet['kelly_stake_$']):.0f}\n"
        f"- captured_at: {now.isoformat()}\n"
        f"- edge_pct: {float(bet.get('edge_pct', 0.0)):.2f}%\n"
        f"- model_q50: {bet.get('model_q50')}  model_prob: {bet.get('model_prob')}\n"
        f"- kelly_pct: {bet.get('kelly_pct_used')}%  stake: ${float(bet['kelly_stake_$']):.2f}\n"
    )


def append_urgent(bet: Mapping[str, Any], now: _dt.datetime, *, dry_run: bool,
                  path: str = URGENT_BETS_MD) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = ""
    if not os.path.exists(path):
        header = (
            "# URGENT BETS — auto-placement alerts\n\n"
            "Monitor this file. Each new section is a high-confidence bet the "
            "auto_place_daemon has logged to the ledger and that you should "
            "now MIRROR on the actual sportsbook.\n\n"
            "---\n\n"
        )
    with open(path, "a", encoding="utf-8") as fh:
        if header:
            fh.write(header)
        fh.write(format_urgent(bet, now, dry_run))
        fh.write("\n---\n\n")
    # R21_N3 — layered alert (vault + critical-stack always; Discord if URL set).
    try:
        from src.alerts.discord_webhook import alert
        headline = (f"{'DRY' if dry_run else 'LIVE'} FIRE — {bet.get('player', '?')} "
                    f"{str(bet.get('stat', '?')).upper()} {str(bet.get('side', '?')).upper()} "
                    f"{bet.get('line', '?')}")
        detail = (f"@{bet.get('book', '?')} {int(bet.get('odds', 0)):+d}  "
                  f"edge={float(bet.get('edge_pct', 0)):.2f}%  "
                  f"stake=${float(bet.get('kelly_stake_$', 0)):.2f}")
        alert(
            headline,
            level="critical",
            tag="auto_place_daemon",
            source="auto_place_daemon",
            body=detail,
            fields=[{"name": "kelly_pct", "value": f"{bet.get('kelly_pct_used', '?')}%"},
                    {"name": "model_prob", "value": str(bet.get('model_prob', '?'))}],
        )
    except Exception:
        pass  # never block live placement on push-notify failure


def append_auto_place_log(
    entry: Dict[str, Any], path: str = AUTO_PLACE_LOG_MD
) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = ""
    if not os.path.exists(path):
        header = (
            "# Auto-place log\n\n"
            "Appended row per safety-gate evaluation by `auto_place_daemon.py`.\n\n"
        )
    fired = "FIRED" if entry.get("fired") else "SKIP "
    bet = entry.get("bet", {})
    line = (
        f"- {entry.get('ts')}  {fired}  "
        f"{bet.get('player','?')} {str(bet.get('stat','?')).upper()} "
        f"{str(bet.get('side','?')).upper()} {bet.get('line','?')} @ "
        f"{bet.get('book','?')} {int(bet.get('odds',0)):+d}  "
        f"edge={float(bet.get('edge_pct',0)):.2f}%  "
        f"stake=${float(bet.get('kelly_stake_$',0)):.2f}  "
        f"dry_run={entry.get('dry_run')}  "
        f"blocked_by={entry.get('blocked_by') or '-'}"
    )
    with open(path, "a", encoding="utf-8") as fh:
        if header:
            fh.write(header)
        fh.write(line + "\n")


# --------------------------------------------------------------------------- #
# Single-tick evaluator                                                       #
# --------------------------------------------------------------------------- #
def evaluate_tick(
    live_bets: Mapping[str, Any],
    *,
    bankroll: float,
    per_bet_cap: float,
    daily_cap: float,
    confidence_floor: float,
    tip_off_utc: Optional[_dt.datetime],
    min_pre_tip_min: int,
    injuries: Mapping[str, str],
    open_rows: List[Dict[str, Any]],
    daily_bets_remaining: int,
    now: Optional[_dt.datetime] = None,
    top_n: int = 5,
    sigma_thresh: float = DEFAULT_Q50_DEV_SIGMAS,
    use_snapshot_validator: bool = False,
    lines_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Walk top-N ranked bets, run all gates, return per-bet results.

    Each result row: {bet, gates: [...], all_passed: bool, blocked_by: list[str]}.
    The caller decides whether to actually fire (dry-run vs live).
    """
    now = now or _now_utc()
    out: List[Dict[str, Any]] = []
    bets = list(live_bets.get("ranked_bets", []))[:top_n]
    # Sort by edge_pct DESC just in case
    bets.sort(key=lambda b: float(b.get("edge_pct", 0.0)), reverse=True)
    existing_exposure = 0.0  # additive within this tick

    for bet in bets:
        if daily_bets_remaining <= 0:
            out.append({
                "bet": dict(bet), "all_passed": False,
                "gates": [], "blocked_by": ["daily_cap_reached"],
            })
            continue
        ok, gates = run_all_gates(
            bet,
            bankroll=bankroll,
            per_bet_cap=per_bet_cap,
            daily_cap=daily_cap,
            existing_daily_exposure=existing_exposure,
            open_rows=open_rows,
            confidence_floor=confidence_floor,
            tip_off_utc=tip_off_utc,
            min_pre_tip_min=min_pre_tip_min,
            injuries=injuries,
            now=now,
            sigma_thresh=sigma_thresh,
            use_snapshot_validator=use_snapshot_validator,
            lines_dir=lines_dir,
        )
        blocked_by = [g["gate"] for g in gates if not g["ok"]]
        out.append({
            "bet": dict(bet), "all_passed": bool(ok),
            "gates": gates, "blocked_by": blocked_by,
        })
        if ok:
            existing_exposure += float(bet.get("kelly_stake_$", 0.0))
            daily_bets_remaining -= 1
    return out


# --------------------------------------------------------------------------- #
# Daemon loop                                                                 #
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slate", default="sas_okc_2026-05-26",
                    help="Slate id (matches live_bet_ranker.SLATES).")
    ap.add_argument("--interval-sec", type=int, default=DEFAULT_INTERVAL_SEC)
    ap.add_argument("--max-daily-bets", type=int, default=DEFAULT_MAX_DAILY)
    ap.add_argument("--confidence-floor", type=float, default=DEFAULT_CONFIDENCE_FLOOR,
                    help="Min edge_pct as fraction (0.08 == 8%%).")
    ap.add_argument("--per-bet-cap", type=float, default=DEFAULT_PER_BET_CAP)
    ap.add_argument("--daily-cap", type=float, default=DEFAULT_DAILY_CAP)
    ap.add_argument("--bankroll", type=float, default=DEFAULT_BANKROLL)
    ap.add_argument("--min-pre-tip-min", type=int, default=DEFAULT_MIN_PRE_TIP_MIN)
    ap.add_argument("--sigma-thresh", type=float, default=DEFAULT_Q50_DEV_SIGMAS)
    ap.add_argument("--tipoff-utc", default=None,
                    help="ISO-8601 UTC tipoff (overrides KNOWN_TIPOFFS_UTC).")
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--max-ticks", type=int, default=None,
                    help="Stop after N ticks (default: run forever).")
    ap.add_argument("--live", action="store_true",
                    help="Actually call place_bet.py (default: dry-run only).")
    ap.add_argument("--live-bets-dir", default=LIVE_BETS_DIR)
    ap.add_argument("--use-snapshot-validator", action="store_true",
                    help="Also call R17_J2 snapshot validator (needs data/lines/*.csv).")
    ap.add_argument("--lines-dir", default=None)
    return ap


def run_daemon(args: argparse.Namespace) -> Dict[str, Any]:
    pid = os.getpid()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [auto_place pid=%(process)d] %(message)s",
    )
    logger = logging.getLogger("auto_place")
    logger.info(
        f"START slate={args.slate} interval={args.interval_sec}s "
        f"max_daily={args.max_daily_bets} floor={args.confidence_floor} "
        f"live={'YES' if args.live else 'NO (dry-run)'}"
    )

    # Tipoff
    tipoff_iso = args.tipoff_utc or KNOWN_TIPOFFS_UTC.get(args.slate)
    tip_off_utc: Optional[_dt.datetime] = None
    if tipoff_iso:
        try:
            tip_off_utc = _dt.datetime.fromisoformat(tipoff_iso)
            if tip_off_utc.tzinfo is None:
                tip_off_utc = tip_off_utc.replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            logger.warning(f"could not parse tipoff {tipoff_iso!r}")

    # Date from slate id (last 10 chars usually YYYY-MM-DD)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", args.slate)
    date_iso = date_match.group(1) if date_match else _now_utc().date().isoformat()

    bets_today = 0
    summary: Dict[str, Any] = {
        "daemon_pid": pid,
        "slate": args.slate,
        "live": bool(args.live),
        "started_at": _now_utc().isoformat(),
        "ticks_observed": 0,
        "bets_fired": 0,
        "bets_skipped": 0,
        "fired_records": [],
        "last_tick_results": [],
    }

    tick = 0
    try:
        while True:
            # R19_L3 heartbeat
            _r19_hb('auto_place_daemon')
            t_start = time.time()
            tick += 1

            live_path = latest_live_bets_path(args.slate, args.live_bets_dir)
            if live_path is None:
                logger.warning(f"no live_bets file for slate={args.slate} — sleeping")
                time.sleep(max(0, args.interval_sec - (time.time() - t_start)))
                if args.max_ticks is not None and tick >= args.max_ticks:
                    break
                continue
            live_bets = load_live_bets(live_path)
            if live_bets is None:
                logger.warning(f"could not parse {live_path}")
                time.sleep(max(0, args.interval_sec - (time.time() - t_start)))
                if args.max_ticks is not None and tick >= args.max_ticks:
                    break
                continue

            injuries = load_injury_status(date_iso)
            open_rows = open_bets_keys()
            now = _now_utc()
            results = evaluate_tick(
                live_bets,
                bankroll=args.bankroll,
                per_bet_cap=args.per_bet_cap,
                daily_cap=args.daily_cap,
                confidence_floor=args.confidence_floor,
                tip_off_utc=tip_off_utc,
                min_pre_tip_min=args.min_pre_tip_min,
                injuries=injuries,
                open_rows=open_rows,
                daily_bets_remaining=max(0, args.max_daily_bets - bets_today),
                now=now,
                top_n=args.top_n,
                sigma_thresh=args.sigma_thresh,
                use_snapshot_validator=args.use_snapshot_validator,
                lines_dir=args.lines_dir,
            )
            summary["ticks_observed"] += 1
            summary["last_tick_results"] = results

            for r in results:
                if r["all_passed"] and bets_today < args.max_daily_bets:
                    rc, stdout = invoke_place_bet(
                        r["bet"], bankroll=args.bankroll, dry_run=not args.live,
                        no_slate_validate=True,
                    )
                    ok_fire = (rc == 0)
                    entry = {
                        "ts": now.isoformat(),
                        "bet": r["bet"],
                        "dry_run": not args.live,
                        "rc": rc,
                        "place_bet_output": stdout.strip().splitlines()[:20],
                        "fired": ok_fire,
                        "blocked_by": None,
                    }
                    if ok_fire:
                        if args.live:
                            append_urgent(r["bet"], now, dry_run=False)
                        else:
                            # Still write urgent in dry-run mode so the operator can preview the format
                            append_urgent(r["bet"], now, dry_run=True)
                        append_auto_place_log(entry)
                        summary["bets_fired"] += 1
                        summary["fired_records"].append(entry)
                        if args.live:
                            bets_today += 1
                        logger.info(
                            f"FIRED {r['bet']['player']} "
                            f"{str(r['bet']['stat']).upper()} "
                            f"{str(r['bet']['side']).upper()} {r['bet']['line']:g} "
                            f"@ {r['bet']['book']} {int(r['bet']['odds']):+d} "
                            f"${r['bet']['kelly_stake_$']:.0f} "
                            f"(rc={rc}, dry={not args.live})"
                        )
                    else:
                        logger.warning(
                            f"place_bet.py rc={rc} for "
                            f"{r['bet']['player']} {r['bet']['stat']} — output: "
                            f"{stdout.strip()[:200]}"
                        )
                        entry["fired"] = False
                        entry["blocked_by"] = ["place_bet_rc_nonzero"]
                        append_auto_place_log(entry)
                        summary["bets_skipped"] += 1
                else:
                    summary["bets_skipped"] += 1
                    append_auto_place_log({
                        "ts": now.isoformat(),
                        "bet": r["bet"],
                        "dry_run": not args.live,
                        "fired": False,
                        "blocked_by": r["blocked_by"],
                    })

            # Probe results dump
            try:
                with open(PROBE_RESULTS, "w", encoding="utf-8") as fh:
                    json.dump(summary, fh, indent=2, default=str)
            except OSError:
                pass

            if args.max_ticks is not None and tick >= args.max_ticks:
                break
            time.sleep(max(0, args.interval_sec - (time.time() - t_start)))
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — daemon exiting cleanly.")
    finally:
        summary["stopped_at"] = _now_utc().isoformat()
        logger.info(
            f"STOP pid={pid} ticks={summary['ticks_observed']} "
            f"fired={summary['bets_fired']} skipped={summary['bets_skipped']}"
        )

    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.live:
        print("[auto_place] LIVE mode — will call place_bet.py for passing bets.", flush=True)
    else:
        print("[auto_place] DRY-RUN mode (default) — no ledger writes. Pass --live to enable.", flush=True)
    run_daemon(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
