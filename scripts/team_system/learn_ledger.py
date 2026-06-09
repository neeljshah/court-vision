"""ALWAYS-LEARNING ledger + validation GATE -- the discipline layer on top of the rebuild pipeline.

After `update.py` rebuilds every identity from the latest games, this:
  1. SNAPSHOTS what the system now BELIEVES (key learned identities + the in-game origin lever), keyed by
     the as-of date (latest game in the data) so you can SEE the beliefs sharpen game over game.
  2. RUNS THE BOARD GATE (pytest tests/test_sim_engine.py) so learning can never silently ship a
     regression -- a red board is flagged, not buried.
  3. APPENDS one row to `vault/Intelligence/LEARNING_LOG.md` (the visible always-learning record).

The learning that is SAFE to do continuously = the identity / rate layer (empirical-Bayes that sharpens
with data). Betting policy + model STRUCTURE are NOT auto-learned here (that is the overfit / auto-apply
trap the project guards against) -- they change only behind a gated, separately-validated flag.

  python scripts/team_system/learn_ledger.py            # snapshot + gate + append ledger
  python scripts/team_system/learn_ledger.py --nogate   # snapshot + append only (skip pytest)
"""
from __future__ import annotations
import json, os, subprocess, sys
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
LOG = os.path.join(ROOT, "vault", "Intelligence", "LEARNING_LOG.md")
PY = sys.executable


def _load(name):
    fp = os.path.join(TS, name)
    return pd.read_parquet(fp) if os.path.exists(fp) else None


def snapshot():
    s = {}
    tg = _load("team_game.parquet")
    if tg is not None:
        s["asof"] = str(tg.date.max()); s["nyksas_games"] = int(len(tg))
    lg = _load("league_team_game.parquet")
    if lg is not None:
        s["league_games"] = int(lg.gid.nunique()); s["league_asof"] = str(lg.date.max())
    td = _load("team_defense.parquet")
    if td is not None:
        d = td.set_index("team")
        for t in ("NYK", "SAS"):
            if t in d.index:
                s[f"{t}_tov"] = float(d.loc[t, "tov_force"]); s[f"{t}_ft"] = float(d.loc[t, "ft_force"])
    rec = _load("recency_rates.parquet")
    if rec is not None and "player" in rec.columns:
        for nm, key in (("Wembanyama", "Wemby"), ("Brunson", "Brunson")):
            r = rec[rec.player.str.contains(nm, na=False)]
            if len(r):
                s[f"{key}_rec_pts"] = round(float(r.iloc[0]["pts_pg_rec"]), 1)
    op = os.path.join(TS, "origin_ppp.json")
    if os.path.exists(op):
        o = json.load(open(op)); s["origin_trans_mult"] = o.get("transition_mult"); s["origin_2nd_mult"] = o.get("second_chance_mult")
    ds = _load("defender_suppression.parquet")
    if ds is not None:
        s["n_defenders_rated"] = int(len(ds))
    return s


def gate():
    try:
        r = subprocess.run([PY, "-m", "pytest", os.path.join(ROOT, "tests", "test_sim_engine.py"), "-q"],
                           capture_output=True, text=True, timeout=180, cwd=ROOT)
        ok = r.returncode == 0
        tail = [l for l in r.stdout.splitlines() if l.strip()][-1:]
        return ok, (tail[0] if tail else "")
    except Exception as e:
        return False, f"gate error: {e}"


def main():
    s = snapshot()
    if "--nogate" in sys.argv:
        board, detail = None, "skipped"
    else:
        board, detail = gate()
    def f3(k):
        v = s.get(k); return f"{v:.3f}" if isinstance(v, (int, float)) else "?"
    row = (f"| {s.get('asof','?')} | {s.get('nyksas_games','?')} | {s.get('league_games','?')} "
           f"| {f3('NYK_tov')}/{f3('NYK_ft')} | {f3('SAS_tov')}/{f3('SAS_ft')} "
           f"| {s.get('Wemby_rec_pts','?')}/{s.get('Brunson_rec_pts','?')} "
           f"| x{s.get('origin_trans_mult','?')}/x{s.get('origin_2nd_mult','?')} "
           f"| {'GREEN' if board else ('skipped' if board is None else 'RED')} |")
    header = ("# Always-Learning Ledger\n\n*One row per learning cycle (after `update.py`). Shows the system's "
              "beliefs sharpening as games arrive; the board gate ensures learning never ships a regression.*\n\n"
              "| as-of | NYK/SAS g | league g | NYK tov/ft | SAS tov/ft | Wemby/Brunson rec pts | origin trans/2nd | board |\n"
              "|---|---|---|---|---|---|---|---|\n")
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if not os.path.exists(LOG):
        open(LOG, "w", encoding="utf-8").write(header)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(row + "\n")
    print("LEARNING SNAPSHOT:", json.dumps(s, default=str))
    print(f"BOARD GATE: {'GREEN' if board else ('SKIPPED' if board is None else 'RED -> ' + detail)}  ({detail})")
    print(f"ledger -> {LOG}")
    if board is False:
        print("!! board RED -- learning produced a regression; investigate before trusting predictions")
        sys.exit(1)


if __name__ == "__main__":
    main()
