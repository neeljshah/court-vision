"""Aggregator -- one index over every novel_* showcase stat.

Reads each out/novel_*.json (except itself), pulls its self-describing
"index_card" (falling back to top-level keys), and writes a single
out/novel_stats_index.json the website renders. Composition only -- computes
no new numbers; every card is copied from its module's own output.

edge_claimed=False on every card, always. A module missing from disk is
recorded as a skip, never silently dropped.

Usage:
    python -m scripts.platformkit.analytics_showcase.novel_stats_index
    python -m scripts.platformkit.analytics_showcase.novel_stats_index --check
"""
import glob
import json
import os
from datetime import datetime, timezone

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
OUT_DIR = os.path.join(SHOWCASE, "out")
OUT_JSON = os.path.join(OUT_DIR, "novel_stats_index.json")
SELF_NAME = "novel_stats_index.json"


def _sources():
    return [p for p in sorted(glob.glob(os.path.join(OUT_DIR, "novel_*.json")))
            if os.path.basename(p) != SELF_NAME]


def _card_from(path):
    """Prefer the module's own index_card; else synthesize from top-level keys."""
    d = json.loads(open(path, encoding="utf-8").read())
    card = d.get("index_card")
    if not isinstance(card, dict):
        card = {
            "stat_name": d.get("stat_name"),
            "abbrev": d.get("abbrev"),
            "module": os.path.splitext(os.path.basename(path))[0],
            "formula": d.get("formula"),
            "prior_art_verdict": d.get("prior_art_verdict"),
            "headline": d.get("headline"),
            "source_artifacts": d.get("source_artifacts"),
            "n_results": len(d.get("results", [])) if isinstance(d.get("results"), (list, dict)) else None,
        }
    card = dict(card)
    card["edge_claimed"] = False  # never trust a card to claim otherwise
    card["artifact"] = os.path.relpath(path, ROOT).replace("\\", "/")
    card["is_honest_null"] = bool(d.get("is_honest_null"))
    return card


def build():
    cards, skipped = [], []
    for path in _sources():
        try:
            cards.append(_card_from(path))
        except Exception as e:  # malformed artifact -> record, never crash the index
            skipped.append({"artifact": os.path.relpath(path, ROOT).replace("\\", "/"), "reason": str(e)})
    payload = {
        "edge_claimed": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "composition only -- each card copied from its module's own novel_*.json output",
        "n_stats": len(cards),
        "stats": cards,
        "skipped": skipped,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _validate(d):
    assert d["edge_claimed"] is False
    assert d["stats"], "index has no stats"
    for c in d["stats"]:
        assert c["edge_claimed"] is False
        assert c.get("stat_name") and c.get("module")


def check():
    if not _sources():
        verify_recorded_artifact(OUT_JSON, _validate, "novel_stats_index")
        return
    payload = build()
    _validate(payload)
    print(f"OK: novel_stats_index ({payload['n_stats']} stats: "
          f"{', '.join(c['module'] for c in payload['stats'])}; {len(payload['skipped'])} skipped)")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        print(json.dumps({"n_stats": p["n_stats"],
                          "stats": [{"stat_name": c["stat_name"], "abbrev": c["abbrev"],
                                     "prior_art_verdict": c["prior_art_verdict"]} for c in p["stats"]],
                          "skipped": p["skipped"]}, indent=2))
