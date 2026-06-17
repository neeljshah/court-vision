"""grade_live.py -- settle logged live predictions from REAL final scores.

Completes the forward loop: run_live logs the model's pregame prediction on real
games; once a game is Final, this fills its `outcome` in the ledger so the
record becomes a MEASURED result (accuracy / Brier / CLV via status.py).

Reuses the existing immutable grader (ledger/grade_outcomes.grade_outcomes,
read-only otherwise): matches on pred_id, never overwrites a graded row, asserts
the vintage guard. We only supply {pred_id: {outcome}} from public final scores
(MLB stats API, keyless). Network degrades to {} (no crash). No edge claimed.
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request
from typing import Dict, Optional

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def fetch_mlb_finals(date: str = "") -> Dict[str, int]:
    """Return {game_id(str): home_win 0/1} for FINAL MLB games on `date`
    (YYYY-MM-DD; "" = today on the server). {} on any network/parse error."""
    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
    if date:
        url += "&date=%s" % date
    try:
        with urllib.request.urlopen(url, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}
    out: Dict[str, int] = {}
    for d in data.get("dates", []):
        for g in d.get("games", []):
            try:
                state = (g.get("status", {}) or {}).get("abstractGameState", "")
                if state != "Final":
                    continue
                teams = g["teams"]
                hs = teams["home"].get("score")
                as_ = teams["away"].get("score")
                if hs is None or as_ is None:
                    continue
                out[str(g.get("gamePk", ""))] = 1 if hs > as_ else 0
            except Exception:
                continue
    return out


def grade_from_ledger(base_dir: Optional[str] = None, date: str = "",
                      finals: Optional[Dict[str, int]] = None,
                      sport: str = "mlb") -> dict:
    """Settle ungraded `sport` predictions in the ledger from final scores.

    Pass `finals` to inject results (tests / offline); otherwise fetched live.
    Returns the grader summary plus how many finals were available/applied.
    """
    from scripts.platformkit.ledger.ledger import read_ledger  # reuse, read-only
    from scripts.platformkit.ledger.grade_outcomes import grade_outcomes  # reuse

    df = read_ledger(base_dir=base_dir)
    base = {"matched": 0, "filled": 0, "finals_available": 0, "ungraded": 0}
    if df is None or df.empty:
        return base

    ungraded = df[(df["sport"] == sport) & (df["outcome"].isna())]
    base["ungraded"] = int(len(ungraded))
    if ungraded.empty:
        return base

    if finals is None:
        finals = {}
        for d in {str(x) for x in ungraded["game_date"].tolist() if x}:
            finals.update(fetch_mlb_finals(d))
    base["finals_available"] = len(finals)

    outcomes: Dict[str, dict] = {}
    for _, row in ungraded.iterrows():
        gid = str(row.get("game_id", ""))
        if gid and gid in finals:
            outcomes[str(row["pred_id"])] = {"outcome": int(finals[gid])}
    if not outcomes:
        return base

    summary = grade_outcomes(outcomes, base_dir=base_dir)
    summary["finals_available"] = base["finals_available"]
    summary["ungraded"] = base["ungraded"]
    return summary


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Settle live predictions from finals")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default today)")
    ap.add_argument("--sport", default="mlb")
    a = ap.parse_args(argv)
    s = grade_from_ledger(date=a.date, sport=a.sport)
    print("grade_live: %s" % s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
