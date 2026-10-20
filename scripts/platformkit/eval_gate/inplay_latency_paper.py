"""Recompute the in-play latency paper tables from committed ledgers only.

Inputs (read-only, all tracked):
  docs/evidence/forward/latency/*_latency_ledger.json   (S663 nightly ledgers)
  docs/evidence/forward/model2/m2/2026-*.json            (S542 arm M2 read-outs)
Outputs:
  docs/papers/INPLAY_LATENCY_2026.md   (only the text between the GENERATED markers)
  docs/papers/out/inplay_latency_2026.json

Deterministic: sorted inputs, fixed bootstrap seed, no wall-clock fields.
Usage: python -m scripts.platformkit.eval_gate.inplay_latency_paper [--repo-root .] [--check]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

LEDGER_GLOB = "docs/evidence/forward/latency/*_latency_ledger.json"
M2_GLOB = "docs/evidence/forward/model2/m2/2026-*.json"
PAPER = "docs/papers/INPLAY_LATENCY_2026.md"
SIDECAR = "docs/papers/out/inplay_latency_2026.json"
MIN_NIGHTS = 10      # slate R7 / map item 5 kill rule: fewer nights -> INSUFFICIENT, not pooled
BOOT_REPS = 2000
BOOT_SEED = 20261020
QS = ("p50", "p90", "p99")


def sha256_lf(path: Path) -> str:
    """SHA-256 of the file with CRLF normalised to LF (stable across git autocrlf)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_ledgers(root: Path) -> list[dict]:
    """One record per (night, sport, feed) from each ledger's pooled block, plus per-game rows."""
    out = []
    for f in sorted(root.glob(LEDGER_GLOB)):
        d = json.loads(f.read_text(encoding="utf-8"))
        night = d["range"]["first"]
        games = {}
        for r in d.get("rows", []):
            games.setdefault(r["sport"], []).append(r)
        for p in d["pooled"]:
            rme = p["receipt_minus_event"]
            out.append({
                "night": night, "sport": p["sport"], "feed": p["feed"], "games": p["games"],
                "underpowered_games": p["underpowered_games"], "flagged_games": p["flagged_games"],
                "n": rme["n"], **{q: rme.get(q) for q in QS}, "reason": rme.get("reason"),
                "offset_journal": d.get("offset_journal") is not None,
                "bmf_games": [(night, g["game_key"], g["book_moved_first"]["num"],
                               g["book_moved_first"]["den"]) for g in games.get(p["sport"], [])
                              if g["book_moved_first"]["den"]],
            })
    return out


def cluster_share(games: list[tuple]) -> dict:
    """Pooled share sum(num)/sum(den) with a game-clustered percentile bootstrap interval."""
    if not games:
        return {"games": 0, "num": 0, "den": 0, "share": None, "lo": None, "hi": None}
    num = np.array([g[2] for g in games], dtype=float)
    den = np.array([g[3] for g in games], dtype=float)
    idx = np.random.default_rng(BOOT_SEED).integers(0, len(games), size=(BOOT_REPS, len(games)))
    boot = num[idx].sum(axis=1) / den[idx].sum(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"games": len(games), "num": int(num.sum()), "den": int(den.sum()),
            "share": round(float(num.sum() / den.sum()), 4),
            "lo": round(float(lo), 4), "hi": round(float(hi), 4)}


def summarise(recs: list[dict], min_nights: int = MIN_NIGHTS) -> dict:
    """Per sport: nights listed, nights with events, n, and the spread of nightly quantiles.

    A night is a unique date (several feeds on one date are one night), and each game enters
    the bootstrap once, keyed by (night, game_key), however many feeds carry its sport."""
    sports = {}
    for r in recs:
        s = sports.setdefault(r["sport"], {"nights_listed": set(), "nights_events": set(), "n": 0,
                                           "games": 0, "feeds": set(), "night_q": [], "bmf": {}})
        s["nights_listed"].add(r["night"])
        s["games"] += r["games"]
        s["feeds"].add(r["feed"])
        if r["n"] > 0:
            s["nights_events"].add(r["night"])
            s["n"] += r["n"]
            s["night_q"].append([r[q] for q in QS])
            for g in r["bmf_games"]:
                s["bmf"].setdefault(g[:2], g)
    out = {}
    for sport, s in sorted(sports.items()):
        ok = len(s["nights_events"]) >= min_nights
        row = {"nights_listed": len(s["nights_listed"]), "nights_with_events": len(s["nights_events"]),
               "events_n": s["n"], "games_listed": s["games"], "feeds": sorted(s["feeds"]),
               "verdict": "POOLED" if ok else "INSUFFICIENT"}
        if s["night_q"]:
            a = np.array(s["night_q"], dtype=float)
            for i, q in enumerate(QS):
                row[q] = {"min": float(a[:, i].min()), "median": float(np.median(a[:, i])),
                          "max": float(a[:, i].max())}
        row["book_moved_first"] = cluster_share(list(s["bmf"].values())) if ok else None
        out[sport] = row
    return out


def staleness(root: Path) -> dict:
    """Live ticks by receipt age vs the S542 read-out's 15 s fresh/stale split, per sport."""
    out = {}
    for f in sorted(root.glob(M2_GLOB)):
        d = json.loads(f.read_text(encoding="utf-8"))
        for c in d.get("cells", []):
            if c["cls"] == "live" and c["segment"] == "all" and c["age"] in ("fresh", "stale"):
                s = out.setdefault(c["sport"], {"fresh": 0, "stale": 0, "nights": set()})
                s[c["age"]] += c["n_ticks"]
                s["nights"].add(d["date"])
    for s in out.values():
        tot = s["fresh"] + s["stale"]
        s["stale_share"] = round(s["stale"] / tot, 4) if tot else None
        s["nights"] = len(s["nights"])
    return dict(sorted(out.items()))


def interval_sentence(summ: dict) -> str:
    """Read each POOLED sport's interval against 0.5 (never a fixed claim)."""
    parts = []
    for sp, s in summ.items():
        b = s["book_moved_first"]
        if not b or b["lo"] is None:
            continue
        if b["lo"] > 0.5:
            parts.append((sp, "lies entirely above 0.5, so in this sample the book receipt moved first "
                              "on more than half of the moves"))
        elif b["hi"] < 0.5:
            parts.append((sp, "lies entirely below 0.5, so in this sample the book receipt moved first "
                              "on fewer than half of the moves"))
        else:
            parts.append((sp, "contains 0.5, so neither ordering is established"))
    if not parts:
        return "No sport is POOLED, so no interval is read."
    if len(parts) == 1:
        return f"The interval {parts[0][1]}."
    return " ".join(f"The {sp} interval {txt}." for sp, txt in parts)


def gap_nights(recs: list[dict]) -> list[str]:
    nights = sorted({r["night"] for r in recs})
    if not nights:
        return []
    d0, d1 = (dt.date.fromisoformat(x) for x in (nights[0], nights[-1]))
    have = set(nights)
    return [str(d0 + dt.timedelta(i)) for i in range((d1 - d0).days + 1)
            if str(d0 + dt.timedelta(i)) not in have]


def fmt(v) -> str:
    return "-" if v is None else (f"{v:.1f}" if isinstance(v, float) else str(v))


def render_results(recs: list[dict], summ: dict, stale: dict, gaps: list[str]) -> str:
    nights = sorted({r["night"] for r in recs})
    L = [f"Ledgers read: {len(nights)} nights, {nights[0]} to {nights[-1]}. "
         f"Calendar nights in that span with no committed ledger: {len(gaps)} "
         f"({', '.join(gaps) or 'none'}). Offset journal present on "
         f"{len({r['night'] for r in recs if r['offset_journal']})} nights.", "",
         "Table 1. Receipt minus play clock (seconds), per sport, across nights. "
         f"Nightly quantiles are summarised as min / median / max across nights; a sport with "
         f"fewer than {MIN_NIGHTS} nights carrying events is INSUFFICIENT.", "",
         "| sport | feed | nights listed | nights with events | events n | p50 min/med/max "
         "| p90 min/med/max | p99 min/med/max | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    for sp, s in summ.items():
        qs = [" / ".join(fmt(s[q][k]) for k in ("min", "median", "max")) if q in s else "-" for q in QS]
        L.append(f"| {sp} | {', '.join(s['feeds'])} | {s['nights_listed']} | {s['nights_with_events']} "
                 f"| {s['events_n']} | {' | '.join(qs)} | {s['verdict']} |")
    L += ["", "Table 2. Book-moved-first share (POOLED sports only; descriptive, game-clustered "
          f"percentile bootstrap, {BOOT_REPS} reps, seed {BOOT_SEED}).", "",
          "| sport | games | num / den | share | 95% interval |", "|---|---|---|---|---|"]
    for sp, s in summ.items():
        b = s["book_moved_first"]
        if b:
            L.append(f"| {sp} | {b['games']} | {b['num']} / {b['den']} | {b['share']} "
                     f"| [{b['lo']}, {b['hi']}] |")
    L += ["", interval_sentence(summ) + " The book time is our own "
          "snapshot receipt, not the venue's update time, so the complement is not evidence that our "
          "feed leads the venue. It is not an information advantage and not a pricing input."]
    L += ["", "Table 3. Live ticks by our receipt age at the S542 read-out's 15 s split "
          "(fresh <= 15 s < stale), summed over the committed M2 read-out nights.", "",
          "| sport | read-out nights | fresh ticks | stale ticks | stale share |", "|---|---|---|---|---|"]
    for sp, s in stale.items():
        L.append(f"| {sp} | {s['nights']} | {s['fresh']} | {s['stale']} | {s['stale_share']} |")
    L += ["", "Table 4. Per night and sport (receipt minus play clock, seconds). "
          "UNDERPOWERED = every game on that night is under the ledger's own per-game floor.", "",
          "| night | sport | feed | games | events n | p50 | p90 | p99 | label |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        lab = r["reason"] or ("UNDERPOWERED" if r["games"] == r["underpowered_games"] else "ok")
        L.append(f"| {r['night']} | {r['sport']} | {r['feed']} | {r['games']} | {r['n']} | "
                 + " | ".join(fmt(r[q]) for q in QS) + f" | {lab} |")
    return "\n".join(L)


def render_appendix(files: list[tuple[str, str]]) -> str:
    L = ["| file | sha256 (CRLF normalised to LF) |", "|---|---|"]
    L += [f"| `{p}` | `{h}` |" for p, h in files]
    return "\n".join(L)


def replace_block(text: str, name: str, body: str) -> str:
    """Rewrite only the text between <!-- BEGIN GENERATED name --> and its END marker."""
    pat = re.compile(rf"(<!-- BEGIN GENERATED {name} -->\n).*?(<!-- END GENERATED {name} -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"marker block {name} missing")
    return pat.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text)


def build(root: Path, min_nights: int = MIN_NIGHTS) -> tuple[dict, str, str]:
    recs = load_ledgers(root)
    if not recs:
        raise SystemExit("no latency ledgers found")
    summ, stale, gaps = summarise(recs, min_nights), staleness(root), gap_nights(recs)
    files = [(p.relative_to(root).as_posix(), sha256_lf(p)) for g in (LEDGER_GLOB, M2_GLOB)
             for p in sorted(root.glob(g))]
    side = {"schema": "inplay_latency_paper_v1", "min_nights": min_nights, "gap_nights": gaps,
            "as_of": max(r["night"] for r in recs),
            "per_sport": summ, "staleness_15s": stale,
            "per_night": [{k: v for k, v in r.items() if k != "bmf_games"} for r in recs],
            "inputs": [{"path": p, "sha256_lf": h} for p, h in files]}
    return side, render_results(recs, summ, stale, gaps), render_appendix(files)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--check", action="store_true", help="exit 1 if outputs would change")
    a = ap.parse_args(argv)
    root = Path(a.repo_root).resolve()
    side, results, appendix = build(root)
    paper = root / PAPER
    old = paper.read_text(encoding="utf-8")
    new = replace_block(replace_block(old, "results", results), "appendix", appendix)
    side_txt = json.dumps(side, indent=1, sort_keys=True) + "\n"
    sc = root / SIDECAR
    if a.check:
        same = new == old and sc.exists() and sc.read_text(encoding="utf-8") == side_txt
        print("UP_TO_DATE" if same else "STALE")
        return 0 if same else 1
    paper.write_text(new, encoding="utf-8", newline="\n")
    sc.parent.mkdir(parents=True, exist_ok=True)
    sc.write_text(side_txt, encoding="utf-8", newline="\n")
    print(f"wrote {PAPER} and {SIDECAR}: {len(side['per_night'])} night-sport rows, "
          f"{len(side['inputs'])} inputs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
