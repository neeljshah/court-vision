"""market_coverage.coverage -- the EVERY-MARKET book for a matchup, each market
priced from the joint sim and tagged with thinness + validatable honesty axes.

GIVEN a matchup, produce the FULL market book: every enumerated market priced from
ONE coherent sim (NBA) or the calibrated predictor (mlb/soccer/tennis), each tagged
with (a) THINNESS (how policed -> the obscure-market lane) and (b) VALIDATABLE (can
the price be confirmed offline at all, or only via forward CLV). This is the entry
edge_finder.py judges and the buyer-facing "what can I bet, and how trustworthy is
each price" view.

PLUMBING (all READ-ONLY of human-gated code):
  sample_book.run_nba_sim   -> src.sim.fast_sim joint Monte-Carlo OUTPUT
  book_builder.build_full_book -> enumerates+prices every market off the SampleBook
  predictor_jd._build_predictor (via _other_sport_book) -> mlb/soccer/tennis
  tags.*                    -> thinness / validatable / forward-CLV honesty
The sim PRICES every number; nothing is authored by hand.

THE 7 CATEGORIES (build contract): player-props-core, player-props-combos,
team-quarter-half, game-scenario-longshot, sgp-correlation, mlb-soccer-tennis,
ingame-micro.

HONEST RAILS: a price is a price, NOT an edge. Liquid mainlines we MATCH (record
honestly). Obscure/prop/SGP/in-game-micro are mostly FORWARD_ONLY -> priced +
calibrated now, validated only by forward capture; real $ capped by book limits.
No $/ROI claims; no fabricated survivor. The GATE (edge_finder) decides any beat,
vs the SHIN-devigged close, leak-free.

Stdlib + numpy. ASCII only. <=300 LOC. Per-file test: tests/test_coverage_book.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from scripts.platformkit.market_coverage import book_builder as BB
from scripts.platformkit.market_coverage import tags as TG
from scripts.platformkit.market_coverage.markets import SampleBook
from scripts.platformkit.market_coverage.sample_book import (
    add_period_columns, book_from_sim, run_nba_sim)

_NBA = ("nba", "basketball_nba")

# book_builder kind -> the tags.is_mainline 'kind' bucket (for thinness/validatable).
_KIND_MAP = {"single": "single", "combo": "single", "longshot": "single",
             "team": "team", "quarter": "single", "scenario": "scenario",
             "sgp": "single", "ingame": "single"}


def _prob_of(rec: Dict[str, Any]) -> float:
    """A priced record is either a single (prob) or a joint (joint)."""
    if "prob" in rec:
        return float(rec["prob"])
    return float(rec.get("joint", float("nan")))


def _tag(category: str, name: str, rec: Dict[str, Any]) -> Dict[str, Any]:
    kind = _KIND_MAP.get(rec.get("kind", "single"), "single")
    p = _prob_of(rec)
    thin = TG.thinness_for(category, name, kind, p if p == p else 0.5)
    val = TG.validatable_for(category, name, kind)
    out = dict(rec)
    out["name"] = name
    out["category"] = category
    out["prob"] = p
    out["thinness"] = thin
    out["validatable"] = val
    out["needs_forward_clv"] = TG.needs_forward_clv(val)
    out["honesty"] = TG.honesty_note(thin, val)
    return out


def _relabel(name: str, pid_name: Dict[int, str]) -> str:
    """book_builder keys columns by pid; swap leading pids -> player names for
    human-readable market names (e.g. '1628973 pts O24' -> 'Jalen Brunson pts O24')."""
    out = name
    for pid, nm in pid_name.items():
        out = out.replace(str(pid), nm)
    return out


def _degenerate(rec: Dict[str, Any]) -> bool:
    """A single/team/quarter market pinned at ~0/1 (an out-of-support line, e.g.
    'blk O-0.5' = always over) carries no information -> drop it. Joints/longshots
    legitimately live in the tail and are kept."""
    if rec.get("kind") in ("sgp",) or "joint" in rec:
        return False
    if rec.get("kind") in ("longshot", "scenario"):
        return False
    p = _prob_of(rec)
    return not (0.02 < p < 0.98)  # applies to single/team/quarter/ingame singles


def _nba_categories(book: SampleBook, ingame: bool,
                    pid_name: Optional[Dict[int, str]] = None) -> Dict[str, List[Dict]]:
    """Enumerate + price every NBA category off the coherent SampleBook, drop
    degenerate out-of-support lines, relabel pids -> names (if a map is given),
    then tag with thinness + validatable."""
    pid_name = pid_name or {}
    cats_wanted = [c for c in BB.CATEGORIES if c != "ingame-micro"]
    if ingame:
        cats_wanted = list(BB.CATEGORIES)  # include ingame-micro on a live book
    priced = BB.build_full_book(book, categories=cats_wanted)
    out: Dict[str, List[Dict]] = {c: [] for c in cats_wanted}
    for name, rec in priced.items():
        if _degenerate(rec):
            continue
        cat = rec.get("category", "player-props-core")
        out.setdefault(cat, []).append(_tag(cat, _relabel(name, pid_name), rec))
    return out


def _nba_book(home: str, away: str, n_sims: int, seed: int,
              state: Optional[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    """Run ONE sim (read-only) -> SampleBook -> every NBA category, internally
    consistent by construction. With `state`, the rest-of-game book also yields
    ingame-micro markets."""
    res = run_nba_sim(home, away, n_sims=n_sims, seed=seed, state=state)
    book, name_to_pid, team_pids = book_from_sim(res)
    book = add_period_columns(book)
    pid_name = {int(pid): str(d["name"]) for pid, d in res.players.items()}
    return _nba_categories(book, ingame=bool(state), pid_name=pid_name)


def _other_sport_book(sport: str, home: str, away: str,
                      surface: str) -> Dict[str, List[Dict]]:
    """mlb/soccer/tennis: price the markets the calibrated predictor exposes (match
    winner + the sport's headline total/derivative). HAS_CLOSE on the moneyline; no
    player-level joint sim offline. Degrades cleanly if the corpus is absent."""
    try:
        from scripts.platformkit.predictor_jd import _build_predictor
        pred = _build_predictor(sport)
    except Exception:  # noqa: BLE001 - never crash on a fresh clone
        pred = None
    if pred is None:
        return {"mlb-soccer-tennis": [{
            "name": "unavailable", "category": "mlb-soccer-tennis", "prob": float("nan"),
            "kind": "single", "thinness": "N/A", "validatable": "N/A",
            "needs_forward_clv": False, "tier": "N/A",
            "honesty": "corpus unavailable on this clone (local/gitignored); no price produced."}]}
    raw = pred.predict(home, away, surface=surface) if sport == "tennis" else pred.predict(home, away)
    rows: List[Dict] = []

    def _r(name: str, prob: float, kind: str) -> None:
        rows.append({"name": name, "prob": float(prob), "kind": kind,
                     "fair_decimal": (1.0 / prob) if prob > 1e-9 else float("inf")})

    ph = raw.get("p_home_win", raw.get("p1_match_win", raw.get("p_home")))
    if ph is not None:
        _r(f"match_winner {home}", float(ph), "side")
        if "p_draw" not in raw or raw.get("p_draw") is None:
            _r(f"match_winner {away}", 1.0 - float(ph), "side")
    if raw.get("p_draw") is not None:
        _r("draw", float(raw["p_draw"]), "side")
        _r(f"match_winner {away}", max(0.0, 1.0 - float(ph) - float(raw["p_draw"])), "side")
    if sport == "soccer" and raw.get("over_2.5") is not None:
        _r("game_total over 2.5", float(raw["over_2.5"]), "scenario")
    return {"mlb-soccer-tennis": [_tag("mlb-soccer-tennis", r["name"], r) for r in rows]}


def full_book(sport: str, home: str, away: str, n_sims: int = 8000, seed: int = 2026,
              surface: str = "Hard", state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Produce the FULL market book for a matchup across all applicable categories."""
    s = sport.lower()
    cats = _nba_book(home, away, n_sims, seed, state) if s in _NBA \
        else _other_sport_book(s, home, away, surface)
    flat = [r for rows in cats.values() for r in rows]
    return {
        "sport": s, "home": home, "away": away, "edge_claimed": False,
        "framing": ("FULL market book priced from the joint sim / calibrated predictor. "
                    "Liquid mainlines MATCH the devigged close (calibration, not edge); "
                    "obscure/prop/SGP/in-game markets are PRICED + CALIBRATED and flagged "
                    "needs-forward-CLV. No $ edge claimed; the gate decides any beat."),
        "categories": list(cats.keys()),
        "n_markets": len(flat),
        "summary": _summary(flat),
        "markets": cats,
    }


def _summary(flat: List[Dict]) -> Dict[str, Any]:
    thin: Dict[str, int] = {}
    val: Dict[str, int] = {}
    tier: Dict[str, int] = {}
    fwd = 0
    for r in flat:
        thin[r.get("thinness", "?")] = thin.get(r.get("thinness", "?"), 0) + 1
        val[r.get("validatable", "?")] = val.get(r.get("validatable", "?"), 0) + 1
        tier[r.get("tier", "?")] = tier.get(r.get("tier", "?"), 0) + 1
        if r.get("needs_forward_clv"):
            fwd += 1
    return {"by_thinness": thin, "by_validatable": val, "by_tier": tier,
            "needs_forward_clv": fwd}


def _print(book: Dict[str, Any]) -> None:
    print("=" * 90)
    print(f"FULL MARKET BOOK -- {book['away']} @ {book['home']}  [{book['sport']}, "
          f"{book['n_markets']} markets]")
    print("  thinness: LIQUID(matched) / SEMI / THIN / EXTREME(the obscure-market lane)")
    print("  validatable: HAS_CLOSE(gate now) / PRICE_ONLY / FORWARD_ONLY(needs forward CLV)")
    print("=" * 90)
    for cat, rows in book["markets"].items():
        if not rows:
            continue
        print(f"\n[{cat}]  ({len(rows)} markets)")
        ranked = sorted(rows, key=lambda x: -(x["prob"] if x["prob"] == x["prob"] else -1.0))
        for r in ranked[:14]:
            p = r["prob"]
            ps = "  nan" if p != p else f"{p*100:5.1f}%"
            lift = r.get("lift")
            extra = f"  lift x{lift:.2f}" if isinstance(lift, (int, float)) else ""
            fwd = " [fwd-CLV]" if r.get("needs_forward_clv") else ""
            print(f"   {r['name'][:34]:34s} {ps}  {r['thinness']:7s} "
                  f"{r['validatable']:12s}{fwd}{extra}")
        if len(rows) > 14:
            print(f"   ... +{len(rows) - 14} more")
    s = book["summary"]
    print("\nSUMMARY")
    print(f"   markets: {book['n_markets']}  | thinness {s['by_thinness']}")
    print(f"   validatable {s['by_validatable']}  | needs_forward_clv {s['needs_forward_clv']}")
    print("   * LIQUID/HAS_CLOSE = mainlines we MATCH (calibration, not edge).")
    print("   * EXTREME/FORWARD_ONLY = the obscure-market lane: priced+calibrated, SUGGESTIVE,")
    print("     needs forward CLV; $ capped by book limits. No edge claimed here; gate decides.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Full per-matchup market book with thinness/validatable tags")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--nsims", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--surface", default="Hard")
    ap.add_argument("--state", default="", help="JSON live-state file -> adds ingame-micro (NBA)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the table")
    ap.add_argument("--out", default="", help="write JSON book to this path (gitignored data/)")
    a = ap.parse_args(argv)

    state = None
    if a.state and os.path.exists(a.state):
        state = json.load(open(a.state, encoding="utf-8"))
    book = full_book(a.sport, a.home, a.away, n_sims=a.nsims, seed=a.seed,
                     surface=a.surface, state=state)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(book, fh, indent=2, default=float)
        print(f"wrote {a.out}  ({book['n_markets']} markets)")
    elif a.json:
        print(json.dumps(book, indent=2, default=float))
    else:
        _print(book)
    return 0


if __name__ == "__main__":
    sys.exit(main())
