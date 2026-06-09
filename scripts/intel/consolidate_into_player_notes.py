"""Consolidate ALL matchup/scheme/situational intelligence INTO the single
canonical player note (vault/Intelligence/Players/<pid>_<slug>.md), so the
Obsidian graph shows ONE node per player — not a separate matchup note.

- 2025-26 is the PRIMARY season (current). 2024-25 kept as a compact secondary.
- Pulls H2H from data/cache/coverage_faced_allseasons.parquet (built game-by-game),
  the rest from data/cache/intel/player_<pid>.json, and lifts the agent-written
  "## Scouting Read" narrative out of the old Matchups/Players note.
- Idempotent: the merged block is wrapped in HTML markers and replaced on re-run.
- After merging, the old Matchups/Players/ notes are deleted by the caller.

Run AFTER the scouting fan-out completes:
  python scripts/intel/consolidate_into_player_notes.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MATRIX = os.path.join(ROOT, "data", "cache", "coverage_faced_allseasons.parquet")
JSON_DIR = os.path.join(ROOT, "data", "cache", "intel")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
OLD_MATCHUPS = os.path.join(ROOT, "vault", "Intelligence", "Matchups", "Players")

START = "<!-- MATCHUP-INTEL-START -->"
END = "<!-- MATCHUP-INTEL-END -->"
MIN_POSS = 18.0
SEASON_JSON = os.path.join(JSON_DIR, "season_2025_26.json")
_SEASON = None


def _season():
    global _SEASON
    if _SEASON is None:
        try:
            _SEASON = json.load(open(SEASON_JSON, encoding="utf-8"))
        except Exception:
            _SEASON = {"reg": {}, "playoffs": {}}
    return _SEASON


def season_line(pid):
    s = _season()
    r = s.get("reg", {}).get(str(pid))
    L = []
    if r:
        L.append(f"**2025-26 ({r['team']}, {r['g']}g):** {r['pts']} pts · {r['reb']} reb · {r['ast']} ast · "
                 f"{r['fg3m']} 3pm · {r['stl']} stl · {r['blk']} blk · {r['tov']} tov · {r['min']} min · "
                 f"{int(r['fg_pct']*100)}/{int(r['fg3_pct']*100)} FG/3P · L10 {r['l10_pts']}p/{r['l10_min']}m "
                 f"(last {r['last_game']})")
    p = s.get("playoffs", {}).get(str(pid))
    if p:
        L.append(f"**2026 Playoffs ({p['g']}g):** {p['pts']} pts · {p['reb']} reb · {p['ast']} ast · {p['min']} min")
    if L:
        L.append("")
    return L


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _baselines(df):
    ob = df.groupby("off_player_id").agg(p=("pts", "sum"), q=("poss", "sum")).reset_index()
    ob["base"] = ob.p / ob.q.replace(0, 1)
    return dict(zip(ob.off_player_id, ob.base))


def h2h_offense_block(df_season, pid, base, season_label, topn):
    off = df_season[(df_season.off_player_id == pid) & (df_season.poss >= MIN_POSS)] \
        .sort_values("poss", ascending=False).head(topn)
    if off.empty:
        return []
    b = base.get(pid, 0.0)
    L = [f"**Guarded by — {season_label}** (≥{MIN_POSS:.0f} poss · baseline {b:.2f} pts/poss · "
         f"vs-self <0.85 = tough, >1.15 = feasts):", "",
         "| Defender | G | Poss | Pts | AST | TOV | FG% | PPP | vs self |",
         "|---|--|--|--|--|--|--|--|--|"]
    tough, feast = [], []
    for r in off.itertuples(index=False):
        ppp = r.pts / r.poss if r.poss else 0
        rel = ppp / b if b else 0
        read = "tough" if rel < 0.85 else "feasts" if rel > 1.15 else "neutral"
        if read == "tough":
            tough.append(r.def_player_name)
        elif read == "feasts":
            feast.append(r.def_player_name)
        fgp = '' if pd.isna(r.fg_pct) else int(r.fg_pct * 100)
        L.append(f"| {r.def_player_name} | {r.n_games} | {r.poss:.0f} | {int(r.pts)} | {int(r.ast)} | "
                 f"{int(r.tov)} | {fgp} | {ppp:.2f} | {rel:.2f} ({read}) |")
    L.append("")
    if tough:
        L.append(f"- **Toughest covers:** {', '.join(tough[:7])}")
    if feast:
        L.append(f"- **Feasts on:** {', '.join(feast[:7])}")
    L.append("")
    return L


def defender_block(df_season, pid, season_label, topn=8):
    dfn = df_season[(df_season.def_player_id == pid) & (df_season.poss >= MIN_POSS)] \
        .sort_values("poss", ascending=False).head(topn)
    if dfn.empty:
        return []
    L = [f"**As a defender — who he guarded ({season_label}):**", "",
         "| Assignment | G | Poss | Pts allowed | FG% allowed |", "|---|--|--|--|--|"]
    for r in dfn.itertuples(index=False):
        fgp = '' if pd.isna(r.fg_pct) else int(r.fg_pct * 100)
        L.append(f"| {r.off_player_name} | {r.n_games} | {r.poss:.0f} | {int(r.pts)} | {fgp} |")
    L.append("")
    return L


def extract_scouting_read(pid, name):
    """Lift the agent-written narrative from the old Matchups/Players note."""
    fp = os.path.join(OLD_MATCHUPS, f"{pid}_{slug(name)}.md")
    if not os.path.exists(fp):
        return []
    txt = open(fp, encoding="utf-8").read()
    m = re.search(r"## Scouting Read \(agent\)(.*?)(?=\n## |\Z)", txt, re.S)
    if not m:
        return []
    body = m.group(1).strip()
    return ["**Scouting Read:**", "", body, ""] if body else []


def build_block(pid, name, df25, df24, base25, base24, intel):
    L = [START, "", "## Matchup & Scheme Intelligence",
         "*One-stop matchup card — how he plays against people & schemes. 2025-26 primary; "
         "built game-by-game. Single-pairing tails are small-sample leads.*", ""]
    L += season_line(pid)
    read = extract_scouting_read(pid, name)
    if read:
        L += read
    # H2H 2025-26 primary
    L += h2h_offense_block(df25, pid, base25, "2025-26", 14)
    # H2H 2024-25 compact
    L += h2h_offense_block(df24, pid, base24, "2024-25", 8)
    # as defender (2025-26)
    L += defender_block(df25, pid, "2025-26")
    if intel:
        sc = intel.get("defender_scouting", {})
        if sc:
            L.append("**Defensive scouting (matchup totals):**")
            for s in sorted(sc):
                v = sc[s]
                L.append(f"- {s}: {v['games']}g · {v['pts_allowed_per_game']} pts allowed/g · "
                         f"FG% allowed {int(v['fg_pct_allowed']*100)} · 3P% {int(v['fg3_pct_allowed']*100)} · "
                         f"{v['switches_per_game']} switch/g · {v['blocks_per_game']} blk/g")
            L.append("")
        vso = intel.get("vs_opponents", {})
        if vso and len(vso) >= 3:
            items = sorted(vso.items(), key=lambda kv: -kv[1]["pts"])
            best, worst = items[0], items[-1]
            L.append(f"**vs Opponents (career):** best vs [[{best[0]}]] ({best[1]['pts']} pts/n{best[1]['n']}) · "
                     f"worst vs [[{worst[0]}]] ({worst[1]['pts']} pts/n{worst[1]['n']})")
            L.append("")
        ss = intel.get("scheme_split", {})
        if ss and ss.get("best_scheme"):
            L.append(f"**Scheme:** best vs [[Schemes/{ss['best_scheme']}]] · worst vs [[Schemes/{ss['worst_scheme']}]] "
                     f"(TS gap {ss.get('ts_best_minus_worst')})")
            L.append("")
        q = intel.get("quarter_shape", {})
        if q and q.get("pts_by_quarter"):
            pq = q["pts_by_quarter"]
            L.append(f"**Quarter shape:** Q1 {pq.get(1,'–')} · Q2 {pq.get(2,'–')} · Q3 {pq.get(3,'–')} · "
                     f"Q4 {pq.get(4,'–')} (Q4−Q1 {q['q4_minus_q1']}{' — fades late' if q.get('q4_fade_flag') else ''})")
            L.append("")
    L += [END, ""]
    return "\n".join(L)


def upsert(note_path, block):
    if os.path.exists(note_path):
        txt = open(note_path, encoding="utf-8").read()
        if START in txt and END in txt:
            txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
        txt = txt.rstrip() + "\n\n" + block
    else:
        txt = block
    open(note_path, "w", encoding="utf-8").write(txt)


def main():
    df = pd.read_parquet(MATRIX)
    df25 = df[df.season == "2025-26"]
    df24 = df[df.season == "2024-25"]
    base25, base24 = _baselines(df25), _baselines(df24)

    name_map = {}
    for jf in glob.glob(os.path.join(JSON_DIR, "player_*.json")):
        try:
            d = json.load(open(jf, encoding="utf-8"))
            name_map[int(d["player_id"])] = d.get("name", "")
        except Exception:
            continue
    # also names from coverage
    for r in df[["off_player_id", "off_player_name"]].drop_duplicates().itertuples(index=False):
        name_map.setdefault(int(r.off_player_id), r.off_player_name)

    pids = set(name_map) | set(int(p) for p in df.off_player_id.unique()) | set(int(p) for p in df.def_player_id.unique())
    merged = created = 0
    for pid in sorted(pids):
        name = name_map.get(pid)
        if not name:
            continue
        intel = None
        jf = os.path.join(JSON_DIR, f"player_{pid}.json")
        if os.path.exists(jf):
            try:
                intel = json.load(open(jf, encoding="utf-8"))
            except Exception:
                intel = None
        block = build_block(pid, name, df25, df24, base25, base24, intel)
        if START + "\n\n## Matchup & Scheme Intelligence\n" in block and block.count("\n") < 8:
            continue  # empty
        # locate canonical Players/ note
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if cands:
            upsert(cands[0], block)
            merged += 1
        else:
            np_ = os.path.join(PLAYERS, f"{pid}_{slug(name)}.md")
            header = f"<!-- PLAYSTYLE-EXPORT v1 -->\n# {name}\n**player_id:** {pid}\n\n"
            open(np_, "w", encoding="utf-8").write(header + block)
            created += 1
    print(f"DONE: merged matchup intel into {merged} existing player notes, created {created} new.")


if __name__ == "__main__":
    main()
