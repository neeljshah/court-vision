"""market_coverage.corpora -- REAL-close corpus state-builders for the edge-finder.

Each builder reads a local domain corpus and returns eval-gate states
(game_id, home, away, state_ts, outcome, devig_close_prob) for ONE has-close MAINLINE market.
These are the ONLY markets with real historical close data locally; every obscure/prop/SGP/
in-game-micro market has NO local close (priceable+calibratable, but validatable only via
forward capture). The reference we score against is the SHIN-devigged close, devigged here via
the verified eval_gate.shin reference (READ-ONLY reuse) -- never a live re-poll, never invented.

Leak-freeness is enforced by walk_forward itself (the builder only supplies the close + the
realized outcome + a monotonic per-game timestamp; the model predict_fn learns from the train
slice only). ASCII only. <=300 LOC. Tested via tests/test_edge_finder.py (integration).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# READ-ONLY reuse of the verified Shin devig reference. Package + bare-run fallbacks.
try:
    from scripts.platformkit.eval_gate.shin import shin_devig_decimal
except ImportError:  # direct-script / per-file-test fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval_gate"))
    from shin import shin_devig_decimal  # type: ignore

SOCCER_CAP = 2500        # cap the soccer corpus slice (walk_forward is O(n^2)); recent + >MIN_N
_CANON = {"GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}


# ---------------------------------------------------------------------------
# Devig helpers -- the SHIN-devigged close is the ONLY reference we score against.
# ---------------------------------------------------------------------------
def _american_to_decimal(ml: float) -> float:
    ml = float(ml)
    return 1.0 + (100.0 / -ml if ml < 0 else ml / 100.0)


def devig_two_way(price_a: float, price_b: float, american: bool = True) -> float:
    """SHIN-devigged fair P(side A) from a 2-way market. Reuses the verified shin reference."""
    da = _american_to_decimal(price_a) if american else float(price_a)
    db = _american_to_decimal(price_b) if american else float(price_b)
    probs, _z = shin_devig_decimal([da, db])
    return float(probs[0])


# ---------------------------------------------------------------------------
# Corpus state-builders for the MAINLINE markets that DO have real local close data.
# ---------------------------------------------------------------------------
def nba_ml_states(root: Path) -> List[dict]:
    """NBA moneyline -- the liquid mainline reference (expect MATCH/REJECT, never SHIP)."""
    import pandas as pd
    box = pd.read_parquet(root / "espn_boxscores.parquet").copy()
    # home_score/away_score are the reliable score columns (home_pts is sparse for recent games)
    box["hs"] = box["home_score"].where(box["home_score"].notna(), box.get("home_pts"))
    box["as"] = box["away_score"].where(box["away_score"].notna(), box.get("away_pts"))
    box = box.dropna(subset=["hs", "as"])
    box["date"] = pd.to_datetime(box["date"]).dt.normalize()
    for c in ("home_abbr", "away_abbr"):
        box[c] = box[c].astype(str).str.upper().replace(_CANON)
    odds = pd.read_parquet(root / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    odds["date"] = pd.to_datetime(odds["date"]).dt.normalize()
    for c in ("home_abbr", "away_abbr"):              # canon BOTH sides so the join lands
        odds[c] = odds[c].astype(str).str.upper().replace(_CANON)
    odds = odds.dropna(subset=["home_ml", "away_ml"])
    m = box.merge(odds[["date", "home_abbr", "away_abbr", "home_ml", "away_ml"]],
                  on=["date", "home_abbr", "away_abbr"], how="inner").reset_index(drop=True)
    states: List[dict] = []
    for i, r in m.iterrows():
        try:
            pc = devig_two_way(r["home_ml"], r["away_ml"], american=True)
        except Exception:
            continue
        # unique monotonic timestamp per game so purge/embargo never collapse the sample
        ts = (r["date"] + pd.Timedelta(minutes=int(i))).isoformat()
        states.append({
            "game_id": f"nba-{r['date'].date()}-{r['home_abbr']}-{r['away_abbr']}",
            "home": str(r["home_abbr"]), "away": str(r["away_abbr"]),
            "state_ts": ts, "outcome": int(r["hs"] > r["as"]), "devig_close_prob": pc,
        })
    return states


def mlb_ml_states(root: Path) -> List[dict]:
    """MLB moneyline -- declared has-close, but the local box/odds id-spaces do not join
    (ESPN numeric event_id vs date-team odds id) -> returns [] -> honest DATA_LIMITED."""
    import pandas as pd
    odds = pd.read_parquet(root / "odds.parquet")
    box = pd.read_parquet(root / "espn_boxscores.parquet")
    if not {"ml_close_home_am", "ml_close_away_am"}.issubset(odds.columns):
        return []
    if "event_id" not in odds.columns or "event_id" not in box.columns:
        return []
    odds = odds.dropna(subset=["ml_close_home_am", "ml_close_away_am"]).copy()
    bc = {c.lower(): c for c in box.columns}
    hp = bc.get("home_pts") or bc.get("home_score") or bc.get("home_runs")
    ap = bc.get("away_pts") or bc.get("away_score") or bc.get("away_runs")
    ha = bc.get("home_abbr") or bc.get("home_team")
    aa = bc.get("away_abbr") or bc.get("away_team")
    if not all([hp, ap, ha, aa]):
        return []
    box = box.dropna(subset=[hp, ap]).copy()
    m = box.merge(odds, on="event_id", how="inner", suffixes=("", "_o")).reset_index(drop=True)
    if len(m) == 0:
        return []
    states: List[dict] = []
    for i, r in m.iterrows():
        try:
            pc = devig_two_way(r["ml_close_home_am"], r["ml_close_away_am"], american=True)
        except Exception:
            continue
        ts = (pd.Timestamp("2010-01-01") + pd.Timedelta(minutes=int(i))).isoformat()
        states.append({
            "game_id": f"mlb-{r[ha]}-{r[aa]}-{i}", "home": str(r[ha]), "away": str(r[aa]),
            "state_ts": ts, "outcome": int(float(r[hp]) > float(r[ap])), "devig_close_prob": pc,
        })
    return states


def soccer_ou25_states(root: Path) -> List[dict]:
    """Soccer Over-2.5-goals -- a REAL has-close totals market (decimal over/under close).

    outcome = target_over25 (total_goals > 2.5); close = SHIN-devigged over prob from the closing
    decimal over/under prices. Modeled side = OVER 2.5. Capped to the recent SOCCER_CAP slice
    (walk_forward is O(n^2)); the cap keeps the gate tractable while staying well above MIN_N.
    """
    import pandas as pd
    odds = pd.read_parquet(root / "odds.parquet")
    matches = pd.read_parquet(root / "matches.parquet")
    if "event_id" not in odds.columns or "event_id" not in matches.columns:
        return []
    if not {"ou_close_over", "ou_close_under"}.issubset(odds.columns):
        return []
    odds = odds.dropna(subset=["ou_close_over", "ou_close_under"]).copy()
    ocol = "target_over25" if "target_over25" in matches.columns else None
    if ocol is None and "total_goals" in matches.columns:
        matches["target_over25"] = (matches["total_goals"] > 2.5).astype(int)
        ocol = "target_over25"
    if ocol is None:
        return []
    m = matches.merge(odds[["event_id", "ou_close_over", "ou_close_under"]],
                      on="event_id", how="inner").dropna(subset=[ocol]).reset_index(drop=True)
    m["date"] = pd.to_datetime(m.get("date"), errors="coerce")
    m = m.sort_values("date").reset_index(drop=True)
    if len(m) > SOCCER_CAP:
        m = m.tail(SOCCER_CAP).reset_index(drop=True)
    states: List[dict] = []
    for i, r in m.iterrows():
        try:
            pc = devig_two_way(r["ou_close_over"], r["ou_close_under"], american=False)
        except Exception:
            continue
        d = r["date"] if pd.notna(r["date"]) else pd.Timestamp("2015-01-01")
        ts = (d + pd.Timedelta(minutes=int(i))).isoformat()
        # 'home'/'away' carry team labels purely so purge/embargo can run; outcome = OVER hit
        states.append({
            "game_id": f"soc-{r['event_id']}",
            "home": str(r.get("home_team", f"H{i}")), "away": str(r.get("away_team", f"A{i}")),
            "state_ts": ts, "outcome": int(r[ocol]), "devig_close_prob": pc,
        })
    return states
