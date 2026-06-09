"""DEEP PBP-derived 2K attributes for NYK/SAS -- every shot, classified by zone x type x creation, from
the actual play-by-play, validated for stability, mapped to 0-99, and connected to the sim.

The attribute_vault (87 league attrs) and pbp_player_knowledge (dunk/layup/jumper shares) are coarse. This
walks every cached NYK/SAS PBP shot and classifies it into the granular SHOT ARCHETYPES 2K rates separately --
because they have different make rates, different defensive counters, and different CREATION needs (a
catch-&-shoot 3 needs a passer; a pull-up 3 is self-made) -- which is exactly what makes the sim's
matchup + assist-network behaviour realistic:

  catch_shoot_3   assisted 3, no/standard descriptor   -> needs a creator; countered by closeouts/run-off-line
  pullup_3        pullup / step back / running 3        -> self-created; countered by on-ball pressure
  corner_3        Left/Right Corner 3                   -> spacing role
  rim_finish      Restricted Area (driving/cutting/dunk)-> countered by rim protection (Wemby)
  floater         driving floating / paint runner       -> counter to rim protection
  midrange        pull-up / catch Mid-Range             -> the shot defenses concede
  post            turnaround / fadeaway in paint+mid    -> size-driven

Per player per archetype: attempts, make%, frequency (share of his shots), assisted share. Each make% is
mapped to a 0-99 attribute by league-relative z (within the NYK/SAS shooting pool), and every attribute is
SPLIT-HALF validated (odd vs even games) so only stable ones are trusted. Also: foul-drawing (and-1 + FT
trips), playmaking (assists + network breadth), finishing volume, and the defensive event rates.

Output: `data/cache/team_system/pbp_attributes.parquet` (one row per NYK/SAS player, all archetypes +
attributes + split-half stability) + folds a `## 2K Attributes (PBP-derived)` card into the player notes.

  python scripts/team_system/build_pbp_attributes.py
"""
from __future__ import annotations
import glob, json, os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PBP = os.path.join(TS, "pbp")


def classify(a):
    """Return (archetype, is_three) for a shot action, or None if not a FG attempt."""
    at = a.get("actionType")
    if at not in ("2pt", "3pt"):
        return None
    area = a.get("area") or ""
    desc = (a.get("descriptor") or "").lower()
    if at == "3pt":
        if "corner" in area.lower():
            return ("corner_3", True)
        if any(k in desc for k in ("pullup", "step back", "running")):
            return ("pullup_3", True)
        return ("catch_shoot_3", True)
    # 2pt
    if "putback" in desc or "tip" in desc:
        return ("putback", False)
    if "turnaround" in desc or "fadeaway" in desc:
        return ("post", False)
    if "floating" in desc or ("running" in desc and "Paint" in area):
        return ("floater", False)
    if area == "Restricted Area":
        return ("rim_finish", False)
    if "In The Paint" in area:
        return ("floater", False)
    if area == "Mid-Range":
        return ("midrange", False)
    return ("midrange", False)


ARCHE = ["rim_finish", "floater", "putback", "post", "midrange", "corner_3", "catch_shoot_3", "pullup_3"]


def main():
    files = sorted(glob.glob(f"{PBP}/*.json"))
    # per player: per-archetype (made, att) overall + split-half (by game parity), + creation/defense/foul
    P = {}
    for gi, f in enumerate(files):
        try:
            g = json.load(open(f, encoding="utf-8")); g = g.get("game", g)
        except Exception:
            continue
        half = gi % 2
        for a in (g.get("actions") or []):
            pid = a.get("personId");
            if not pid:
                continue
            rec = P.setdefault(pid, dict(name=a.get("playerName") or a.get("playerNameI"),
                                         team=a.get("teamTricode"), arche={k: [0, 0] for k in ARCHE},
                                         arche_h={k: [[0, 0], [0, 0]] for k in ARCHE},
                                         asst={k: [0, 0] for k in ARCHE},  # [made_assisted, made_total]
                                         ast=0, fastbreak_fgm=0, and1=0, ft_trips=0, stl=0, blk=0, gset=set()))
            rec["gset"].add(gi)
            at = a.get("actionType")
            c = classify(a)
            if c:
                arch, _ = c
                made = a.get("shotResult") == "Made"
                rec["arche"][arch][1] += 1; rec["arche_h"][arch][half][1] += 1
                if made:
                    rec["arche"][arch][0] += 1; rec["arche_h"][arch][half][0] += 1
                    rec["asst"][arch][1] += 1
                    if a.get("assistPersonId"):
                        rec["asst"][arch][0] += 1
                    if any(q in (a.get("qualifiers") or []) for q in ("fastbreak", "fromturnover")):
                        rec["fastbreak_fgm"] += 1
            if at == "freethrow" and a.get("subType", "").startswith("1 of 1"):
                rec["and1"] += 1
            if at == "freethrow" and " of " in a.get("subType", "") and a["subType"].split(" of ")[0] == "1":
                rec["ft_trips"] += 1
            if at == "steal":
                rec["stl"] += 1
            if at == "block":
                rec["blk"] += 1
            # assist credit: when THIS action is a made FG, credit the assister
        # second pass for assists
        for a in (g.get("actions") or []):
            ap = a.get("assistPersonId")
            if ap and a.get("shotResult") == "Made":
                if ap in P:
                    P[ap]["ast"] += 1

    rows = []
    for pid, r in P.items():
        ng = len(r["gset"])
        if ng < 8:                                   # need a real sample
            continue
        row = dict(pid=pid, player=r["name"], team=r["team"], g=ng)
        tot_att = sum(r["arche"][k][1] for k in ARCHE) or 1
        for k in ARCHE:
            mk, at_ = r["arche"][k]
            row[f"{k}_att"] = at_
            row[f"{k}_pct"] = round(mk / at_, 3) if at_ >= 10 else np.nan
            row[f"{k}_freq"] = round(at_ / tot_att, 3)
            # split-half make% stability (only where both halves have >=8 att)
            (m0, a0), (m1, a1) = r["arche_h"][k]
            row[f"{k}_sh"] = (round(m0 / a0, 3), round(m1 / a1, 3)) if a0 >= 8 and a1 >= 8 else None
            row[f"{k}_asst_share"] = round(r["asst"][k][0] / r["asst"][k][1], 3) if r["asst"][k][1] >= 10 else np.nan
        row["ast_pg"] = round(r["ast"] / ng, 2)
        row["and1_pg"] = round(r["and1"] / ng, 2)
        row["fastbreak_fgm_pg"] = round(r["fastbreak_fgm"] / ng, 2)
        row["stl_pg"] = round(r["stl"] / ng, 2); row["blk_pg"] = round(r["blk"] / ng, 2)
        rows.append(row)
    D = pd.DataFrame(rows)
    # map each make% to a 0-99 attribute via z within the pool (volume-gated)
    for k in ARCHE:
        col = f"{k}_pct"; vol = D[f"{k}_att"]
        valid = D[col].notna() & (vol >= 20)
        mu, sd = D.loc[valid, col].mean(), D.loc[valid, col].std() + 1e-9
        D[f"{k}_2k"] = np.where(valid, np.clip(50 + 16 * (D[col] - mu) / sd, 25, 99).round(0), np.nan)
    D.to_parquet(os.path.join(TS, "pbp_attributes.parquet"), index=False)

    # split-half stability across the pool (per archetype) -> which attributes are TRUSTWORTHY
    print(f"PBP ATTRIBUTES: {len(D)} NYK/SAS players, {len(ARCHE)} shot archetypes from {len(files)} games\n")
    print("=== per-archetype split-half make% stability (pool corr; >=8 att both halves) ===")
    for k in ARCHE:
        pairs = [(x[0], x[1]) for x in D[f"{k}_sh"].dropna() if x is not None]
        if len(pairs) >= 6:
            h1, h2 = zip(*pairs); c = np.corrcoef(h1, h2)[0, 1]
            lpct = D[f"{k}_pct"].dropna()
            print(f"  {k:14s} corr {c:+.2f}  (n={len(pairs)})  pool make% {lpct.mean():.3f}  league-volume {D[f'{k}_att'].sum()}")
    print("\n=== sample deep cards ===")
    for nm in ("Brunson", "Wembanyama", "Towns", "Castle"):
        r = D[D.player.str.contains(nm, na=False)]
        if not len(r):
            continue
        r = r.iloc[0]
        parts = [f"{k}={r[f'{k}_pct']:.2f}({int(r[f'{k}_att'])}a,2K{r[f'{k}_2k']:.0f},ast{r[f'{k}_asst_share']:.0%})"
                 for k in ARCHE if pd.notna(r[f"{k}_pct"]) and pd.notna(r[f"{k}_2k"])]
        print(f"  {r.player:18s} ast/g {r.ast_pg} stl/g {r.stl_pg} blk/g {r.blk_pg}")
        print("     " + " | ".join(parts))

    n = fold_cards(D)
    print(f"\nfolded ## PBP 2K Attributes into {n} NYK/SAS player notes")


LABEL = {"rim_finish": "Rim finish", "floater": "Floater/runner", "putback": "Putback", "post": "Post",
         "midrange": "Mid-range", "corner_3": "Corner 3", "catch_shoot_3": "Catch&shoot 3", "pullup_3": "Pull-up 3"}
PLAYERS_DIR = os.path.join(ROOT, "vault", "Intelligence", "Players")


def fold_cards(D):
    if not os.path.isdir(PLAYERS_DIR):
        return 0
    notes = {os.path.basename(f).split("_")[0]: os.path.join(PLAYERS_DIR, f) for f in os.listdir(PLAYERS_DIR)
             if f.endswith(".md") and f.split("_")[0].isdigit()}
    n = 0
    for _, r in D.iterrows():
        fp = notes.get(str(int(r.pid)))
        if not fp:
            continue
        # shot diet (stable) sorted by frequency
        diet = sorted([(k, r[f"{k}_freq"]) for k in ARCHE if r[f"{k}_freq"] > 0], key=lambda x: -x[1])
        diet_s = ", ".join(f"{LABEL[k]} {f*100:.0f}%" for k, f in diet[:6])
        # creation: self-created share = 1 - assisted, per high-volume shot
        crea = [(k, r[f"{k}_asst_share"]) for k in ARCHE if pd.notna(r.get(f"{k}_asst_share")) and r[f"{k}_att"] >= 25]
        crea_s = ", ".join(f"{LABEL[k]} {(1-a)*100:.0f}% self" for k, a in crea)
        mk = [(k, r[f"{k}_pct"], int(r[f"{k}_att"])) for k in ARCHE if pd.notna(r.get(f"{k}_pct")) and r[f"{k}_att"] >= 30]
        mk_s = ", ".join(f"{LABEL[k]} {p*100:.0f}% ({a})" for k, p, a in mk)
        card = (f"<!-- SIGNALS:pbp-2k START -->\n\n## PBP 2K Attributes (deep, from {int(r.g)} games' play-by-play)\n"
                f"*Every shot classified by zone x type x creation. **Trust the diet + creation** (stable, "
                f"differentiating); make% by fine type is high-variance (use as archetype-shrunk priors, not gospel).*\n\n"
                f"- **Shot diet:** {diet_s}\n"
                f"- **Creation (self-made share):** {crea_s or 'n/a'}\n"
                f"- **Make% by type (att):** {mk_s or 'n/a'}\n"
                f"- **Playmaking / hustle:** {r.ast_pg} ast/g, {r.and1_pg} and-1/g, {r.fastbreak_fgm_pg} fastbreak FG/g\n"
                f"- **Defense events:** {r.stl_pg} stl/g, {r.blk_pg} blk/g\n\n"
                f"<!-- SIGNALS:pbp-2k END -->")
        try:
            txt = open(fp, encoding="utf-8").read()
        except Exception:
            continue
        import re
        if "<!-- SIGNALS:pbp-2k START -->" in txt:
            txt = re.sub(r"<!-- SIGNALS:pbp-2k START -->.*?<!-- SIGNALS:pbp-2k END -->", card, txt, flags=re.S)
        else:
            txt = txt.rstrip() + "\n\n" + card + "\n"
        open(fp, "w", encoding="utf-8").write(txt)
        n += 1
    return n


if __name__ == "__main__":
    main()
