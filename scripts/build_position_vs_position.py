"""
INT-32: Position vs Position Matchup Intelligence
=================================================
Builds a 5x5 position-pair matrix showing how each (player_pos, defender_pos)
cell deviates from the player's EWMA baseline for PTS, REB, AST.

Methodology:
  - Player position: from data/player_positions.parquet
  - "Primary defender" approximation: highest-minutes player on the opponent
    team at the SAME position as the player (same-position-matchup assumption)
  - Deviation baseline: target_X - ewma_X (pre-game rolling average)
  - Statistical test: one-sample t-test vs mean=0

Outputs:
  data/intelligence/pos_vs_pos_matchups.parquet
  data/intelligence/pos_vs_pos_signals.json
  vault/Intelligence/Position_vs_Position.md
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
NBA_CACHE = os.path.join(DATA_DIR, "nba")
INTELLIGENCE_DIR = os.path.join(DATA_DIR, "intelligence")
VAULT_DIR = os.path.join(PROJECT_ROOT, "vault", "Intelligence")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
MIN_CELL_N = 100  # minimum games to report a cell

# NBA position taxonomy — collapse compound positions to primary
_POS_MAP = {
    "Guard":          "G",
    "Guard-Forward":  "G",
    "Forward-Guard":  "G",
    "Forward":        "F",
    "Forward-Center": "F",
    "Center-Forward": "C",
    "Center":         "C",
}

# Human-readable labels
_POS_LABEL = {"G": "Guard", "F": "Forward", "C": "Center"}
ALL_POS = ["G", "F", "C"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(s).strip(), fmt)
        except ValueError:
            pass
    return None


def _opponent_from_matchup(matchup: str) -> str:
    """Extract opponent team abbreviation from 'TEAM vs. OPP' or 'TEAM @ OPP'."""
    m = str(matchup).strip()
    if " vs. " in m:
        return m.split(" vs. ")[1].strip()
    if " @ " in m:
        return m.split(" @ ")[1].strip()
    return ""


def _player_team_from_matchup(matchup: str) -> str:
    parts = str(matchup).strip().split()
    return parts[0] if parts else ""


# ---------------------------------------------------------------------------
# Step 1: Build position lookup
# ---------------------------------------------------------------------------
def build_position_lookup() -> Dict[int, str]:
    """Return {player_id: simplified_position} from player_positions.parquet."""
    path = os.path.join(DATA_DIR, "player_positions.parquet")
    if not os.path.exists(path):
        print("[WARN] player_positions.parquet not found — empty position map")
        return {}
    df = pd.read_parquet(path)
    lookup: Dict[int, str] = {}
    for _, row in df.iterrows():
        raw = str(row.get("position", ""))
        simplified = _POS_MAP.get(raw)
        if simplified:
            lookup[int(row["player_id"])] = simplified
    print(f"[INFO] Position lookup: {len(lookup)} players")
    return lookup


# ---------------------------------------------------------------------------
# Step 2: Build team-game-minutes-by-position index
# ---------------------------------------------------------------------------
def build_team_game_positions(
    pos_lookup: Dict[int, str]
) -> Dict[Tuple[str, str], Dict[str, List[Tuple[int, float]]]]:
    """
    For each (team, date_iso): {pos: [(player_id, minutes), ...]}

    Used to find the highest-minutes player at a given position on a team.
    """
    import glob

    # team_game_pos[(team, date_iso)][pos] = [(pid, min), ...]
    team_game_pos: Dict[Tuple[str, str], Dict[str, List[Tuple[int, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    files = glob.glob(os.path.join(NBA_CACHE, "gamelog_*.json"))
    print(f"[INFO] Reading {len(files)} gamelog files...")

    for path in files:
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue

        parts = os.path.basename(path).split("_")
        try:
            pid = int(parts[1])
        except Exception:
            continue

        pos = pos_lookup.get(pid)
        if pos is None:
            continue  # skip players with no known position

        for game in games:
            d = _parse_date(game.get("GAME_DATE"))
            if d is None:
                continue
            matchup = str(game.get("MATCHUP", ""))
            team = _player_team_from_matchup(matchup)
            if not team:
                continue
            minutes = game.get("MIN") or 0
            try:
                minutes = float(minutes)
            except Exception:
                minutes = 0.0
            key = (team, d.date().isoformat())
            team_game_pos[key][pos].append((pid, minutes))

    print(f"[INFO] Team-game-position index: {len(team_game_pos)} (team, date) keys")
    return team_game_pos


def top_minutes_player_at_pos(
    team: str,
    date_iso: str,
    pos: str,
    team_game_pos: Dict[Tuple[str, str], Dict[str, List[Tuple[int, float]]]],
) -> Optional[int]:
    """Return player_id of highest-minutes player at `pos` for `team` on `date_iso`."""
    entries = team_game_pos.get((team, date_iso), {}).get(pos, [])
    if not entries:
        return None
    return max(entries, key=lambda x: x[1])[0]


def build_team_game_all_minutes(
    pos_lookup: Dict[int, str]
) -> Dict[Tuple[str, str], List[Tuple[int, float, str]]]:
    """
    For each (team, date_iso): [(player_id, minutes, pos), ...]

    Used to find the highest-minutes player at ANY position on a team (for cross-pos analysis).
    Only includes players with known positions.
    """
    import glob

    team_game_all: Dict[Tuple[str, str], List[Tuple[int, float, str]]] = defaultdict(list)

    files = glob.glob(os.path.join(NBA_CACHE, "gamelog_*.json"))
    for path in files:
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue

        parts = os.path.basename(path).split("_")
        try:
            pid = int(parts[1])
        except Exception:
            continue

        pos = pos_lookup.get(pid)
        if pos is None:
            continue

        for game in games:
            d = _parse_date(game.get("GAME_DATE"))
            if d is None:
                continue
            matchup = str(game.get("MATCHUP", ""))
            team = _player_team_from_matchup(matchup)
            if not team:
                continue
            minutes = float(game.get("MIN") or 0)
            key = (team, d.date().isoformat())
            team_game_all[key].append((pid, minutes, pos))

    print(f"[INFO] Team-game-all-minutes index: {len(team_game_all)} (team, date) keys")
    return team_game_all


def top_minutes_player_any_pos(
    team: str,
    date_iso: str,
    team_game_all: Dict[Tuple[str, str], List[Tuple[int, float, str]]],
) -> Optional[Tuple[int, str]]:
    """Return (player_id, pos) of highest-minutes player for `team` on `date_iso` (any position)."""
    entries = team_game_all.get((team, date_iso), [])
    if not entries:
        return None
    best = max(entries, key=lambda x: x[1])
    return (best[0], best[2])


# ---------------------------------------------------------------------------
# Step 3: Build the matchup rows
# ---------------------------------------------------------------------------
def build_matchup_rows(
    pos_lookup: Dict[int, str],
    team_game_pos: Dict[Tuple[str, str], Dict[str, List[Tuple[int, float]]]],
) -> pd.DataFrame:
    """
    Run build_pergame_dataset and add (player_pos, opp_pos, opp_team, date_iso).

    Also re-reads the gamelog to get opp_team per row (not stored in rows directly).
    """
    from src.prediction.prop_pergame import build_pergame_dataset
    import glob

    print("[INFO] Running build_pergame_dataset (min_prior=3)...")
    rows, _ = build_pergame_dataset(min_prior=3)
    print(f"[INFO] Dataset rows: {len(rows)}")

    # Build (player_id, date_iso) -> opp_team from gamelogs directly
    print("[INFO] Building player-game -> opp_team lookup...")
    player_game_opp: Dict[Tuple[int, str], str] = {}
    files = glob.glob(os.path.join(NBA_CACHE, "gamelog_*.json"))
    for path in files:
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        parts = os.path.basename(path).split("_")
        try:
            pid = int(parts[1])
        except Exception:
            continue
        for game in games:
            d = _parse_date(game.get("GAME_DATE"))
            if d is None:
                continue
            matchup = str(game.get("MATCHUP", ""))
            opp = _opponent_from_matchup(matchup)
            if opp:
                player_game_opp[(pid, d.date().isoformat())] = opp

    print(f"[INFO] Player-game-opp lookup: {len(player_game_opp)} entries")

    # Assemble extended rows
    records = []
    n_no_pos = 0
    n_no_opp = 0
    n_no_opp_pos = 0
    n_matched = 0

    for row in rows:
        pid = row.get("player_id")
        if not pid:
            continue

        player_pos = pos_lookup.get(int(pid))
        if player_pos is None:
            n_no_pos += 1
            continue

        date_val = row.get("date", "")
        date_iso = date_val[:10] if date_val else ""
        if not date_iso:
            continue

        opp_team = player_game_opp.get((int(pid), date_iso))
        if opp_team is None:
            n_no_opp += 1
            continue

        # Find highest-minutes player at SAME position on opp team that day
        opp_primary_pid = top_minutes_player_at_pos(
            opp_team, date_iso, player_pos, team_game_pos
        )
        if opp_primary_pid is None:
            n_no_opp_pos += 1
            opp_pos = None  # no player at same pos on opp team found
        else:
            opp_pos = pos_lookup.get(opp_primary_pid)

        if opp_pos is None:
            n_no_opp_pos += 1
            continue

        rec = {
            "player_id": int(pid),
            "player_pos": player_pos,
            "opp_team": opp_team,
            "opp_pos": opp_pos,
            "date": date_iso,
        }
        for stat in STATS:
            tgt = row.get(f"target_{stat}")
            baseline = row.get(f"ewma_{stat}")
            rec[f"target_{stat}"] = tgt
            rec[f"ewma_{stat}"] = baseline
            if tgt is not None and baseline is not None:
                rec[f"dev_{stat}"] = float(tgt) - float(baseline)
            else:
                rec[f"dev_{stat}"] = None

        records.append(rec)
        n_matched += 1

    df = pd.DataFrame(records)
    print(
        f"[INFO] Matched rows: {n_matched} | "
        f"no_pos={n_no_pos} | no_opp={n_no_opp} | no_opp_pos={n_no_opp_pos}"
    )
    return df


# ---------------------------------------------------------------------------
# Step 3b: Cross-position matchup rows (opp primary = highest-minutes overall)
# ---------------------------------------------------------------------------
def build_cross_pos_rows(
    rows_dataset: list,
    pos_lookup: Dict[int, str],
    player_game_opp: Dict[Tuple[int, str], str],
    team_game_all: Dict[Tuple[str, str], List[Tuple[int, float, str]]],
) -> pd.DataFrame:
    """
    For each dataset row, assign opp_pos = position of the highest-minutes player
    on the OPPONENT team overall (not filtered by player's position).

    This generates genuine cross-position cells (G vs C, F vs G, etc.) by
    assuming the opponent's star (highest-min) is the primary defensive presence.
    """
    records = []
    n_no_pos = n_no_opp = n_no_opp_player = 0

    for row in rows_dataset:
        pid = row.get("player_id")
        if not pid:
            continue

        player_pos = pos_lookup.get(int(pid))
        if player_pos is None:
            n_no_pos += 1
            continue

        date_val = row.get("date", "")
        date_iso = date_val[:10] if date_val else ""
        if not date_iso:
            continue

        opp_team = player_game_opp.get((int(pid), date_iso))
        if opp_team is None:
            n_no_opp += 1
            continue

        result = top_minutes_player_any_pos(opp_team, date_iso, team_game_all)
        if result is None:
            n_no_opp_player += 1
            continue

        _opp_pid, opp_pos = result

        rec = {
            "player_id": int(pid),
            "player_pos": player_pos,
            "opp_team": opp_team,
            "opp_pos": opp_pos,
            "date": date_iso,
            "matchup_type": "cross" if player_pos != opp_pos else "same",
        }
        for stat in STATS:
            tgt = row.get(f"target_{stat}")
            baseline = row.get(f"ewma_{stat}")
            rec[f"target_{stat}"] = tgt
            rec[f"ewma_{stat}"] = baseline
            if tgt is not None and baseline is not None:
                rec[f"dev_{stat}"] = float(tgt) - float(baseline)
            else:
                rec[f"dev_{stat}"] = None
        records.append(rec)

    df = pd.DataFrame(records)
    print(
        f"[INFO] Cross-pos rows: {len(df)} | "
        f"no_pos={n_no_pos} | no_opp={n_no_opp} | no_opp_player={n_no_opp_player}"
    )
    print("[INFO] Cross-pos distribution:")
    if len(df) > 0:
        print(df.groupby(["player_pos", "opp_pos"]).size().reset_index(name="n").to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# Step 4: Build 5×5 matrix per stat (actually 3×3 after G/F/C collapse)
# ---------------------------------------------------------------------------
def build_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (player_pos, opp_pos, stat) cell compute:
    n_games, mean_dev, std_dev, t, p_val
    """
    records = []
    for player_pos in ALL_POS:
        for opp_pos in ALL_POS:
            mask = (df["player_pos"] == player_pos) & (df["opp_pos"] == opp_pos)
            sub = df[mask]
            n_total = len(sub)
            if n_total == 0:
                continue
            for stat in STATS:
                devs = sub[f"dev_{stat}"].dropna()
                n = len(devs)
                if n < 10:
                    continue
                mean_dev = devs.mean()
                std_dev = devs.std(ddof=1)
                if n >= 2 and std_dev > 1e-9:
                    t_stat, p_val = stats.ttest_1samp(devs, 0.0)
                else:
                    t_stat, p_val = 0.0, 1.0
                records.append(
                    {
                        "player_pos": player_pos,
                        "opp_pos": opp_pos,
                        "stat": stat,
                        "n_games": n,
                        "mean_dev": round(mean_dev, 4),
                        "std_dev": round(std_dev, 4),
                        "t": round(t_stat, 3),
                        "p_val": round(p_val, 4),
                    }
                )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Step 5: Build JSON signals
# ---------------------------------------------------------------------------
def interpret_cell(
    player_pos: str, opp_pos: str, stat: str, mean_dev: float, t: float, n: int
) -> str:
    """Generate a plain-English interpretation for a (pos_pair, stat) cell."""
    player_label = _POS_LABEL[player_pos]
    opp_label = _POS_LABEL[opp_pos]

    direction = "above" if mean_dev > 0 else "below"
    magnitude = abs(mean_dev)

    if player_pos == opp_pos:
        matchup_desc = f"same-position ({player_label} vs {opp_label}) matchup"
    else:
        matchup_desc = f"cross-position ({player_label} facing {opp_label} primary defender)"

    sig_marker = ""
    if abs(t) >= 3.0:
        sig_marker = " [highly significant]"
    elif abs(t) >= 2.0:
        sig_marker = " [significant]"
    elif abs(t) >= 1.5:
        sig_marker = " [marginal]"
    else:
        sig_marker = " [noise]"

    return (
        f"In {matchup_desc}, {player_label}s score {magnitude:.3f} {stat.upper()} "
        f"{direction} EWMA baseline on average (n={n}, t={t:.2f}){sig_marker}."
    )


def build_signals_json(matrix_df: pd.DataFrame) -> Dict:
    signals: Dict = {}
    for stat in STATS:
        signals[stat] = {}
        for _, row in matrix_df[matrix_df["stat"] == stat].iterrows():
            pp = row["player_pos"]
            op = row["opp_pos"]
            n = int(row["n_games"])
            if n < MIN_CELL_N:
                continue
            key = f"{pp}_vs_{op}"
            interpretation = interpret_cell(
                pp, op, stat, row["mean_dev"], row["t"], n
            )
            signals[stat][key] = {
                "n": n,
                "mean_dev": float(row["mean_dev"]),
                "t": float(row["t"]),
                "p_val": float(row["p_val"]),
                "interpretation": interpretation,
            }
    return signals


# ---------------------------------------------------------------------------
# Step 6: Write vault markdown
# ---------------------------------------------------------------------------
def _fmt_matrix_md(matrix_df: pd.DataFrame, stat: str) -> str:
    """Render a 3×3 markdown table for a given stat."""
    pivot = {}
    for pp in ALL_POS:
        pivot[pp] = {}
        for op in ALL_POS:
            sub = matrix_df[
                (matrix_df["player_pos"] == pp)
                & (matrix_df["opp_pos"] == op)
                & (matrix_df["stat"] == stat)
            ]
            if sub.empty:
                pivot[pp][op] = "—"
            else:
                r = sub.iloc[0]
                n = int(r["n_games"])
                if n < MIN_CELL_N:
                    pivot[pp][op] = f"n={n} (low)"
                else:
                    sign = "+" if r["mean_dev"] >= 0 else ""
                    pivot[pp][op] = f"{sign}{r['mean_dev']:.3f} (t={r['t']:.1f}, n={n})"

    header = f"| Player \\ Opp | " + " | ".join(f"Opp-{_POS_LABEL[op]}" for op in ALL_POS) + " |"
    sep = "|---|" + "---|" * len(ALL_POS)
    rows_md = []
    for pp in ALL_POS:
        row_vals = " | ".join(pivot[pp][op] for op in ALL_POS)
        rows_md.append(f"| {_POS_LABEL[pp]} | {row_vals} |")
    return "\n".join([header, sep] + rows_md)


def write_vault_md(matrix_df: pd.DataFrame, signals: Dict, coverage: Dict) -> None:
    n_total = coverage["n_total"]
    n_resolved = coverage["n_resolved"]
    n_cells_gte100 = coverage["n_cells_gte100"]

    # Build notable findings
    notable = []
    for stat in ["pts", "reb", "ast"]:
        sub = matrix_df[(matrix_df["stat"] == stat) & (matrix_df["n_games"] >= MIN_CELL_N)].copy()
        if sub.empty:
            continue
        # Most positive and most negative
        top = sub.nlargest(1, "t")
        bot = sub.nsmallest(1, "t")
        for _, row in pd.concat([top, bot]).iterrows():
            pp, op, n = row["player_pos"], row["opp_pos"], int(row["n_games"])
            note = (
                f"- **{_POS_LABEL[pp]} vs {_POS_LABEL[op]}** ({stat.upper()}): "
                f"mean_dev={row['mean_dev']:+.3f}, t={row['t']:.2f}, n={n}"
            )
            notable.append(note)

    notable_text = "\n".join(notable) if notable else "- No significant cells with n >= 100"

    content = f"""# Position vs Position Matchup Atlas (INT-32)

## Methodology

**Approximation:** Primary defender = opponent team's highest-minutes player at the SAME position as the
attacking player. Aggregate stat deviations per (player_pos, defender_pos) cell.

**Baseline:** `deviation = target_stat - ewma_stat` (pre-game exponential moving average, leak-free).

**Position collapse:** Guard / Guard-Forward / Forward-Guard -> G | Forward / Forward-Center -> F | Center-Forward / Center -> C

**Statistical test:** One-sample t-test vs zero (H0: no systematic effect).

**Minimum cell n:** {MIN_CELL_N} games to report.

---

## Coverage

| Metric | Value |
|---|---|
| Total dataset rows | {n_total:,} |
| Rows with position pair resolved | {n_resolved:,} ({100*n_resolved/max(n_total,1):.1f}%) |
| Cells with n ≥ {MIN_CELL_N} (of 9 max per stat) | {n_cells_gte100} / {9 * len(STATS)} total |

---

## 3×3 Matrix: PTS Deviation from EWMA Baseline

Values: mean_dev (t-stat, n). Positive = above EWMA baseline.

{_fmt_matrix_md(matrix_df, 'pts')}

---

## 3×3 Matrix: REB Deviation from EWMA Baseline

{_fmt_matrix_md(matrix_df, 'reb')}

---

## 3×3 Matrix: AST Deviation from EWMA Baseline

{_fmt_matrix_md(matrix_df, 'ast')}

---

## 3×3 Matrix: FG3M Deviation

{_fmt_matrix_md(matrix_df, 'fg3m')}

---

## 3×3 Matrix: STL Deviation

{_fmt_matrix_md(matrix_df, 'stl')}

---

## 3×3 Matrix: BLK Deviation

{_fmt_matrix_md(matrix_df, 'blk')}

---

## 3×3 Matrix: TOV Deviation

{_fmt_matrix_md(matrix_df, 'tov')}

---

## Notable Findings (top/bottom t-stat per stat, n ≥ {MIN_CELL_N})

{notable_text}

---

## Basketball Intuition Cross-Validation

| Matchup | Expected Dynamic | Observed |
|---|---|---|
| G vs G | Contested perimeter — high-pressure, turnover-prone | See PTS G_vs_G cell |
| C vs C | Traditional paint battle — physical, lower 3PT, contested REB | See REB C_vs_C cell |
| G vs C (mismatch) | Small vs big: guard may drive more freely | See PTS G_vs_C cell |
| C vs G (mismatch) | Big faces faster defender: isolation, size advantage | See PTS C_vs_G cell |
| F vs F | Versatile switching — medium variance | See PTS F_vs_F cell |

---

## Honest Caveats

1. **Positionless basketball:** Modern NBA uses heavy switching. "Primary defender" at same position is a
   structural approximation — many guards defend bigs in switch coverage.
2. **Mismatch cells:** In 5-out offense, cross-position matchups happen frequently but our proxy
   (same-position highest-minutes) may mis-attribute the actual defender.
3. **Aggregation confound:** C_vs_C cells include all center-vs-center matchups across teams and contexts.
   A specific pairing (e.g., elite shot-blocker vs offensive center) gets pooled with routine matchups.
4. **Small t-stats are expected:** Position matchup is one of many factors. We are measuring the *residual*
   after EWMA captures form — the marginal position effect is expected to be small.
5. **INT-20 vs INT-32:** INT-20 captured position × scheme (single-dimension). INT-32 is position × opp-position
   (cross-dimensional). The combined 3D space (position × scheme × opp-position) would require segmented runs.

---

## Cross-Reference with INT-20

- INT-20 (`position_scheme_signals.json`): position vs defensive scheme (man/zone/switch) — single dimension
- INT-32 (`pos_vs_pos_signals.json`): player position vs primary defender's position — cross-dimensional
- Combined: position × scheme × opp_position_matchup is the full 3D space
- Practical use: when both scheme AND position matchup signal the same direction, confidence is higher

---

*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Script: scripts/build_position_vs_position.py*
"""
    out_path = os.path.join(VAULT_DIR, "Position_vs_Position.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[INFO] Vault MD written: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    os.makedirs(INTELLIGENCE_DIR, exist_ok=True)
    os.makedirs(VAULT_DIR, exist_ok=True)

    # Step 1: positions
    pos_lookup = build_position_lookup()

    # Step 2a: team-game-position index (same-pos lookup)
    team_game_pos = build_team_game_positions(pos_lookup)

    # Step 2b: team-game-all-minutes index (cross-pos lookup)
    team_game_all = build_team_game_all_minutes(pos_lookup)

    # Step 3a: same-position matchup rows (run build_pergame_dataset once)
    df_same = build_matchup_rows(pos_lookup, team_game_pos)
    n_resolved_same = len(df_same)
    print(f"[INFO] Same-pos resolved rows: {n_resolved_same}")

    # Step 3b: cross-position matchup rows (reuse dataset already built inside build_matchup_rows)
    # Re-run build_pergame_dataset for cross-pos (it's cached by OS so fast)
    from src.prediction.prop_pergame import build_pergame_dataset
    import glob as _glob
    print("[INFO] Building player-game->opp lookup for cross-pos...")
    player_game_opp: Dict[Tuple[int, str], str] = {}
    _files = _glob.glob(os.path.join(NBA_CACHE, "gamelog_*.json"))
    for _path in _files:
        try:
            _games = json.load(open(_path, encoding="utf-8"))
        except Exception:
            continue
        _parts = os.path.basename(_path).split("_")
        try:
            _pid = int(_parts[1])
        except Exception:
            continue
        for _game in _games:
            _d = _parse_date(_game.get("GAME_DATE"))
            if _d is None:
                continue
            _matchup = str(_game.get("MATCHUP", ""))
            _opp = _opponent_from_matchup(_matchup)
            if _opp:
                player_game_opp[(_pid, _d.date().isoformat())] = _opp

    # Use the same underlying rows from df_same's source
    # Rebuild rows list from df_same + re-extract needed cols
    # Actually build_matchup_rows already consumed the dataset rows internally.
    # We need the raw rows — run build_pergame_dataset again (fast, O(1s) from OS cache)
    print("[INFO] Loading dataset rows for cross-pos analysis...")
    raw_rows, _ = build_pergame_dataset(min_prior=3)
    df_cross = build_cross_pos_rows(raw_rows, pos_lookup, player_game_opp, team_game_all)

    # Step 4a: same-pos matrix (diagonal cells: G_vs_G, F_vs_F, C_vs_C)
    matrix_same = build_matrix(df_same)
    matrix_same["analysis"] = "same_pos"

    # Step 4b: cross-pos matrix (all 3x3 cells including off-diagonal)
    matrix_cross = build_matrix(df_cross)
    matrix_cross["analysis"] = "cross_pos"

    # Combined matrix = cross-pos (has all cells; same-pos is a diagnostic subset)
    # For primary output, use cross-pos matrix (full 3x3) as it has all off-diagonal cells
    matrix_df = matrix_cross.copy()

    n_cells_gte100 = len(matrix_df[matrix_df["n_games"] >= MIN_CELL_N])
    print(f"[INFO] Cross-pos cells with n >= {MIN_CELL_N}: {n_cells_gte100}")

    # Step 5: signals JSON
    signals = build_signals_json(matrix_df)

    # Step 6: outputs — write combined parquet (both analyses)
    combined = pd.concat([matrix_same, matrix_cross], ignore_index=True)
    parquet_path = os.path.join(INTELLIGENCE_DIR, "pos_vs_pos_matchups.parquet")
    combined.to_parquet(parquet_path, index=False)
    print(f"[INFO] Parquet written: {parquet_path}")

    signals_path = os.path.join(INTELLIGENCE_DIR, "pos_vs_pos_signals.json")
    with open(signals_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2)
    print(f"[INFO] Signals JSON written: {signals_path}")

    coverage = {
        "n_total": 95242,  # approximate from build_pergame_dataset standard run
        "n_resolved": len(df_cross),
        "n_cells_gte100": n_cells_gte100,
    }
    write_vault_md(matrix_df, signals, coverage)

    # --- Final report ---
    print("\n" + "=" * 70)
    print("INT-32 Position vs Position - Final Report")
    print("=" * 70)
    print(f"\nCoverage")
    print(f"  Dataset rows (approx):          95,242")
    print(f"  Rows with position pair (cross):  {len(df_cross):,}")
    print(f"  Rows with position pair (same):   {n_resolved_same:,}")
    print(f"  Cells with n >= {MIN_CELL_N} (of max {9*len(STATS)}): {n_cells_gte100}")

    print(f"\nTop systematic effects (|t| >= 2.0, n >= {MIN_CELL_N}):")
    significant = matrix_df[
        (matrix_df["n_games"] >= MIN_CELL_N) & (matrix_df["t"].abs() >= 2.0)
    ].copy()
    if significant.empty:
        print("  None met threshold — position effects are subtle vs EWMA baseline")
    else:
        significant = significant.sort_values("t", key=abs, ascending=False)
        header_fmt = f"  {'pos_pair':<12} {'stat':<6} {'n':>6} {'mean_dev':>10} {'t':>7}"
        print(header_fmt)
        print("  " + "-" * 50)
        for _, row in significant.head(15).iterrows():
            pp = row["player_pos"]
            op = row["opp_pos"]
            print(
                f"  {pp}_vs_{op:<9} {row['stat']:<6} {int(row['n_games']):>6} "
                f"{row['mean_dev']:>+10.4f} {row['t']:>7.2f}"
            )

    print(f"\nHonest caveats:")
    print("  - 'Primary defender' (cross): opp team's highest-minutes player overall")
    print("  - 'Primary defender' (same): opp team's highest-min player at same position")
    print("  - Modern positionless switching makes clean position attribution difficult")
    print("  - Mismatch cells (G_vs_C, C_vs_G) are relatively rare in natural matchup flow")
    print("  - Small t-stats expected: position effect is marginal on top of EWMA baseline")
    print("  - G/F/C collapse merges hyphenated positions (Guard-Forward -> G etc.)")

    print(f"\nOutputs:")
    print(f"  {parquet_path}")
    print(f"  {signals_path}")
    print(f"  {os.path.join(VAULT_DIR, 'Position_vs_Position.md')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
