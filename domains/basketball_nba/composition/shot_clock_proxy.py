"""domains.basketball_nba.composition.shot_clock_proxy -- a DERIVED shot-clock-
remaining label built from fields already in the PBP corpus (no shotClock
field exists anywhere -- see nba_hypotheses.BLOCKED_REASONS["spacing x late-
clock (<=7s) efficiency"]). This module exists to UNBLOCK that hypothesis with
an honestly-validated proxy, not to invent a new statistical framework.

proxy = 24s minus elapsed time since the possession-holding team last changed
(a "possession start"). No invention beyond what a possession start means:
  - made shot (2pt/3pt/freethrow, final FT of the trip) -> OTHER team next.
  - rebound (any subtype -- offensive rebounds are a same-team no-op, they do
    NOT reset this proxy; only DEFENSIVE rebounds actually change the team,
    which naturally falls out of "direct-read the rebounder's own teamId").
  - turnover/steal -> OTHER team next.
  - period start -> forced reset, team unknown until the period's first
    anchor event resolves it (a handful of actions/period, harmless).
  ponytail: real NBA rule resets the clock to 14s on an offensive rebound too
  -- this proxy does NOT model that (team continuity, not clock-only resets),
  matching the task's literal 4-trigger spec. See validate_distribution()'s
  pct_over24 for how much that costs in practice; if it's small, fine as v1.

TWO inference modes:
  cdn_field  -- the 196 CDN-native files carry an explicit `possession` field
    (teamId) on every action; a boundary is wherever that value changes.
    Near-ground-truth, used as the actual proxy source for those files.
  semantic   -- the 996 ESPN-derived files carry none of that; boundaries are
    inferred purely from actionType/subType/description text (the 4 rules
    above). Used as the actual proxy source for ESPN files, AND run a second
    time on the CDN files (ignoring their real `possession` field) purely to
    MEASURE how trustworthy this same semantic logic is -- see
    cdn_semantic_agreement().

Descriptive/measurement only. NETWORK: zero.
CLI: python -m domains.basketball_nba.composition.shot_clock_proxy
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.basketball_nba.lineups.pbp_lineups import _elapsed_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_PBP_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "pbp"

SHOT_CLOCK_S = 24.0

_REBOUND_RE = re.compile(r"rebound", re.I)  # ESPN text anchor; CDN uses actionType=='rebound'
_TURNOVER_RE = re.compile(
    r"\bturnover\b|\btraveling\b|offensive foul|offensive charge|\bbackcourt\b|"
    r"double dribble|discontinu|\bpalming\b|kicked ball violation|"
    r"\d+.second violation|\bsteals?\b",
    re.I,
)  # ESPN text anchor for turnover/steal; CDN uses actionType in ('turnover','steal')
_FT_PAT = re.compile(r"(\d+)\s*of\s*(\d+)", re.I)


def _other_team(team_ids: List[int], tid: Optional[int]) -> Optional[int]:
    rest = [i for i in team_ids if i != tid]
    return rest[0] if len(rest) == 1 else None


def _is_final_ft(desc: str) -> bool:
    """True for the last (or only, e.g. a technical) FT of a trip -- only the
    final FT can end a possession; '1 of 2' does not."""
    m = _FT_PAT.search(desc or "")
    return True if m is None else m.group(1) == m.group(2)


def _resolve_row(a: Dict[str, Any], team_ids: List[int], current_team: Optional[int]):
    """Returns (this_row_team, next_current_team). `this_row_team` is what the
    action ITSELF should read as (matches the real CDN `possession` field's
    own convention: a shot/rebound/turnover row's possessing team == its own
    teamId); `next_current_team` is what carries forward to the next non-
    anchor row (fouls/subs/timeouts don't change it themselves)."""
    at, tid = a.get("actionType"), a.get("teamId")
    desc = (a.get("description") or "").lower()

    if at in ("2pt", "3pt", "freethrow"):
        ended = at != "freethrow" or _is_final_ft(desc)
        made = a.get("shotResult") == "Made"
        nxt = _other_team(team_ids, tid) if (made and ended) else tid
        return tid, nxt
    if at == "rebound" or (at == "other" and _REBOUND_RE.search(desc)):
        return tid, tid
    if at == "steal" or (at == "jumpball" and a.get("subType") == "recovered"):
        return tid, tid
    if at == "turnover" or (at == "other" and _TURNOVER_RE.search(desc)):
        return tid, _other_team(team_ids, tid)
    return current_team, current_team


def resolve_segments(actions: List[Dict[str, Any]], mode: str = "semantic") -> List[Dict[str, Any]]:
    """One row per PBP action: action_number, period, elapsed_s, seg_team,
    seg_start_s. mode='cdn_field' trusts the file's own `possession` field
    (CDN-native only); mode='semantic' uses only the 4 rules above (works on
    either shape, but is the ONLY option ESPN-derived files have)."""
    actions = sorted(actions, key=lambda a: a["actionNumber"])
    team_ids = sorted({a["teamId"] for a in actions if a.get("teamId")})
    out: List[Dict[str, Any]] = []
    current_team: Optional[int] = None
    seg_start = 0.0
    last_period: Optional[int] = None
    prev_possession: Optional[int] = None

    for a in actions:
        period = a["period"]
        elapsed = _elapsed_s(period, a["clock"])
        if period != last_period:
            current_team, seg_start, prev_possession = None, elapsed, None
            last_period = period

        if mode == "cdn_field":
            poss = a.get("possession")
            if poss and poss != prev_possession:
                current_team, seg_start = poss, elapsed
            if poss:
                prev_possession = poss
            out_team, out_start = current_team, seg_start
        else:
            row_team, next_team = _resolve_row(a, team_ids, current_team)
            if row_team is not None and row_team != current_team:
                current_team, seg_start = row_team, elapsed
            # this row's own team/start is captured BEFORE applying next_team's
            # forward-looking flip (a made shot/turnover still belongs to the
            # team that just acted; the flip only affects rows AFTER this one)
            out_team, out_start = current_team, seg_start
            if next_team is not None and next_team != current_team:
                current_team, seg_start = next_team, elapsed

        out.append({
            "action_number": a["actionNumber"], "period": period, "elapsed_s": elapsed,
            "seg_team": out_team, "seg_start_s": out_start,
        })
    return out


def _detect_mode(actions: List[Dict[str, Any]]) -> str:
    return "cdn_field" if any("possession" in a for a in actions[:20]) else "semantic"


def build_shot_clock_frame(pbp_dir: Path = _PBP_DIR, limit: Optional[int] = None) -> pd.DataFrame:
    """One row per 2pt/3pt shot attempt with the derived shot_clock_proxy
    (clipped [0,24]) plus the unclipped raw_since_start for validation."""
    files = sorted(pbp_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    rows: List[Dict[str, Any]] = []
    for fp in files:
        d = json.loads(fp.read_text(encoding="utf-8"))
        game_id = d["game"]["gameId"]
        actions = d["game"]["actions"]
        mode = _detect_mode(actions)
        resolved = {r["action_number"]: r for r in resolve_segments(actions, mode=mode)}
        for a in actions:
            if a.get("actionType") not in ("2pt", "3pt") or not a.get("teamId"):
                continue
            r = resolved[a["actionNumber"]]
            if r["seg_team"] is None:
                continue  # unresolved (first action(s) of a period) -- skip, not a broken value
            raw_since_start = r["elapsed_s"] - r["seg_start_s"]
            rows.append({
                "game_id": game_id, "team_id": a["teamId"], "period": a["period"],
                "elapsed_s": r["elapsed_s"], "raw_since_start": raw_since_start,
                "made": int(a.get("shotResult") == "Made"),
                "shot_clock_proxy": min(max(SHOT_CLOCK_S - raw_since_start, 0.0), SHOT_CLOCK_S),
                "source_mode": mode,
            })
    return pd.DataFrame(rows)


def validate_distribution(df: pd.DataFrame) -> Dict[str, Any]:
    """Bullet (a): raw_since_start must mostly live in [0,24] (i.e. proxy
    un-clipped in [0,24]). pct_negative = time-since-start > 24s (clipped to
    0 -- a stale/likely-broken or OREB-extended possession); pct_over_shot_clock
    is the same quantity, named for what it means physically."""
    n = len(df)
    if n == 0:
        return {"n": 0, "pct_negative": None, "mean": None, "median": None}
    negative = (df["raw_since_start"] > SHOT_CLOCK_S).sum()
    return {
        "n": int(n), "pct_negative": float(negative) / n,
        "mean": float(df["shot_clock_proxy"].mean()), "median": float(df["shot_clock_proxy"].median()),
    }


def cdn_semantic_agreement(pbp_dir: Path = _PBP_DIR, limit: Optional[int] = None) -> Dict[str, Any]:
    """Bullet (b): on CDN-native files only, run the semantic (ESPN-style)
    inference blind to the real `possession` field, then compare per-action
    team assignment against that real field. This is the ONLY place we can
    check the semantic logic against ground truth -- it calibrates how much
    to trust the identical logic running unchecked on the 996 ESPN files."""
    files = [fp for fp in sorted(pbp_dir.glob("*.json"))
             if _detect_mode(json.loads(fp.read_text(encoding="utf-8"))["game"]["actions"]) == "cdn_field"]
    if limit:
        files = files[:limit]
    n_compared = n_agree = n_skipped = 0
    for fp in files:
        actions = json.loads(fp.read_text(encoding="utf-8"))["game"]["actions"]
        semantic = {r["action_number"]: r["seg_team"] for r in resolve_segments(actions, mode="semantic")}
        truth = {r["action_number"]: r["seg_team"] for r in resolve_segments(actions, mode="cdn_field")}
        for num, sem_team in semantic.items():
            if sem_team is None:
                n_skipped += 1
                continue
            n_compared += 1
            if sem_team == truth.get(num):
                n_agree += 1
    agreement = (n_agree / n_compared) if n_compared else None
    return {"n_games": len(files), "n_compared": n_compared, "n_agree": n_agree,
            "n_skipped_unknown": n_skipped, "agreement_pct": agreement}


def main() -> int:
    df = build_shot_clock_frame()
    dist = validate_distribution(df)
    agree = cdn_semantic_agreement()
    print(f"shot_clock_proxy: n_shots={dist['n']} pct_over24(negative-before-clip)={dist['pct_negative']:.4f} "
          f"mean={dist['mean']:.2f} median={dist['median']:.2f}")
    print(f"cdn_semantic_agreement: n_games={agree['n_games']} n_compared={agree['n_compared']} "
          f"agreement_pct={agree['agreement_pct']:.4f} n_skipped_unknown={agree['n_skipped_unknown']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
