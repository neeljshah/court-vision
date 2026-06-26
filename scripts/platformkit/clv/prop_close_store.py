"""prop_close_store -- closing-line history for player props (the prop analog of line_store).

A player prop only becomes CLV-measurable if we capture its TWO-WAY price near the
moment the market closes. This store holds timestamped two-way quotes (Over/Under
decimals) keyed by prop identity; the LATEST quote before settlement is the prop's
closing line, exactly as line_store.get_close serves a moneyline close near tip-off.

Honest by construction: it stores ONLY real two-way prices we actually observed
(both Over and Under decimals present). It never invents a close -- a prop we never
snapshotted simply has get_close() -> None, and the settler keeps clv_status
'no_close'. Append-only JSONL; latest-wins on read. Stdlib-only, ASCII.

Per-file test: scripts/platformkit/clv/test_prop_close_store.py
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
DEFAULT_STORE = os.path.join(_REPO, "data", "frontend", "prop_close_lines.jsonl")


def _norm(s: Any) -> str:
    """Canonical token: lowercase, collapse spaces / '+' so 'Hits+Runs+RBIs' ==
    'hits runs rbis' across the placer and the live feed."""
    out = []
    for ch in str(s).strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " +-/_":
            out.append(" ")
    return " ".join("".join(out).split())


def prop_key(sport: Any, game_date: Any, player: Any, stat: Any, line: Any) -> str:
    """Side-independent key (the two-way price covers BOTH over and under)."""
    try:
        line_s = "%.4g" % float(line)
    except (TypeError, ValueError):
        line_s = _norm(line)
    return "|".join([_norm(sport), str(game_date or ""), _norm(player),
                     _norm(stat), line_s])


def key_for_row(row: Dict[str, Any]) -> Optional[str]:
    """prop_key for a ledger bet row, or None if it lacks prop identity."""
    player = row.get("prop_player")
    stat = row.get("prop_stat")
    line = row.get("line")
    if player is None or stat is None or line is None:
        return None
    gd = row.get("game_date") or (str(row.get("ts") or "")[:10]) or ""
    return prop_key(row.get("sport"), gd, player, stat, line)


def record_quote(key: str, over_dec: float, under_dec: float, ts: str,
                 *, source: str = "", store_path: str = DEFAULT_STORE) -> bool:
    """Append a real two-way quote. Returns False (no write) if either side is
    missing/non-positive -- we never store a half-priced 'close'."""
    try:
        o, u = float(over_dec), float(under_dec)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(o) and math.isfinite(u)):
        return False
    if o <= 1.0 or u <= 1.0:
        return False
    rec = {"key": key, "over_dec": o, "under_dec": u, "ts": ts, "source": source}
    try:
        os.makedirs(os.path.dirname(store_path) or ".", exist_ok=True)
        with open(store_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        return False
    return True


def _load(store_path: str) -> Dict[str, Dict[str, Any]]:
    """Latest quote per key (last line wins). Missing file -> empty."""
    latest: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(store_path):
        return latest
    with open(store_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = r.get("key")
            if not k:
                continue
            # Defensive: skip any legacy row whose over_dec or under_dec is
            # present but non-finite (NaN/inf).  A poisoned row can never win
            # latest-wins ordering and can never serve as a close.
            for field in ("over_dec", "under_dec"):
                v = r.get(field)
                if v is not None:
                    try:
                        if not math.isfinite(float(v)):
                            k = None
                            break
                    except (TypeError, ValueError):
                        k = None
                        break
            if not k:
                continue
            cur = latest.get(k)
            if cur is None or str(r.get("ts") or "") >= str(cur.get("ts") or ""):
                latest[k] = r
    return latest


def get_close(key: str, *, store_path: str = DEFAULT_STORE) -> Optional[Dict[str, Any]]:
    """The closing two-way quote for *key* (latest observed), or None."""
    return _load(store_path).get(key)


def close_for_row(row: Dict[str, Any], *, store_path: str = DEFAULT_STORE
                  ) -> Optional[Dict[str, Any]]:
    k = key_for_row(row)
    if not k:
        return None
    return get_close(k, store_path=store_path)
