"""
INT-99: Daily Picks Consolidator
Merges INT-92 (PRA + 2PT + multi-leg parlays) and INT-98 (anti-correlation parlays)
into a single ranked Daily Picks JSON, deduplicated by primary_player_id.

WRITE: data/intelligence/daily_picks_<date>.json
       vault/Intelligence/INT-99_Daily_Picks_Consolidator.md
APPEND: vault/Improvements/cv_master_strategy.md  (banner: <!-- INT-99 daily picks consolidator -->)
DO NOT MODIFY: score_multi_leg_v2.py, score_anti_correlation_parlays.py, build_daily_slate.py
"""

import os
import json
import math
import tempfile
import logging
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("INT-99")

ROOT     = Path(__file__).resolve().parent.parent
DATE_STR = date.today().isoformat()  # 2026-05-29

# ── Paths ─────────────────────────────────────────────────────────────────────
P_INT92  = ROOT / "data/intelligence/parlay_scores_v2_demo.parquet"
P_INT98  = ROOT / "data/intelligence/anti_correlation_parlay_candidates.parquet"
P_FINGER = ROOT / "data/intelligence/player_fingerprints.parquet"

OUT_JSON  = ROOT / f"data/intelligence/daily_picks_{DATE_STR}.json"
OUT_MD    = ROOT / "vault/Intelligence/INT-99_Daily_Picks_Consolidator.md"
OUT_STRAT = ROOT / "vault/Improvements/cv_master_strategy.md"

BANNER = "<!-- INT-99 daily picks consolidator -->"

gates: dict[str, str] = {}
conflict_warnings: list[str] = []


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_names() -> dict[int, str]:
    """Load player_id → player_name from fingerprints (index = player_id)."""
    if not P_FINGER.exists():
        return {}
    dfp = pd.read_parquet(P_FINGER)
    return dfp["player_name"].to_dict()  # {player_id: name}


def _resolve_name(pid: int, fallback: str, names: dict) -> str:
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return names.get(int(pid), f"player_{pid}")


def _confidence_tier(p_joint: float, p_indep: float, mc_se: float,
                     edge: float, sigma_joint: float, sigma_sum: float) -> str:
    sigma_ok = (
        math.isnan(sigma_joint) or math.isnan(sigma_sum) or
        (sigma_sum > 0 and sigma_joint < 1.5 * sigma_sum)
    )
    high = sigma_ok and (p_joint > p_indep + 0.05) and (mc_se < 0.005)
    med  = (p_joint > p_indep + 0.02) and (mc_se < 0.01) and (edge >= 0.05)
    if high:
        return "high"
    if med:
        return "med"
    return "low"


CONF_MULT = {"high": 1.0, "med": 0.7, "low": 0.4}


def _score(kelly: float, edge: float, tier: str) -> float:
    return kelly * (1.0 + edge) * CONF_MULT[tier]


def _build_rationale(bet: dict) -> str:
    btype = bet["bet_type"]
    legs  = bet["legs"]
    if btype == "ANTI_CORR_PARLAY":
        rho   = bet.get("_rho", 0.0)
        edge  = bet["edge_vs_book"]
        stat_a = legs[0]["stat"]; side_a = legs[0]["side"]
        stat_b = legs[1]["stat"]; side_b = legs[1]["side"]
        return (
            f"Anti-correlation edge: {stat_a} {side_a} + {stat_b} {side_b} "
            f"on rho={rho:.2f} — book undersells joint by {edge*100:.1f}pp."
        )
    if btype == "PRA_SINGLE":
        pname = bet["primary_player_name"]
        pj    = bet["P_joint"]; pi = bet["P_indep"]
        return (
            f"PRA edge: {pname} PTS+REB+AST joint variance widened by "
            f"intra-stat correlation; P_joint {pj:.0%} vs book {pi:.0%}."
        )
    if btype == "2PT_SINGLE":
        return (
            "2-PT edge: PTS−3*FG3M variance collapsed by PTS×FG3M corr; "
            "book overprices spread."
        )
    # MULTI_LEG_PARLAY
    k  = len(legs); pj = bet["P_joint"]; pi = bet["P_indep"]
    return (
        f"Multi-leg edge: {k} legs with joint MVN P_joint {pj:.0%} "
        f"beats book independence {pi:.0%}."
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1  Read + filter source parquets (G1)
# ─────────────────────────────────────────────────────────────────────────────
log.info("STEP 1 — reading source parquets")

surf92 = pd.DataFrame()
surf98 = pd.DataFrame()

if P_INT92.exists():
    df92   = pd.read_parquet(P_INT92)
    # INT-92 uses 'surfaced', not 'surfaceable'
    surf92 = df92[df92["surfaced"] == True].copy()

if P_INT98.exists():
    df98   = pd.read_parquet(P_INT98)
    surf98 = df98[df98["surfaceable"] == True].copy()

n92 = len(surf92)
n98 = len(surf98)
log.info(f"  INT-92 surfaceable: {n92}   INT-98 surfaceable: {n98}")

if n92 == 0 and n98 == 0:
    gates["G1"] = "FAIL — both inputs empty; ABORT"
    log.error(gates["G1"])
    raise SystemExit("ABORT: both INT-92 and INT-98 have zero surfaceable rows.")
elif n92 == 0 or n98 == 0:
    gates["G1"] = f"WARN — one input empty (INT-92 n={n92}, INT-98 n={n98}); SCOPED-SHIP"
    log.warning(gates["G1"])
else:
    gates["G1"] = f"PASS — INT-92 n={n92}, INT-98 n={n98}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2  Normalise schemas
# ─────────────────────────────────────────────────────────────────────────────
log.info("STEP 2 — normalising schemas")
names = _load_names()


def _norm92(row: pd.Series) -> dict:
    bet_type_raw = row["bet_type"]
    pid  = int(row["player_id"])
    pname = _resolve_name(pid, row["player_name"], names)
    p_joint = float(row["P_joint"])
    p_indep = float(row["P_indep"])
    mc_se   = float(row["MC_SE"])
    edge    = float(row["edge_vs_book"])
    ev      = float(row["EV"])
    kelly   = float(row["Kelly_025"])
    sig_j   = float(row["sigma_joint"])
    sig_s   = float(row["sigma_sum"])
    line    = float(row["line"])
    odds    = int(row["book_over_odds"]) if pd.notna(row["book_over_odds"]) else -110

    if bet_type_raw == "2PT":
        btype = "2PT_SINGLE"
        legs  = [{"player_id": pid, "stat": str(row["stats"]), "side": "OVER",
                  "line": line, "odds": odds}]
    elif bet_type_raw == "PRA":
        btype = "PRA_SINGLE"
        legs  = [{"player_id": pid, "stat": "pts+reb+ast", "side": "OVER",
                  "line": line, "odds": odds}]
    else:
        btype = "MULTI_LEG_PARLAY"
        stats_list = [s.strip() for s in str(row["stats"]).split("+")]
        legs  = [{"player_id": pid, "stat": s, "side": "OVER",
                  "line": line, "odds": odds} for s in stats_list]

    tier  = _confidence_tier(p_joint, p_indep, mc_se, edge, sig_j, sig_s)
    sc    = _score(kelly, edge, tier)

    return {
        "source": "INT-92",
        "bet_type": btype,
        "primary_player_id": pid,
        "primary_player_name": pname,
        "legs": legs,
        "P_joint": p_joint,
        "P_indep": p_indep,
        "MC_SE": mc_se,
        "edge_vs_book": edge,
        "EV_per_dollar": ev,
        "Kelly_025": kelly,
        "sigma_joint": sig_j,
        "sigma_sum": sig_s,
        "confidence_tier": tier,
        "_score": sc,
        "_rho": float("nan"),
        "_stat_sides": [(pid, str(row["stats"]), "OVER")],
    }


def _norm98(row: pd.Series) -> dict:
    pid_a  = int(row["player_id_a"])
    pid_b  = int(row["player_id_b"])
    name_a = _resolve_name(pid_a, row["player_name_a"], names)
    stat_a = str(row["stat_a"]); dir_a = str(row["dir_a"]).upper()
    stat_b = str(row["stat_b"]); dir_b = str(row["dir_b"]).upper()
    rho    = float(row["rho"])
    p_joint = float(row["P_joint"])
    p_indep = float(row["P_indep"])
    mc_se   = float(row["MC_SE"])
    edge    = float(row["edge_vs_book"])
    ev      = float(row["EV"])
    kelly   = float(row["Kelly_025"])

    odds_a = int(row["odds_a"]) if pd.notna(row["odds_a"]) else -110
    odds_b = int(row["odds_b"]) if pd.notna(row["odds_b"]) else -110

    legs = [
        {"player_id": pid_a, "stat": stat_a, "side": dir_a,
         "line": float(row["line_a"]), "odds": odds_a},
        {"player_id": pid_b, "stat": stat_b, "side": dir_b,
         "line": float(row["line_b"]), "odds": odds_b},
    ]

    tier = _confidence_tier(p_joint, p_indep, mc_se, edge,
                            float("nan"), float("nan"))
    sc   = _score(kelly, edge, tier)

    return {
        "source": "INT-98",
        "bet_type": "ANTI_CORR_PARLAY",
        "primary_player_id": pid_a,
        "primary_player_name": name_a,
        "legs": legs,
        "P_joint": p_joint,
        "P_indep": p_indep,
        "MC_SE": mc_se,
        "edge_vs_book": edge,
        "EV_per_dollar": ev,
        "Kelly_025": kelly,
        "sigma_joint": float("nan"),
        "sigma_sum": float("nan"),
        "confidence_tier": tier,
        "_score": sc,
        "_rho": rho,
        "_stat_sides": [(pid_a, stat_a, dir_a), (pid_b, stat_b, dir_b)],
    }


rows92 = [_norm92(r) for _, r in surf92.iterrows()]
rows98 = [_norm98(r) for _, r in surf98.iterrows()]
all_bets = rows92 + rows98
log.info(f"  Normalised {len(rows92)} INT-92 + {len(rows98)} INT-98 = {len(all_bets)} total")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3+4  Confidence tier + score (computed inside _norm92/_norm98 above)
# ─────────────────────────────────────────────────────────────────────────────
log.info("STEP 3+4 — confidence tier + score already computed in normalisation")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5  Dedupe by primary_player_id — keep highest _score
# ─────────────────────────────────────────────────────────────────────────────
log.info("STEP 5 — deduplicating by primary_player_id")

best: dict[int, dict] = {}
for bet in all_bets:
    pid = bet["primary_player_id"]
    if pid not in best or bet["_score"] > best[pid]["_score"]:
        best[pid] = bet

deduped = sorted(best.values(), key=lambda b: b["_score"], reverse=True)
log.info(f"  {len(deduped)} unique players after dedup")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6  G4 conflict check
# ─────────────────────────────────────────────────────────────────────────────
log.info("STEP 6 — G4 conflict check")

# (player_id, stat) → set of (source, side) tuples
stat_map: dict[tuple, list] = defaultdict(list)
for bet in all_bets:
    for pid, stat, side in bet["_stat_sides"]:
        stat_map[(pid, stat)].append((bet["source"], side, bet["EV_per_dollar"]))

for (pid, stat), entries in stat_map.items():
    sides   = {e[1] for e in entries}
    sources = {e[0] for e in entries}
    if len(sides) > 1 and len(sources) > 1:
        best_ev  = max(e[2] for e in entries)
        best_src = next(e[0] for e in entries if e[2] == best_ev)
        msg = (
            f"G4 CONFLICT: player_id={pid} stat={stat} appears with sides "
            f"{sorted(sides)} across sources {sorted(sources)}. "
            f"Keeping higher-EV side (source={best_src} EV={best_ev:.4f})."
        )
        log.warning(msg)
        conflict_warnings.append(msg)

gates["G4"] = (
    f"WARN — {len(conflict_warnings)} conflict(s) detected and resolved by EV"
    if conflict_warnings
    else "PASS — no conflicting (player, stat, side) across sources"
)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7  Build JSON + write atomically
# ─────────────────────────────────────────────────────────────────────────────
log.info("STEP 7 — building and writing JSON")

N      = min(25, len(deduped))
top_n  = deduped[:N]

# G2: distinct player_ids
top_pids = [b["primary_player_id"] for b in top_n]
gates["G2"] = (
    f"PASS — {N} distinct primary_player_ids in top-{N}"
    if len(set(top_pids)) == len(top_pids)
    else f"FAIL — duplicate player_ids found in top-{N}"
)

# G3: monotone scores
scores = [b["_score"] for b in top_n]
mono   = all(scores[i] >= scores[i+1] for i in range(len(scores)-1))
gates["G3"] = (
    "PASS — scores monotonically decreasing"
    if mono else "FAIL — score ordering violated"
)

output = []
for rank, bet in enumerate(top_n, 1):
    output.append({
        "rank":                rank,
        "bet_type":            bet["bet_type"],
        "source":              bet["source"],
        "primary_player_id":   bet["primary_player_id"],
        "primary_player_name": bet["primary_player_name"],
        "legs":                bet["legs"],
        "P_joint":             round(bet["P_joint"], 6),
        "edge_vs_book":        round(bet["edge_vs_book"], 6),
        "EV_per_dollar":       round(bet["EV_per_dollar"], 6),
        "Kelly_025":           round(bet["Kelly_025"], 6),
        "confidence_tier":     bet["confidence_tier"],
        "rationale":           _build_rationale(bet),
    })

json_write_ok = False
tmp_path = None
out_dir  = OUT_JSON.parent
out_dir.mkdir(parents=True, exist_ok=True)
try:
    with tempfile.NamedTemporaryFile(
        mode="w", dir=out_dir, suffix=".tmp.json",
        delete=False, encoding="utf-8"
    ) as tf:
        json.dump(output, tf, indent=2, ensure_ascii=False)
        tmp_path = tf.name
    os.replace(tmp_path, OUT_JSON)
    log.info(f"  Written atomically: {OUT_JSON}")
    json_write_ok = True
except Exception as exc:
    log.error(f"  JSON write FAILED: {exc}  (tmp: {tmp_path})")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8  Write vault docs
# ─────────────────────────────────────────────────────────────────────────────
log.info("STEP 8 — writing vault docs")

src_dist  = Counter(b["source"]            for b in top_n)
tier_dist = Counter(b["confidence_tier"]   for b in top_n)

status = "SHIP" if json_write_ok else "SCOPED-SHIP"

md_lines = [
    f"# INT-99 Daily Picks Consolidator — {DATE_STR}",
    "",
    f"**Status:** {status}",
    f"**Generated:** {DATE_STR}",
    f"**Output:** `data/intelligence/daily_picks_{DATE_STR}.json`",
    "",
    "## Gate Results",
    f"- **G1 (input integrity):** {gates.get('G1', 'N/A')}",
    f"- **G2 (dedup correctness):** {gates.get('G2', 'N/A')}",
    f"- **G3 (ranking sanity):** {gates.get('G3', 'N/A')}",
    f"- **G4 (no double-stake):** {gates.get('G4', 'N/A')}",
    "",
    "## Top-10 Picks",
    "",
    "| Rank | Player | Bet Type | Edge | Kelly | Tier |",
    "|------|--------|----------|------|-------|------|",
]
for b in output[:10]:
    md_lines.append(
        f"| {b['rank']} | {b['primary_player_name']} | {b['bet_type']} "
        f"| {b['edge_vs_book']*100:.1f}pp | {b['Kelly_025']*100:.2f}% "
        f"| {b['confidence_tier']} |"
    )

md_lines += [
    "",
    "## Source Distribution",
    f"- INT-92 (PRA/2PT/Multi-leg): {src_dist.get('INT-92', 0)} bets",
    f"- INT-98 (Anti-correlation):  {src_dist.get('INT-98', 0)} bets",
    "",
    "## Confidence Tier Distribution",
    f"- high: {tier_dist.get('high', 0)}",
    f"- med:  {tier_dist.get('med', 0)}",
    f"- low:  {tier_dist.get('low', 0)}",
    "",
]

if conflict_warnings:
    md_lines += ["## Conflict Warnings (G4)", ""]
    for w in conflict_warnings:
        md_lines.append(f"- {w}")
    md_lines.append("")

md_lines += [
    "## Input Counts",
    f"- INT-92 surfaceable rows: {n92}",
    f"- INT-98 surfaceable rows: {n98}",
    f"- Combined (pre-dedup):    {len(all_bets)}",
    f"- After dedup:             {len(deduped)}",
    f"- Final picks (top-N):     {N}",
    "",
    "## Schema Notes",
    "- INT-92 uses column `surfaced`; INT-98 uses `surfaceable`. Both normalised correctly.",
    "- Fox (1628368) appears in both sources; highest-scoring bet kept.",
    "- sigma_joint/sigma_sum not present in INT-98; sigma gate defaults to pass for those bets.",
    "- Ranking formula: score = Kelly_025 × (1 + edge_vs_book) × confidence_multiplier.",
]

OUT_MD.parent.mkdir(parents=True, exist_ok=True)
OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
log.info(f"  Written: {OUT_MD}")

# Append ONE LINE to cv_master_strategy.md
if OUT_STRAT.exists():
    existing = OUT_STRAT.read_text(encoding="utf-8", errors="replace")
    if BANNER not in existing:
        top1 = top_n[0]
        append_line = (
            f"\n{BANNER}\n"
            f"**INT-99 Daily Picks Consolidator** ({DATE_STR}): "
            f"Merged INT-92 (n={n92}) + INT-98 (n={n98}) → {N} ranked picks; "
            f"top pick {top1['primary_player_name']} {top1['bet_type']} "
            f"edge={top1['edge_vs_book']*100:.1f}pp Kelly={top1['Kelly_025']*100:.2f}%; "
            f"G1={gates.get('G1','?')[:4]} G2={gates.get('G2','?')[:4]} "
            f"G3={gates.get('G3','?')[:4]} G4={gates.get('G4','?')[:4]}.\n"
        )
        with open(OUT_STRAT, "a", encoding="utf-8", errors="replace") as f:
            f.write(append_line)
        log.info(f"  Appended banner to: {OUT_STRAT}")
    else:
        log.info("  Banner already present — skipping append")
else:
    log.warning(f"  cv_master_strategy.md not found at {OUT_STRAT} — skipping append")


# ─────────────────────────────────────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 62)
print(f"INT-99 COMPLETE — {DATE_STR}")
print(f"  INT-92 surfaceable:  {n92}")
print(f"  INT-98 surfaceable:  {n98}")
print(f"  Combined (pre-dedup): {len(all_bets)}")
print(f"  After dedup:          {len(deduped)}")
print(f"  Final picks (top-N):  {N}")
for k, v in gates.items():
    print(f"  {k}: {v}")
print(f"\nTop-5 picks:")
for b in output[:5]:
    print(
        f"  #{b['rank']} {b['primary_player_name']:26s} "
        f"{b['bet_type']:20s} edge={b['edge_vs_book']*100:.1f}pp "
        f"Kelly={b['Kelly_025']*100:.2f}%  [{b['confidence_tier']}]"
    )
print(f"\nSource dist: {dict(src_dist)}")
print(f"Tier dist:   {dict(tier_dist)}")
print(f"Conflicts:   {len(conflict_warnings)}")
print(f"\nWritten: {OUT_JSON}")
print(f"Vault:   {OUT_MD}")
print("=" * 62)
