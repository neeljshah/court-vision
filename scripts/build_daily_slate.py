"""build_daily_slate.py — INT-85 Daily Slate Ranking Generator.

Fuses prop predictions + confidence + bias + matchup + odds into a ranked
top-N highest-EV bet list per day.

Pipeline (9 stages):
  1. load_slate_games(date)
  2. build_player_universe (drop OUT/DOUBTFUL/NWT)
  3. predict_pergame per player
  4. apply bias_shift (INT-69 per_player_calibration)
  5. attach confidence tier (INT-77 confidence_ensemble + INT-16 per_player_confidence)
  6. attach CV coverage gate (INT-53 cv_coverage_gates); warn -> confidence -=1; skip CV stats
  7. attach matchup composite (INT-63 matchup_grid); mu'' = mu' × (1 + 0.10 × composite); clamp ±0.5
  8. attach lines from data/props/props_<date>.json; over_p from Normal(mu'', sigma); EV; Kelly
  9. rank by score = edge_pp × kelly_b_mult × confidence_weight; filter; truncate to --top N

Usage:
    python scripts/build_daily_slate.py --date 2026-05-29 --top 20 --min-edge 0.5 --bankroll 1000
    python scripts/build_daily_slate.py --date 2025-02-28 --dry-run
    python scripts/build_daily_slate.py --date 2026-05-29 --no-lines
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import warnings
from datetime import datetime, date as _date
from typing import Dict, List, Optional, Tuple

# ── bootstrap path ────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
warnings.filterwarnings("ignore", message="X does not have valid feature names")
warnings.filterwarnings("ignore", category=UserWarning)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import src.data.nba_api_headers_patch  # noqa: F401,E402 — must be first

import numpy as np

# ── constants ─────────────────────────────────────────────────────────────────
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
# Stats derived from CV features — gate='skip' if no CV coverage
CV_DERIVED_STATS: set = set()  # currently none ship; guard is structural

# Confidence tiers and their scoring weights (recipe spec)
_CONF_WEIGHT = {"high": 1.0, "med": 0.7, "low": 0.4}
_DEFAULT_CONF = "med"

# Kelly-B multiplier per confidence tier
_KELLY_B_MULT = {"high": 1.0, "med": 0.75, "low": 0.50}

# Matchup composite clamp
_MATCHUP_CLAMP = 0.5  # clamp 1 + 0.10 × composite to [0.5, 1.5]

# Stat-level sigma from quantile_calibration.json (80% CI → sigma)
# Pre-computed: sigma = cal_avg_width / (2 * 1.2816)
_SIGMA_FALLBACK = {
    "pts": 5.443, "reb": 2.309, "ast": 1.793,
    "fg3m": 0.841, "stl": 0.534, "blk": 0.389, "tov": 0.862,
}

_API_SLEEP = 0.6
_NBA_CACHE = os.path.join(ROOT, "data", "nba")
_MODEL_DIR = os.path.join(ROOT, "data", "models")
_INTEL_DIR = os.path.join(ROOT, "data", "intelligence")
_PROPS_DIR = os.path.join(ROOT, "data", "props")
_OUT_DIR   = os.path.join(ROOT, "data", "intelligence")
_VAULT_DIR = os.path.join(ROOT, "vault", "Intelligence", "Daily_Slates")
_INDEX_PATH = os.path.join(ROOT, "vault", "Intelligence", "_Slate_Index.md")
_INT85_PATH = os.path.join(ROOT, "vault", "Intelligence", "INT-85_Daily_Slate.md")


# ── season detection ──────────────────────────────────────────────────────────

def _detect_season(d: _date) -> str:
    start = d.year if d.month >= 10 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


# ── odds helpers (mirrors compare_to_lines.py) ────────────────────────────────

def _american_to_implied_prob(odds: int) -> float:
    odds = int(odds)
    if odds > 0:
        return 100 / (odds + 100)
    return -odds / (-odds + 100)


def _american_payout(odds: int, stake: float = 1.0) -> float:
    odds = int(odds)
    if odds > 0:
        return stake * (odds / 100)
    return stake * (100 / -odds)


def _normal_over_prob(mu: float, sigma: float, line: float) -> float:
    """P(X > line) under Normal(mu, sigma)."""
    sigma = max(sigma, 1e-6)
    z = (line - mu) / sigma
    return 0.5 * (1 - math.erf(z / math.sqrt(2)))


def _kelly_fraction(prob: float, odds: int) -> float:
    b = _american_payout(odds, 1.0)
    f = (b * prob - (1 - prob)) / b
    return max(0.0, f)


# ── game fetching (reuse predict_slate.py logic) ─────────────────────────────

def _team_abbrev_lookup() -> Dict[int, str]:
    try:
        from nba_api.stats.static import teams
        return {int(t["id"]): str(t["abbreviation"]) for t in teams.get_teams()}
    except Exception:
        return {}


def fetch_games(date_str: str) -> List[Dict]:
    """Return [{game_id, home_id, away_id, home_abbrev, away_abbrev}]."""
    id_to_abbrev = _team_abbrev_lookup()
    games: List[Dict] = []
    try:
        from nba_api.stats.library.http import NBAStatsHTTP
        resp = NBAStatsHTTP().send_api_request(
            endpoint="scoreboardv2",
            parameters={"GameDate": date_str, "LeagueID": "00", "DayOffset": 0},
        )
        time.sleep(_API_SLEEP)
        data = resp.get_dict()
        result_sets = data.get("resultSets") or []
        gh = next((s for s in result_sets if s.get("name") == "GameHeader"), None)
        if not gh:
            return []
        headers = gh.get("headers") or []
        idx = {col: i for i, col in enumerate(headers)}
        for row in gh.get("rowSet") or []:
            try:
                home_id = int(row[idx["HOME_TEAM_ID"]])
                away_id = int(row[idx["VISITOR_TEAM_ID"]])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            home_abbrev = id_to_abbrev.get(home_id, "")
            away_abbrev = id_to_abbrev.get(away_id, "")
            if not home_abbrev or not away_abbrev:
                gc = str(row[idx.get("GAMECODE", 0)]) if "GAMECODE" in idx else ""
                if "/" in gc:
                    token = gc.split("/", 1)[1]
                    if len(token) >= 6:
                        away_abbrev = away_abbrev or token[:3]
                        home_abbrev = home_abbrev or token[3:6]
            games.append({
                "game_id":     str(row[idx.get("GAME_ID", 0)]) if "GAME_ID" in idx else "",
                "home_id":     home_id,
                "away_id":     away_id,
                "home_abbrev": home_abbrev,
                "away_abbrev": away_abbrev,
            })
    except Exception as e:
        print(f"  [warn] scoreboard fetch failed: {e}")
    return games


def fetch_roster(team_id: int, season: str) -> List[Tuple[int, str]]:
    from nba_api.stats.endpoints import commonteamroster
    cr = commonteamroster.CommonTeamRoster(team_id=team_id, season=season)
    time.sleep(_API_SLEEP)
    df = cr.common_team_roster.get_data_frame()
    out = []
    for _, row in df.iterrows():
        try:
            out.append((int(row["PLAYER_ID"]), str(row["PLAYER"])))
        except Exception:
            continue
    return out


# ── injury loading ────────────────────────────────────────────────────────────

def _load_injuries(date_str: str) -> Dict[str, str]:
    """Return {lowercase_name: status} for unavailable players."""
    path = os.path.join(ROOT, "data", f"injuries_{date_str}.json")
    if not os.path.exists(path):
        # Try the most-recent injuries file
        import glob
        files = sorted(glob.glob(os.path.join(ROOT, "data", "injuries_*.json")))
        if files:
            path = files[-1]
            print(f"  [injuries] using most recent file: {os.path.basename(path)}")
        else:
            return {}
    try:
        from src.data.injuries import load_unavailable_players
        return load_unavailable_players(path)
    except Exception as e:
        print(f"  [warn] injury load failed: {e}")
        return {}


# ── INT-69: per-player bias shift ─────────────────────────────────────────────

def _load_bias_shifts(date_str: str) -> Dict:
    """Load per_player_calibration.parquet as nested dict: {(player_id, stat): shift}."""
    path = os.path.join(_INTEL_DIR, "per_player_calibration.parquet")
    if not os.path.exists(path):
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(path)
        # Use the most recent asof_date <= date_str per (player_id, stat)
        df = df[df["asof_date"] <= date_str]
        if df.empty:
            return {}
        # Latest row per (player_id, stat)
        df = df.sort_values("asof_date").groupby(["player_id", "stat"]).last().reset_index()
        result = {}
        for _, row in df.iterrows():
            result[(int(row["player_id"]), str(row["stat"]))] = float(
                row.get("bias_shift_applied", 0.0) or 0.0
            )
        return result
    except Exception as e:
        print(f"  [warn] bias shift load failed: {e}")
        return {}


# ── INT-77/INT-16: confidence tier ────────────────────────────────────────────

def _load_confidence_tiers(date_str: str) -> Dict:
    """Load confidence as {(player_id, stat): 'high'|'med'|'low'}."""
    # Primary: confidence_ensemble.parquet (INT-77 / INT-16)
    path = os.path.join(_INTEL_DIR, "confidence_ensemble.parquet")
    if not os.path.exists(path):
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(path)
        # Filter to most recent asof_date <= date_str
        df = df[df["asof_date"] <= date_str]
        if df.empty:
            return {}
        df = df.sort_values("asof_date").groupby(["player_id", "stat"]).last().reset_index()
        # coverage_class maps to confidence tier:
        # 'partial' (has some CV signals) → 'med', 'thin' → 'low'
        # Also check mult_A/mult_B magnitudes: >1.05 or <0.95 → 'high', ~1.0 → 'med'
        result = {}
        for _, row in df.iterrows():
            cclass = str(row.get("coverage_class", "thin"))
            mult_a = float(row.get("mult_A", 1.0) or 1.0)
            # Tier logic: strong signal → high; some signal → med; thin → low
            deviation = abs(mult_a - 1.0)
            if cclass == "partial" and deviation >= 0.03:
                tier = "high"
            elif cclass == "partial":
                tier = "med"
            else:
                tier = "low"
            result[(int(row["player_id"]), str(row["stat"]))] = tier
        return result
    except Exception as e:
        print(f"  [warn] confidence load failed: {e}")
        return {}


def _load_per_player_confidence(date_str: str) -> Dict:
    """Secondary confidence source: per_player_confidence.parquet (INT-16).
    Returns {player_id: 'high'|'med'|'low'}.
    """
    path = os.path.join(_INTEL_DIR, "per_player_confidence.parquet")
    if not os.path.exists(path):
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(path)
        result = {}
        for _, row in df.iterrows():
            seg = str(row.get("segment", "loose"))
            # segment='medium' → 'med'; 'loose' (high volatility) → 'low'
            tier = "med" if seg == "medium" else "low"
            result[int(row["player_id"])] = tier
        return result
    except Exception as e:
        print(f"  [warn] per_player_confidence load failed: {e}")
        return {}


# ── INT-53: CV coverage gate ──────────────────────────────────────────────────

def _load_cv_gates(date_str: str) -> Dict:
    """Return {player_id: 'warn'|'ok'} based on cv_coverage_gates.parquet."""
    path = os.path.join(_INTEL_DIR, "cv_coverage_gates.parquet")
    if not os.path.exists(path):
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(path)
        df["game_date"] = pd.to_datetime(df["game_date"]).dt.date.astype(str)
        df = df[df["game_date"] <= date_str]
        if df.empty:
            return {}
        df = df.sort_values("game_date").groupby("nba_player_id").last().reset_index()
        result = {}
        for _, row in df.iterrows():
            # coverage_gate < 0.5 → warn (sparse CV history)
            gate_val = float(row.get("coverage_gate", 0.0) or 0.0)
            result[int(row["nba_player_id"])] = "warn" if gate_val < 0.5 else "ok"
        return result
    except Exception as e:
        print(f"  [warn] CV gate load failed: {e}")
        return {}


# ── INT-63: matchup composite ─────────────────────────────────────────────────

def _load_matchup_composites(
    date_str: str, games: List[Dict], matchup_window_days: int = 45
) -> Dict:
    """Return {(team_abbrev, opp_abbrev): (composite_score, atlas_density)}.

    composite_score is the mean of the two shipped interactions:
    mx_tempo_vs_opp_pace + mx_offense_vs_defense_composite.

    matchup_window_days: only consider atlas rows within this many days of
    date_str (INT-96A FIX #3 — prevents stale playoff-era pairs polluting
    regular-season dates).  Default 45.
    """
    path = os.path.join(_INTEL_DIR, "matchup_grid.parquet")
    if not os.path.exists(path):
        return {}
    try:
        import pandas as pd
        from datetime import timedelta
        df = pd.read_parquet(path)
        d_end = date_str
        try:
            from datetime import datetime as _dt
            d_start = (_dt.strptime(date_str, "%Y-%m-%d").date()
                       - timedelta(days=matchup_window_days)).isoformat()
        except Exception:
            d_start = "1900-01-01"
        df = df[(df["game_date"] >= d_start) & (df["game_date"] <= d_end)]
        if df.empty:
            return {}
        # Get the latest game's matchup for each (team, opp) pair within window
        df = df.sort_values("game_date").groupby(["team_id", "opp_team_id"]).last().reset_index()
        result = {}
        mg_pair_miss = 0  # INT-96A: counter for default-fallback (miss) keys
        for _, row in df.iterrows():
            team = str(row["team_id"])
            opp  = str(row["opp_team_id"])
            mx1  = float(row.get("mx_tempo_vs_opp_pace", 0.0) or 0.0)
            mx2  = float(row.get("mx_offense_vs_defense_composite", 0.0) or 0.0)
            composite = (mx1 + mx2) / 2.0
            density = str(row.get("data_density", "league_prior"))
            result[(team, opp)] = (composite, density)
        # Count how many (team, opp) pairs from today's games lack a matchup key
        for game in games:
            for ta, oa in [
                (game.get("home_abbrev", ""), game.get("away_abbrev", "")),
                (game.get("away_abbrev", ""), game.get("home_abbrev", "")),
            ]:
                if ta and oa and (ta, oa) not in result:
                    mg_pair_miss += 1
        if mg_pair_miss:
            print(f"  [matchup] mg_pair_miss={mg_pair_miss} "
                  f"(pairs falling back to league_prior defaults)")
        return result
    except Exception as e:
        print(f"  [warn] matchup composite load failed: {e}")
        return {}


# ── props file ────────────────────────────────────────────────────────────────

def _load_props(date_str: str) -> List[Dict]:
    """Load props_<date>.json. Returns [] when missing or empty."""
    path = os.path.join(_PROPS_DIR, f"props_{date_str}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            return []
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ── player prediction ─────────────────────────────────────────────────────────

def _player_l5_pts(player_id: int, season: str) -> float:
    from src.prediction.prop_pergame import _num, _MIN_PLAYED
    path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(path):
        # try prior season
        try:
            start = int(season[:4]) - 1
            prev = f"{start}-{str(start + 1)[-2:]}"
        except (ValueError, TypeError):
            return 0.0
        path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{prev}.json")
        if not os.path.exists(path):
            return 0.0
    try:
        games = json.load(open(path, encoding="utf-8"))
        played = [g for g in games if _num(g.get("MIN")) >= _MIN_PLAYED]
        recent = played[-5:]
        if not recent:
            return 0.0
        return sum(_num(g.get("PTS")) for g in recent) / len(recent)
    except Exception:
        return 0.0


def _predict_all_stats(
    player_id: int, opp: str, season: str, is_home: bool, rest_days: float
) -> Optional[Dict[str, float]]:
    """Return {stat: pred} dict or None on failure. Uses PROTECTED predict_player_pergame."""
    try:
        from src.prediction.prop_pergame import predict_player_pergame
        return predict_player_pergame(
            player_id, opp, season,
            is_home=is_home, rest_days=rest_days,
            gamelog_dir=_NBA_CACHE, model_dir=_MODEL_DIR,
        )
    except Exception:
        return None


def _predict_quantiles(
    player_id: int, opp: str, season: str, is_home: bool, rest_days: float
) -> Dict[str, Optional[Dict]]:
    """Return {stat: {q25, q75}} using the stat-level sigma fallback.

    q25 = mu - 0.6745*sigma, q75 = mu + 0.6745*sigma
    (Normal approximation — XGB quantile models are unavailable due to 85 vs 129
    feature count mismatch between training and current feature set.)
    """
    try:
        from src.prediction.prop_pergame import build_prediction_row, predict_pergame
        prow = build_prediction_row(
            player_id, opp, season, is_home=is_home, rest_days=rest_days,
            gamelog_dir=_NBA_CACHE,
        )
        if prow is None:
            return {}
        result = {}
        for stat in STATS:
            pred = predict_pergame(stat, prow, _MODEL_DIR)
            if pred is None:
                continue
            sigma = _SIGMA_FALLBACK.get(stat, 3.0)
            result[stat] = {
                "q25": max(0.0, pred - 0.6745 * sigma),
                "q75": max(0.0, pred + 0.6745 * sigma),
            }
        return result
    except Exception:
        return {}


# ── stage 6: CV gate application ──────────────────────────────────────────────

def _apply_cv_gate(
    stat: str, player_id: int, cv_gates: Dict, current_confidence: str
) -> Tuple[str, str]:
    """Returns (new_confidence, gate_status).
    gate_status: 'ok' | 'warn' | 'skip'
    """
    if stat in CV_DERIVED_STATS:
        if cv_gates.get(player_id) == "warn":
            return current_confidence, "skip"  # skip CV-derived stats with no coverage
    gate_status = cv_gates.get(player_id, "ok")
    if gate_status == "warn":
        # Downgrade confidence one tier
        tier_order = ["high", "med", "low"]
        idx = tier_order.index(current_confidence) if current_confidence in tier_order else 1
        new_conf = tier_order[min(idx + 1, 2)]
        return new_conf, "warn"
    return current_confidence, "ok"


# ── stage 9: scoring + ranking ────────────────────────────────────────────────

def _score_row(row: Dict) -> float:
    """score = edge_pp × kelly_b_mult × confidence_weight."""
    edge_pp = abs(row.get("edge_pp", 0.0))
    kelly_mult = _KELLY_B_MULT.get(row.get("confidence", _DEFAULT_CONF), 0.7)
    conf_weight = _CONF_WEIGHT.get(row.get("confidence", _DEFAULT_CONF), 0.7)
    return edge_pp * kelly_mult * conf_weight


# ── filter pass ───────────────────────────────────────────────────────────────

def _passes_filters(
    row: Dict,
    min_edge: float,
    no_lines: bool,
) -> Tuple[bool, str]:
    """Return (passes, drop_reason). Recipe filters applied in order."""
    edge_pp = row.get("edge_pp", 0.0)
    conf = row.get("confidence", _DEFAULT_CONF)
    density = row.get("atlas_density", "league_prior")
    gate = row.get("gate_status", "ok")

    if gate == "skip":
        return False, "cv_gate=skip"
    if edge_pp < min_edge:
        return False, f"edge_pp={edge_pp:.2f}<{min_edge}"
    if conf == "low" and edge_pp < 2.0:
        return False, "low_conf+edge<2pp"
    # INT-96A FIX #1: relaxed — only drop league_prior rows when conf is "low"
    # (previously "conf != 'high'" blocked valid med-confidence rows)
    if density == "league_prior" and conf == "low":
        return False, "league_prior_density+low_conf"
    if no_lines and row.get("line") is None:
        # In --no-lines mode, keep all predictions regardless of line
        return True, ""
    return True, ""


# ── main pipeline ─────────────────────────────────────────────────────────────

def build_slate(
    date_str: str,
    top_n: int = 20,
    min_edge: float = 0.5,
    bankroll: float = 1000.0,
    dry_run: bool = False,
    no_lines: bool = False,
    season: Optional[str] = None,
    rest_days: float = 2.0,
    matchup_window_days: int = 45,
    no_calibration: bool = False,  # INT-100: kill switch for INT-69 bias_shift
) -> Dict:
    """Run the full 9-stage pipeline and return the output dict."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    season = season or _detect_season(d)
    generated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    print(f"\n  [INT-85] Slate: {date_str}  season={season}  top={top_n}  "
          f"min_edge={min_edge}pp  bankroll=${bankroll:.0f}"
          f"  dry_run={dry_run}  no_lines={no_lines}"
          f"  no_calibration={no_calibration}")

    # Stage 1: load games
    print("\n  Stage 1: load slate games...")
    games = fetch_games(date_str)
    print(f"    {len(games)} game(s) found.")
    if not games:
        return _empty_slate(date_str, generated_at, 0)

    # Stage 2: build player universe (drop OUT/DOUBTFUL/NWT)
    print("  Stage 2: build player universe...")
    injuries = _load_injuries(date_str)
    print(f"    {len(injuries)} unavailable players loaded.")

    # Stage 3-8: per-player predictions
    print("  Stage 3-8: predicting + enriching...")
    bias_shifts   = {} if no_calibration else _load_bias_shifts(date_str)
    if no_calibration:
        print("    [INT-100] --no-calibration: bias_shift disabled (INT-69 kill switch)")
    conf_tiers    = _load_confidence_tiers(date_str)
    pp_confidence = _load_per_player_confidence(date_str)
    cv_gates      = _load_cv_gates(date_str)
    matchup_map   = _load_matchup_composites(date_str, games, matchup_window_days)
    props_data    = [] if no_lines else _load_props(date_str)

    # Build props lookup: {(player_lower, stat, side): {line, over_odds, under_odds}}
    props_lookup: Dict = {}
    for p in props_data:
        if not isinstance(p, dict):
            continue
        name_key = str(p.get("player", "")).lower()
        stat_key = str(p.get("stat", "")).lower()
        line_val = p.get("line")
        if line_val is None:
            continue
        try:
            line_val = float(line_val)
        except (ValueError, TypeError):
            continue
        props_lookup[(name_key, stat_key)] = {
            "line": line_val,
            "over_odds":  int(p.get("over_odds", -110) or -110),
            "under_odds": int(p.get("under_odds", -110) or -110),
        }

    n_props_with_line = len(props_lookup)
    print(f"    {n_props_with_line} prop lines loaded.")

    all_rows: List[Dict] = []
    n_universe = 0
    seen_player_stat: set = set()  # cap 1 bet per (player_id, stat)

    for game in games:
        home_id    = game["home_id"]
        away_id    = game["away_id"]
        home_abbrev = game["home_abbrev"] or f"T{home_id}"
        away_abbrev = game["away_abbrev"] or f"T{away_id}"

        for team_id, team_abbrev, opp_abbrev, is_home in [
            (home_id, home_abbrev, away_abbrev, True),
            (away_id, away_abbrev, home_abbrev, False),
        ]:
            try:
                roster = fetch_roster(team_id, season)
            except Exception as e:
                print(f"    [warn] roster fetch failed for {team_abbrev}: {e}")
                continue

            # Sort by L5 PTS desc (rotation proxy)
            ranked = sorted(
                [(pid, name, _player_l5_pts(pid, season)) for pid, name in roster],
                key=lambda t: t[2], reverse=True,
            )

            for pid, name, _l5 in ranked:
                # Stage 2 filter: skip unavailable players
                name_key = name.lower()
                status = injuries.get(name_key, "")
                if status in ("OUT", "DOUBTFUL", "NOT WITH TEAM"):
                    continue

                n_universe += 1

                # Stage 3: predict
                preds = _predict_all_stats(pid, opp_abbrev, season, is_home, rest_days)
                if not preds:
                    continue

                # Get quantile intervals for sigma
                qints = _predict_quantiles(pid, opp_abbrev, season, is_home, rest_days)

                for stat in STATS:
                    mu = preds.get(stat)
                    if mu is None:
                        continue

                    # Stage 4: bias shift (INT-69)
                    shift = bias_shifts.get((pid, stat), 0.0)
                    mu_prime = mu + shift

                    # Stage 5: confidence tier
                    conf = conf_tiers.get((pid, stat), None)
                    if conf is None:
                        # Fall back to INT-16 per-player segment
                        conf = pp_confidence.get(pid, _DEFAULT_CONF)

                    # Stage 6: CV coverage gate
                    conf, gate_status = _apply_cv_gate(stat, pid, cv_gates, conf)
                    if gate_status == "skip":
                        continue  # drop CV-derived stats with no coverage

                    # Stage 7: matchup composite (INT-63)
                    matchup_key = (team_abbrev, opp_abbrev)
                    composite_val, atlas_density = matchup_map.get(
                        matchup_key, (0.0, "league_prior")
                    )
                    # mu'' = mu' × (1 + 0.10 × composite), clamp factor to [0.5, 1.5]
                    factor = 1.0 + 0.10 * composite_val
                    factor = max(1.0 - _MATCHUP_CLAMP, min(1.0 + _MATCHUP_CLAMP, factor))
                    mu_pp = mu_prime * factor

                    # Stage 8: attach lines + EV + Kelly
                    prop_key = (name.lower(), stat)
                    prop_info = props_lookup.get(prop_key)

                    line = prop_info["line"] if prop_info else None
                    over_odds  = prop_info["over_odds"]  if prop_info else -110
                    under_odds = prop_info["under_odds"] if prop_info else -110

                    # Sigma from IQR or fallback
                    qint = qints.get(stat)
                    if qint:
                        sigma = max((qint["q75"] - qint["q25"]) / 1.349, 1e-6)
                    else:
                        sigma = _SIGMA_FALLBACK.get(stat, 3.0)

                    if line is not None:
                        edge = mu_pp - line
                        edge_pp = abs(edge) * 100 / max(line, 0.5)  # as a percentage of line
                        side = "OVER" if edge > 0 else "UNDER"
                        odds = over_odds if side == "OVER" else under_odds
                        over_prob = _normal_over_prob(mu_pp, sigma, line)
                        hit_prob = over_prob if side == "OVER" else (1 - over_prob)
                        net_payout = _american_payout(odds)
                        ev = hit_prob * net_payout - (1 - hit_prob) * 1.0
                        kf = _kelly_fraction(hit_prob, odds)
                        kelly_b = kf * 0.25  # Kelly-B: quarter Kelly
                        kelly_stake = round(kelly_b * bankroll, 2)
                        kelly_b_mult = _KELLY_B_MULT.get(conf, 0.7)
                    else:
                        edge = mu_pp  # vs zero (no-lines mode: edge = prediction magnitude)
                        edge_pp = abs(mu_pp) / max(_SIGMA_FALLBACK.get(stat, 3.0), 0.1)
                        side = "OVER"
                        odds = -110
                        over_prob = None
                        hit_prob = None
                        ev = 0.0
                        kf = 0.0
                        kelly_stake = 0.0
                        kelly_b_mult = _KELLY_B_MULT.get(conf, 0.7)

                    all_rows.append({
                        "player":            name,
                        "player_id":         pid,
                        "team":              team_abbrev,
                        "opp":               opp_abbrev,
                        "game_id":           game["game_id"],
                        "stat":              stat,
                        "side":              side,
                        "line":              line,
                        "pred":              round(float(mu_pp), 3),
                        "pred_raw":          round(float(mu), 3),
                        "q25":               round(float(qint["q25"]), 3) if qint else None,
                        "q75":               round(float(qint["q75"]), 3) if qint else None,
                        "edge_pp":           round(float(edge_pp), 4),
                        "over_prob":         round(float(over_prob), 4) if over_prob is not None else None,
                        "odds":              odds,
                        "kelly_pct":         round(kf * 100, 3),
                        "kelly_stake":       kelly_stake,
                        "kelly_b_mult":      kelly_b_mult,
                        "confidence":        conf,
                        "atlas_density":     atlas_density,
                        "gate_status":       gate_status,
                        "matchup_composite": round(float(composite_val), 4),
                        "bias_shift":        round(float(shift), 4),
                        "notes":             f"status={status}" if status else "",
                        # internal scoring
                        "_score":            0.0,
                    })

    # Stage 9: rank + filter
    n_players_universe = n_universe

    # Compute score
    for row in all_rows:
        row["_score"] = _score_row(row)

    # Apply filters + (player, stat) dedup
    filtered: List[Dict] = []
    drop_counts: Dict[str, int] = {}
    for row in all_rows:
        passes, reason = _passes_filters(row, min_edge, no_lines)
        if not passes:
            drop_counts[reason] = drop_counts.get(reason, 0) + 1
            continue
        key = (row["player_id"], row["stat"])
        if key in seen_player_stat:
            drop_counts["dup_player_stat"] = drop_counts.get("dup_player_stat", 0) + 1
            continue
        seen_player_stat.add(key)
        filtered.append(row)

    # Sort monotonically descending by score
    filtered.sort(key=lambda r: r["_score"], reverse=True)

    # Assert sort monotonicity
    scores = [r["_score"] for r in filtered]
    for i in range(1, len(scores)):
        assert scores[i] <= scores[i - 1] + 1e-9, f"Sort monotonicity violation at {i}"

    top_rows = filtered[:top_n]

    # Assign ranks
    for i, row in enumerate(top_rows, 1):
        row["rank"] = i
        del row["_score"]  # clean up internal field

    n_after_filter = len(filtered)
    coverage_ratio = n_after_filter / max(n_players_universe, 1)

    output = {
        "date": date_str,
        "generated_at": generated_at,
        "n_games": len(games),
        "n_players_universe": n_players_universe,
        "n_props_with_line": n_props_with_line,
        "n_after_filter": n_after_filter,
        "top_n_returned": len(top_rows),
        "coverage_ratio": round(coverage_ratio, 4),
        "min_edge_used": min_edge,
        "no_lines_mode": no_lines,
        "drop_counts": drop_counts,
        "rows": top_rows,
    }

    return output


def _empty_slate(date_str: str, generated_at: str, n_games: int) -> Dict:
    return {
        "date": date_str,
        "generated_at": generated_at,
        "n_games": n_games,
        "n_players_universe": 0,
        "n_props_with_line": 0,
        "n_after_filter": 0,
        "top_n_returned": 0,
        "coverage_ratio": 0.0,
        "min_edge_used": 0.0,
        "no_lines_mode": False,
        "drop_counts": {},
        "rows": [],
    }


# ── validation block ──────────────────────────────────────────────────────────

def run_validations(result: Dict, date_str: str) -> List[str]:
    """Return list of PASS/FAIL strings for each validation gate."""
    rows = result.get("rows", [])
    n_universe = result.get("n_players_universe", 0)
    n_after = result.get("n_after_filter", 0)
    coverage = result.get("coverage_ratio", 0.0)
    checks = []

    # V1: sort monotonicity (already asserted in build, check here too)
    scores = [_score_row(dict(r, _score=0)) for r in rows]
    mono = all(scores[i] <= scores[i-1] + 1e-9 for i in range(1, len(scores)))
    checks.append(f"  V1 sort_monotonicity: {'PASS' if mono else 'FAIL'}")

    # V2: ≥1 high confidence row with edge_pp ≥ 3.0 (sanity)
    high_edge = [r for r in rows if r.get("confidence") == "high" and
                 r.get("edge_pp", 0) >= 3.0]
    v2 = len(high_edge) >= 1
    # V2 is a soft check — warn, don't fail (depends on data availability)
    checks.append(f"  V2 high_conf_edge3pp: {'PASS' if v2 else 'WARN (0 rows -- likely no lines)'}")

    # V3: coverage ≥ 0.30
    v3 = coverage >= 0.30
    checks.append(f"  V3 coverage_ratio≥0.30: {'PASS' if v3 else 'FAIL'} ({coverage:.2%})")

    # V4 (dry-run 2025-02-28): top-10 hit-rate — can only compute if actuals are known
    # We skip this for the standard run; it's noted as uncomputable.
    checks.append("  V4 top10_hit_rate: SKIP (no historical actuals to compute at runtime)")

    return checks


# ── output serialization ──────────────────────────────────────────────────────

def _write_json(result: Dict, date_str: str, dry_run: bool) -> str:
    out_path = os.path.join(_OUT_DIR, f"daily_slate_{date_str}.json")
    if not dry_run:
        os.makedirs(_OUT_DIR, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  -> JSON: {out_path}")
    else:
        print(f"  -> [dry-run] JSON would be: {out_path}")
    return out_path


def _write_vault_md(result: Dict, date_str: str, dry_run: bool) -> str:
    rows = result.get("rows", [])
    out_path = os.path.join(_VAULT_DIR, f"{date_str}.md")
    top3_prose = ""
    if rows:
        top3 = rows[:3]
        parts = []
        for r in top3:
            line_str = f" (line={r['line']})" if r.get("line") else ""
            parts.append(
                f"{r['player']} {r['stat'].upper()} {r['side']}{line_str} "
                f"pred={r['pred']:.1f} conf={r['confidence']} edge_pp={r['edge_pp']:.2f}"
            )
        top3_prose = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(parts))

    # Build table
    header = ("| rank | player | team | opp | stat | side | line | pred | q25 | q75 | "
              "edge_pp | over_prob | odds | kelly_pct | confidence | atlas_density | "
              "gate_status | matchup_composite | bias_shift | notes |")
    sep    = "|------|--------|------|-----|------|------|------|------|-----|-----|"
    sep   += "---------|-----------|------|-----------|------------|-------------|"
    sep   += "------------|-------------------|------------|-------|"
    table_rows = []
    for r in rows:
        line_str   = f"{r['line']:.1f}"   if r.get("line") is not None else "--"
        over_str   = f"{r['over_prob']:.3f}" if r.get("over_prob") is not None else "--"
        q25_str    = f"{r['q25']:.1f}"    if r.get("q25") is not None else "--"
        q75_str    = f"{r['q75']:.1f}"    if r.get("q75") is not None else "--"
        table_rows.append(
            f"| {r.get('rank','')} | {r['player']} | {r['team']} | {r['opp']} | "
            f"{r['stat'].upper()} | {r['side']} | {line_str} | {r['pred']:.2f} | "
            f"{q25_str} | {q75_str} | {r['edge_pp']:.2f} | {over_str} | "
            f"{r['odds']:+d} | {r['kelly_pct']:.2f}% | {r['confidence']} | "
            f"{r['atlas_density']} | {r['gate_status']} | "
            f"{r['matchup_composite']:.3f} | {r['bias_shift']:.3f} | {r.get('notes','')} |"
        )

    lines = [
        f"# Daily Slate — {date_str}",
        "",
        "## Diagnostic Header",
        "",
        f"- generated_at: {result['generated_at']}",
        f"- n_games: {result['n_games']}",
        f"- n_players_universe: {result['n_players_universe']}",
        f"- n_props_with_line: {result['n_props_with_line']}",
        f"- n_after_filter: {result['n_after_filter']}",
        f"- top_n_returned: {result['top_n_returned']}",
        f"- coverage_ratio: {result['coverage_ratio']:.2%}",
        f"- no_lines_mode: {result['no_lines_mode']}",
        f"- drop_counts: {result.get('drop_counts', {})}",
        "",
        "## Top 3 Picks",
        "",
        top3_prose or "  (no rows after filter)",
        "",
        "## Ranked Table",
        "",
        header,
        sep,
    ] + table_rows + [
        "",
        "---",
        "",
        f"*Generated by INT-85 build_daily_slate.py on {date_str}.*",
    ]

    content = "\n".join(lines) + "\n"
    if not dry_run:
        os.makedirs(_VAULT_DIR, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  -> Vault MD: {out_path}")
    else:
        print(f"  -> [dry-run] Vault MD would be: {out_path}")
    return out_path


def _append_index(result: Dict, date_str: str, json_path: str, dry_run: bool) -> None:
    """Append one row to _Slate_Index.md (guard against duplicate date)."""
    rows = result.get("rows", [])
    top_edge = max((r["edge_pp"] for r in rows), default=0.0)
    top_pick = (f"{rows[0]['player']} {rows[0]['stat'].upper()} {rows[0]['side']}"
                if rows else "--")
    n_returned = result.get("top_n_returned", 0)

    new_line = (f"| {date_str} | {n_returned} | {top_edge:.2f} | {top_pick} | "
                f"{json_path} |")

    if dry_run:
        print(f"  -> [dry-run] Index append: {new_line}")
        return

    os.makedirs(os.path.dirname(_INDEX_PATH), exist_ok=True)

    # Guard: check if this date is already in the index
    existing = ""
    if os.path.exists(_INDEX_PATH):
        with open(_INDEX_PATH, encoding="utf-8") as f:
            existing = f.read()
    if date_str in existing:
        print(f"  -> Index: date {date_str} already present, skipping duplicate append.")
        return

    # Append header if file is new or empty
    with open(_INDEX_PATH, "a", encoding="utf-8") as f:
        if not existing.strip():
            f.write("# Slate Index\n\n")
            f.write("| date | n_returned | top_edge | top_pick | json_path |\n")
            f.write("|------|------------|----------|----------|-----------|\n")
        f.write(new_line + "\n")
    print(f"  -> Index appended: {_INDEX_PATH}")


def _write_int85_md(date_str: str, dry_run: bool) -> None:
    """Overwrite the canonical INT-85 doc (always current)."""
    content = (
        f"# INT-85: Daily Slate Ranking Generator\n\n"
        f"**Last run:** {date_str}\n"
        f"**Script:** `scripts/build_daily_slate.py`\n"
        f"**Output dir:** `data/intelligence/daily_slate_*.json`\n"
        f"**Vault dir:** `vault/Intelligence/Daily_Slates/`\n"
        f"**Index:** `vault/Intelligence/_Slate_Index.md`\n\n"
        f"## Pipeline\n\n"
        f"1. load_slate_games(date)\n"
        f"2. build_player_universe (drop OUT/DOUBTFUL/NWT)\n"
        f"3. predict_pergame per player (PROTECTED)\n"
        f"4. apply bias_shift (INT-69 per_player_calibration.parquet)\n"
        f"5. attach confidence tier (INT-77 confidence_ensemble.parquet + INT-16 per_player_confidence.parquet)\n"
        f"6. attach CV coverage gate (INT-53 cv_coverage_gates.parquet); warn -> conf -=1\n"
        f"7. attach matchup composite (INT-63 matchup_grid.parquet); mu'' = mu' * (1 + 0.10 * composite)\n"
        f"8. attach lines from data/props/props_<date>.json; over_p from Normal(mu'', sigma); EV; Kelly\n"
        f"9. rank by score = edge_pp * kelly_b_mult * conf_weight; filter; top-N\n\n"
        f"## Honest Limitations\n\n"
        f"- Props file coverage near-zero (only props_2025-02-28.json exists and is empty)\n"
        f"- --no-lines mode produces ranked predictions only (no EV or Kelly)\n"
        f"- XGB quantile models have 85-feature mismatch with current 129-feature set; "
        f"sigma uses Normal approximation from quantile_calibration.json\n"
        f"- Matchup composite is league_prior for ~68% of pairs (thin coverage)\n"
        f"- Confidence tiers: most rows are 'low' (thin coverage_class in confidence_ensemble)\n"
        f"- No historical CLV to validate top-10 beat closing\n\n"
        f"---\n\n"
        f"*Updated: {datetime.utcnow().isoformat(timespec='seconds')}Z*\n"
    )
    if not dry_run:
        os.makedirs(os.path.dirname(_INT85_PATH), exist_ok=True)
        with open(_INT85_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  -> INT-85 doc: {_INT85_PATH}")
    else:
        print(f"  -> [dry-run] INT-85 doc would be: {_INT85_PATH}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="INT-85 Daily Slate Ranking Generator")
    ap.add_argument("--date", default=None,
                    help="Slate date YYYY-MM-DD (default: today)")
    ap.add_argument("--top", type=int, default=20,
                    help="Top-N rows to return (default 20)")
    ap.add_argument("--min-edge", type=float, default=0.5,
                    help="Minimum edge_pp to include a bet (default 0.5)")
    ap.add_argument("--bankroll", type=float, default=1000.0,
                    help="Bankroll for Kelly sizing (default $1000)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute everything but do not write output files")
    ap.add_argument("--no-lines", action="store_true",
                    help="Skip props lookup; produce ranked predictions only (no EV/Kelly)")
    ap.add_argument("--season", default=None,
                    help="Season override (e.g. 2024-25)")
    ap.add_argument("--rest", type=float, default=2.0,
                    help="Days rest assumed for all players (default 2)")
    ap.add_argument("--matchup-window-days", type=int, default=45,
                    help="INT-96A FIX #3: restrict matchup_grid asof-lookup to this "
                         "many days before date (default 45)")
    ap.add_argument("--no-calibration", action="store_true",
                    help="INT-100: disable INT-69 per-player bias_shift_applied (kill switch). "
                         "Default OFF means calibration is ON.")
    args = ap.parse_args()

    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
            date_str = args.date
        except ValueError:
            print(f"  [fail] bad --date '{args.date}' — use YYYY-MM-DD")
            return 2
    else:
        date_str = _date.today().isoformat()

    result = build_slate(
        date_str=date_str,
        top_n=args.top,
        min_edge=args.min_edge,
        bankroll=args.bankroll,
        dry_run=args.dry_run,
        no_lines=args.no_lines,
        season=args.season,
        rest_days=args.rest,
        matchup_window_days=args.matchup_window_days,
        no_calibration=args.no_calibration,
    )

    # Print summary
    rows = result.get("rows", [])
    print(f"\n  Summary: {result['n_games']} games | "
          f"{result['n_players_universe']} universe | "
          f"{result['n_after_filter']} after filter | "
          f"{result['top_n_returned']} returned")
    print(f"  Drop counts: {result.get('drop_counts', {})}")

    if rows:
        print(f"\n  Top 3 picks:")
        for r in rows[:3]:
            line_str = f" line={r['line']:.1f}" if r.get("line") is not None else ""
            print(f"    #{r['rank']} {r['player']:<25} {r['stat'].upper():4s} "
                  f"{r['side']:5s}{line_str}  pred={r['pred']:.2f}  "
                  f"edge_pp={r['edge_pp']:.2f}  conf={r['confidence']}  "
                  f"density={r['atlas_density']}")

    # Validations
    print("\n  Validations:")
    checks = run_validations(result, date_str)
    for c in checks:
        print(c)

    # Write outputs
    json_path = _write_json(result, date_str, args.dry_run)
    _write_vault_md(result, date_str, args.dry_run)
    _append_index(result, date_str, json_path, args.dry_run)
    _write_int85_md(date_str, args.dry_run)

    print(f"\n  Done. {result['top_n_returned']} bets written for {date_str}.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
