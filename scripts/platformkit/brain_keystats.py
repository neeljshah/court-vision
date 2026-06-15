"""brain_keystats.py — per-sport "which box stats separate WINS from LOSSES".

Mines the gitignored ESPN team box parquets (built by the per-sport
``ingest_espn_box`` modules) into DESCRIPTIVE, person-free knowledge: for each
team box stat, the standardized mean difference (Cohen's d, mean-in-wins minus
mean-in-losses over a pooled SD) ranked by |separation|. Realized post-game data,
NOT a leak-free signal and NOT a bet — markets are efficient; no edge claimed.

Reshape: each game contributes TWO team-game rows (home, away); win/loss is read
from the score columns; stats are the ``home_<stat>``/``away_<stat>`` pairs.

Writes ``vault/_Organized/<SPORT>/_KeyStats.md`` — a dense ranked table resolving
[[wikilinks]] to ``[[_WhatWins]]`` / ``[[_Index]]``. Team ABBRs are NOT written as
nodes; only aggregate stats. Idempotent. Heavy pandas is LAZY.

CLI: ``python -m scripts.platformkit.brain_keystats [<organized_root>] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = ("> **Descriptive intelligence; markets efficient; calibration is not edge; "
           "no edge claimed.** Realized post-game box stats over WINS versus LOSSES — "
           "AGGREGATE knowledge of what separates outcomes, NOT a leak-free signal and "
           "NOT a bet. Must be joined as-of before any model may use it.")

# Per-sport box parquet (gitignored; may be absent/sparse -> skipped honestly) + a
# human label for the magnitude/unit. Stat columns are discovered from the data.
_SPORTS: Dict[str, Dict] = {
    "MLB":    {"parquet": "data/domains/mlb/espn_boxscores.parquet",
               "stat_label": "box stat (per team-game)"},
    "NBA":    {"parquet": "data/domains/basketball_nba/espn_boxscores.parquet",
               "stat_label": "box stat (per team-game)"},
    "Soccer": {"parquet": "data/domains/soccer/espn_matchstats.parquet",
               "stat_label": "match stat (per team-game)"},
}

# Non-stat identity columns never treated as a candidate box stat.
_ID_COLS = frozenset({
    "event_id", "date", "league", "status", "venue", "attendance",
    "abbr", "home_abbr", "away_abbr", "home_score", "away_score",
    "score", "opp_score", "won", "side", "name",
})
_MAX_RANKED = 30          # cap the table at the top |separation| stats
_MAX_TAKEAWAYS = 8        # one-line takeaway per top stat
_SMALL_N = 60             # below this many team-games -> "indicative only" caveat


def _slug(label: str) -> str:
    return str(label).lower().replace(" ", "_")


def _stat_columns(cols) -> List[str]:
    """Box stat suffixes present as BOTH home_<stat> and away_<stat> pairs."""
    home = {c[len("home_"):] for c in cols if str(c).startswith("home_")}
    away = {c[len("away_"):] for c in cols if str(c).startswith("away_")}
    stats = sorted((home & away) - _ID_COLS - {"score", "abbr"})
    return [s for s in stats if f"home_{s}" not in _ID_COLS]


def _to_team_games(df, stats: List[str]):
    """Explode one game-per-row frame into two team-game rows with won + stats.

    Each game contributes a home row and an away row; ``won`` is 1/0 from the
    score columns (ties/equal scores dropped — they carry no win/loss signal).
    Returns a long DataFrame (cols: won + each stat). PURE-ish (lazy pandas).
    """
    import pandas as pd  # noqa: PLC0415
    if "home_score" not in df.columns or "away_score" not in df.columns:
        return None
    hs = pd.to_numeric(df["home_score"], errors="coerce")
    aws = pd.to_numeric(df["away_score"], errors="coerce")
    frames = []
    for side, opp in (("home", "away"), ("away", "home")):
        sub = {"won": (hs > aws).astype("float") if side == "home"
               else (aws > hs).astype("float")}
        for s in stats:
            col = f"{side}_{s}"
            sub[s] = pd.to_numeric(df[col], errors="coerce") if col in df.columns else None
        frames.append(pd.DataFrame(sub))
    long = pd.concat(frames, ignore_index=True)
    # drop ties (equal scores -> neither a win nor a loss) and rows with no result
    decided = (hs != aws) & hs.notna() & aws.notna()
    keep = pd.concat([decided, decided], ignore_index=True)
    return long.loc[keep].reset_index(drop=True)


def _separations(long, stats: List[str]) -> List[Dict]:
    """Standardized mean diff (Cohen's d) per stat: (mean_win-mean_loss)/pooled_sd.

    Ranked by |d|. NaNs dropped per-stat; a stat with <2 wins or <2 losses, or a
    zero pooled SD, is skipped (no separation is computable). DESCRIPTIVE only.
    """
    wins = long[long["won"] == 1.0]
    losses = long[long["won"] == 0.0]
    rows: List[Dict] = []
    for s in stats:
        w = wins[s].dropna()
        l = losses[s].dropna()
        if len(w) < 2 or len(l) < 2:
            continue
        mw, ml = float(w.mean()), float(l.mean())
        vw, vl = float(w.var(ddof=1)), float(l.var(ddof=1))
        nw, nl = len(w), len(l)
        pooled = (((nw - 1) * vw + (nl - 1) * vl) / max(nw + nl - 2, 1)) ** 0.5
        if pooled <= 0:
            continue
        d = (mw - ml) / pooled
        rows.append({"stat": s, "mean_win": round(mw, 3), "mean_loss": round(ml, 3),
                     "separation": round(d, 3), "abs": abs(d), "n_win": nw, "n_loss": nl})
    rows.sort(key=lambda r: r["abs"], reverse=True)
    return rows


def _takeaway(r: Dict) -> str:
    """Person-free one-line descriptive takeaway for a ranked stat."""
    direction = "higher in wins" if r["separation"] >= 0 else "lower in wins"
    return (f"`{r['stat']}` is {direction} "
            f"(win {r['mean_win']:g} vs loss {r['mean_loss']:g}, "
            f"d={r['separation']:+g}) — descriptive realized separation, not a signal.")


def _render(sport: str, rows: List[Dict], n_games: int, n_team_games: int) -> str:
    cfg = _SPORTS[sport]
    small = n_team_games < _SMALL_N
    n_note = (f"**n={n_games} games ({n_team_games} team-games)** — sparse; indicative only."
              if small else f"**n={n_games} games ({n_team_games} team-games).**")
    lines = [
        f"---\ntags: [organized, {sport.lower()}, intelligence, key-stats, person-free]\n---",
        f"# {sport} — Key Stats: what separates WINS from LOSSES\n", _BANNER + "\n",
        f"{n_note} Each box stat ranked by the **standardized mean difference** "
        f"(Cohen's d = (mean in wins − mean in losses) / pooled SD). Larger |d| means the "
        f"stat more cleanly separates winning from losing team-games. DESCRIPTIVE only.\n",
        f"| # | {cfg['stat_label']} | mean(win) | mean(loss) | separation (d) |",
        "|---|------|----------:|-----------:|---------------:|",
    ]
    ranked = rows[:_MAX_RANKED]
    for i, r in enumerate(ranked, 1):
        lines.append(f"| {i} | `{r['stat']}` | {r['mean_win']:g} | {r['mean_loss']:g} "
                     f"| {r['separation']:+g} |")
    lines += ["", "## Top separators (person-free takeaways)"]
    for r in ranked[:_MAX_TAKEAWAYS]:
        lines.append(f"- {_takeaway(r)}")
    lines += [
        "", "## Reading this honestly",
        "- **Descriptive, not predictive.** These are REALIZED team-games; the realized box "
        "stat must NOT be used as a model feature — only its leak-free as-of companion may.",
        "- **Separation ≠ causation ≠ edge.** A large |d| describes the sample; markets are "
        "efficient and no edge is claimed.",
    ]
    if small:
        lines.append("- **Small sample.** Magnitudes are indicative only; ranks are unstable.")
    lines += ["", "## See also",
              f"- [[_WhatWins|{sport} What Wins & Why]]",
              f"- [[_Index|{sport} Index]]"]
    return "\n".join(lines) + "\n"


def _build_one(sport: str, df, write: bool, root: Path) -> Dict:
    """Aggregate one sport's box parquet into a ranked-separation report (+optional write)."""
    cols = list(getattr(df, "columns", []))
    if "home_score" not in cols or "away_score" not in cols:
        return {"skipped": "no score columns"}
    stats = _stat_columns(cols)
    if not stats:
        return {"skipped": "no paired box-stat columns"}
    long = _to_team_games(df, stats)
    if long is None or len(long) == 0:
        return {"skipped": "no decided team-games"}
    rows = _separations(long, stats)
    if not rows:
        return {"skipped": "no computable separation"}
    n_games = int(len(df))
    n_team_games = int(len(long))
    md = _render(sport, rows, n_games, n_team_games)
    if write:
        sdir = root / sport
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "_KeyStats.md").write_text(md, encoding="utf-8")
    return {"n_games": n_games, "n_team_games": n_team_games, "n_stats": len(rows),
            "top": [r["stat"] for r in rows[:_MAX_TAKEAWAYS]],
            "small_n": n_team_games < _SMALL_N, "rows": rows, "keystats_md": md}


def build_keystats(organized_root: Optional[Path] = None,
                   data_root: Optional[Path] = None,
                   write: bool = True,
                   injected: Optional[Dict] = None) -> Dict:
    """Build per-sport KEY-STATS (win-vs-loss separation) notes from box parquets.

    ``injected`` accepts ``{sport: DataFrame}`` for hermetic tests (bypasses I/O).
    Sports with a missing/sparse/unreadable parquet are skipped HONESTLY.
    Returns ``{"n_sports", "by_sport", "_note"}``; idempotent.
    """
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    droot = Path(data_root) if data_root else _REPO_ROOT
    by_sport: Dict[str, Dict] = {}
    n_built = 0
    for sport, cfg in _SPORTS.items():
        if injected is not None:
            if sport not in injected:
                continue
            df = injected[sport]
        else:
            pq = droot / cfg["parquet"]
            if not pq.exists():
                by_sport[sport] = {"skipped": "missing parquet"}
                continue
            try:
                import pandas as pd  # noqa: PLC0415
                df = pd.read_parquet(pq)
            except Exception as exc:  # noqa: BLE001
                by_sport[sport] = {"skipped": f"unreadable parquet: {exc}"}
                continue
        info = _build_one(sport, df, write, root)
        by_sport[sport] = info
        if "skipped" not in info:
            n_built += 1
    return {"n_sports": n_built, "by_sport": by_sport,
            "_note": ("descriptive intelligence; markets efficient; calibration is not "
                      "edge; no edge claimed; realized box stats, not a per-game signal")}


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_keystats(organized_root=Path(root_arg) if root_arg else None, write=True)
    if "--json" in argv:
        slim = {sp: ({k: v for k, v in info.items() if k != "keystats_md"}
                     if isinstance(info, dict) else info)
                for sp, info in rep["by_sport"].items()}
        print(json.dumps({"n_sports": rep["n_sports"], "by_sport": slim,
                          "_note": rep["_note"]}, indent=2, default=str))
        return 0
    print(f"brain_keystats: {rep['n_sports']} sport(s) built")
    for sport, info in rep["by_sport"].items():
        if "skipped" in info:
            print(f"  [{sport:<7}] SKIPPED ({info['skipped']})")
        else:
            tag = " (sparse)" if info.get("small_n") else ""
            print(f"  [{sport:<7}] {info['n_games']} games / {info['n_team_games']} "
                  f"team-games -> {info['n_stats']} stats{tag}; top: {', '.join(info['top'][:5])}")
    print(f"NOTE: {rep['_note']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
