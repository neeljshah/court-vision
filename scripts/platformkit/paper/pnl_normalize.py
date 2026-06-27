"""scripts.platformkit.paper.pnl_normalize -- flat-stake + position-select helpers.

Split out of pnl_series.py to keep each file <=300 LOC. These pure helpers turn the
raw settled ledger rows into the clean, comparable flat-1-unit positions the equity
curve is built from:

  * select_model_positions -- ONE position per distinct market: the side the model
    rated most likely (contradictory both-sides model views are not both staked). The
    market key is (event, group, line), plus a team token for PER-TEAM two-sided markets
    (e.g. "Team total": home Over/Under and away Over/Under share (event, group, line)
    but are two distinct markets) so those genuine markets are not silently collapsed.
  * flat_unit_result -- recompute a row's result at a FLAT 1-unit stake from its
    outcome + decimal price (removes legacy dollar-Kelly stake contamination from the
    CLV ledger WITHOUT mutating it and WITHOUT changing any win/loss).

HONESTY: nothing is fabricated; a row with no recoverable decimal falls back to its
stored unit_result, and a row with no outcome/result is dropped (returns None).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test: covered by scripts/platformkit/paper/test_pnl_series.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file -> list of dicts. Missing file -> []. Malformed lines skipped."""
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def decimal_of(row: Dict[str, Any]) -> Optional[float]:
    """Settle/taken decimal price of a row, from any of the known keys (>1.0)."""
    for k in ("settle_decimal", "taken_decimal", "fair_odds"):
        v = row.get(k)
        if v is not None:
            try:
                d = float(v)
                if d > 1.0:
                    return d
            except (TypeError, ValueError):
                continue
    return None


def flat_unit_result(row: Dict[str, Any]) -> Optional[float]:
    """Recompute this row's result at a FLAT 1-unit stake from outcome + decimal.

    win -> +(dec-1); loss -> -1; push -> 0. Falls back to the stored unit_result only
    when no decimal price is recoverable; None when there is no usable result at all.
    """
    outcome = str(row.get("outcome") or "")
    dec = decimal_of(row)
    if dec is not None:
        if outcome == "win":
            return round(dec - 1.0, 6)
        if outcome == "loss":
            return -1.0
        if outcome == "push":
            return 0.0
    ur = row.get("unit_result")
    try:
        return float(ur) if ur is not None else None
    except (TypeError, ValueError):
        return None


def _team_token(row: Dict[str, Any]) -> Optional[str]:
    """Team this selection refers to, from its text vs the row's home/away team names.

    A per-team selection text is prefixed by the team name (e.g. "Atlanta Braves Over
    3.5", "San Francisco Giants -1.5"). Returns the matched team name (longest match
    wins so a team whose name contains the other's still resolves), else None.
    """
    sel = str(row.get("selection") or "")
    cands = [str(row.get("home_team") or ""), str(row.get("away_team") or "")]
    cands = sorted((t for t in cands if t), key=len, reverse=True)
    for t in cands:
        if sel.startswith(t):
            return t
    return None


def _per_team_groups(pred_rows: List[Dict[str, Any]]) -> set:
    """Data-driven set of groups that are PER-TEAM two-sided markets.

    A per-team market is one where a single (event_id, group, line) tuple silently
    covers more than one team's OWN two-sided sub-market -- e.g. "Team total" logs the
    home team's Over+Under AND the away team's Over+Under at the same line, four genuine
    selections that are really TWO distinct markets (home total, away total).

    Detected (not hardcoded, so new sports inherit it) when, inside some shared
    (event_id, group, line) bucket, 2+ distinct teams each carry their own selections
    AND at least one team carries 2+ selections (its own Over and Under). That second
    clause is what separates a per-team TOTAL from a symmetric game market: moneyline /
    game total / 1X2 / run line / spread name two teams too, but as the single market's
    two opposing sides (one selection per team), never one team's own two-way pair. We
    keep those on (event_id, group, line) so exactly ONE side is chosen -- not both --
    and no genuine two-way market is double-counted.
    """
    buckets: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in pred_rows:
        buckets.setdefault(
            (r.get("event_id"), r.get("group"), r.get("line")), []
        ).append(r)
    groups: set = set()
    for (_ev, group, _line), rows in buckets.items():
        per_team: Dict[str, set] = {}
        for r in rows:
            t = _team_token(r)
            if t is not None:
                per_team.setdefault(t, set()).add(str(r.get("selection") or ""))
        if len(per_team) >= 2 and any(len(s) >= 2 for s in per_team.values()):
            groups.add(group)
    return groups


def _position_key(row: Dict[str, Any], per_team_groups: set) -> tuple:
    """Dedup key identifying the distinct market this selection belongs to.

    Per-team groups get a team discriminator so each team's own market is its own key
    (its Over/Under still collapse to one pick). Symmetric game markets (moneyline,
    game total, run line / spread, 1X2, winning margin, ...) keep (event, group, line)
    so the two opposing sides collapse to ONE chosen side -- never both.
    """
    base = (row.get("event_id"), row.get("group"), row.get("line"))
    if row.get("group") in per_team_groups:
        return base + (_team_token(row),)
    return base


def select_model_positions(pred_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep ONE position per distinct market: the model's highest-prob pick.

    A two-way market logs BOTH sides as model views (e.g. Over AND Under). Flat-staking
    both is not a strategy -- it mechanically loses the spread. We keep only the side
    the model assigns the highest probability to; ties / a missing model_prob fall back
    to first-seen (still one per market).

    The market identity is (event_id, group, line) PLUS a team token for per-team
    two-sided markets (e.g. "Team total": home Over/Under and away Over/Under share the
    same (event, group, line) but are TWO distinct markets). Without the team token
    those four selections collapse to one position, silently dropping ~19% of genuine
    markets. The token splits each team's market apart while still collapsing every
    team's own Over/Under to one pick -- so "one position per market" stays literally
    true and no genuine two-way market is double-counted (symmetric game markets keep
    the plain (event, group, line) key and still pick a single side).
    """
    per_team = _per_team_groups(pred_rows)
    best: Dict[tuple, Dict[str, Any]] = {}
    for r in pred_rows:
        key = _position_key(r, per_team)
        mp = r.get("model_prob")
        try:
            mp = float(mp) if mp is not None else -1.0
        except (TypeError, ValueError):
            mp = -1.0
        cur = best.get(key)
        if cur is None or mp > cur.get("_mp", -1.0):
            r2 = dict(r)
            r2["_mp"] = mp
            best[key] = r2
    out: List[Dict[str, Any]] = []
    for r in best.values():
        r.pop("_mp", None)
        out.append(r)
    return out


def _clv_day(row: Dict[str, Any]) -> str:
    """The day a CLV-ledger row belongs to (settle date, else record date)."""
    for k in ("settled_at", "ts", "logged_at"):
        v = row.get(k)
        if v:
            return str(v)[:10]
    return ""


def _clv_market_key(row: Dict[str, Any]) -> tuple:
    """Distinct market a CLV-ledger placed bet belongs to (NO side).

    A moneyline-style two-way market is keyed by (sport, matchup, line, day) -- its two
    opposing sides (home ML AND away ML) share that key and are ONE market, never two bets.
    A 'line' discriminator keeps a genuinely distinct derived market apart.

    PLAYER PROPS are DISTINCT markets per (player, stat): each player's prop is its own bet,
    NOT one market shared with the rest of the slate. Without prop identity in the key, 50+
    players' o/u-0.5 props in a single game collapsed to ONE position -- silently dropping
    ~90% of the prop book and biasing the equity curve to the kept side. With it, only a
    prop's own over/under (same player+stat+line) collapse; genuinely distinct props stay
    separate, so the curve reconciles to the real placed positions.
    """
    return (str(row.get("sport")), str(row.get("matchup")),
            str(row.get("prop_player") or ""), str(row.get("prop_stat") or ""),
            row.get("line"), _clv_day(row))


def select_clv_positions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ONE position per CLV-ledger market: the model's single backed side.

    The CLV ledger records each placed paper bet as (sport, matchup, side, ...); a
    symmetric two-way market (home ML AND away ML) logs BOTH sides whenever both clear
    the EV floor, and a side recorded twice on the same day logs twice. Flat-staking
    both sides of a two-way market is nonsensical (win/loss cancel minus vig) and must
    NOT count as two bets. We keep exactly one row per (sport, matchup, line, day)
    market -- the side the model actually backs (highest model_prob) -- which also
    collapses duplicate same-side rows. Ties / missing model_prob fall back to
    first-seen (still one per market). Genuinely distinct markets (different line) stay
    separate, so no real two-sided market is silently dropped.
    """
    best: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        key = _clv_market_key(r)
        mp = r.get("model_prob")
        try:
            mp = float(mp) if mp is not None else -1.0
        except (TypeError, ValueError):
            mp = -1.0
        cur = best.get(key)
        if cur is None or mp > cur.get("_mp", -1.0):
            r2 = dict(r)
            r2["_mp"] = mp
            best[key] = r2
    out: List[Dict[str, Any]] = []
    for r in best.values():
        r.pop("_mp", None)
        out.append(r)
    return out


def normalize_flat(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-stake every row to a flat 1 unit; drop rows with no usable result.

    Returns NEW dicts (inputs untouched) with unit_result = flat_unit_result(row) and
    stake_units = 1.0 -- the clean unit track record the equity curve accumulates.
    """
    out: List[Dict[str, Any]] = []
    for r in rows:
        fur = flat_unit_result(r)
        if fur is None:
            continue
        r2 = dict(r)
        r2["unit_result"] = fur
        r2["stake_units"] = 1.0
        out.append(r2)
    return out


__all__ = ["load_jsonl", "decimal_of", "flat_unit_result",
           "select_model_positions", "select_clv_positions", "normalize_flat"]
# Internal helpers exported for the per-file test (per-team market keying):
__all__ += ["_team_token", "_per_team_groups", "_position_key",
            "_clv_market_key", "_clv_day"]
