"""Meta-analytics over the fact-claims corpus (data/cache/intel_claims/).

Per-family claim counts, verified-sample stats from *_validation.json sidecars,
sport breakdown, verdict-kind distribution, index freshness. Degrades honestly
(status + paths_tried) if the corpus dir is missing.

Output: out/claims_corpus_meta.json + docs/img/claims_corpus_meta.png
"""
import glob
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT_JSON = os.path.join(HERE, "out", "claims_corpus_meta.json")
OUT_PNG = os.path.join(REPO, "docs", "img", "claims_corpus_meta.png")

# ponytail: non-claim ledger files that share the .jsonl extension but are not
# per-family claim stores -- excluded from family accounting explicitly.
NON_FAMILY_FILES = {"claim_weights.jsonl", "false_discovery_ledger.jsonl"}

SPORT_PREFIXES = [
    ("nba_", "nba"), ("wnba_", "wnba"), ("mlb_", "mlb"), ("soccer_", "soccer"),
    ("tennis_", "tennis"), ("npb_", "npb_kbo"), ("kbo_", "npb_kbo"),
    ("umpire_", "mlb"), ("catcher_", "mlb"), ("baseball_intl", "baseball_intl"),
    ("cross_sport", "cross_sport"),
]


def infer_sport(filename):
    for prefix, sport in SPORT_PREFIXES:
        if filename.startswith(prefix):
            return sport
    return "unlabeled_cross_sport"  # market/gate/ingame/shooter/prereg/interaction/platoon ledgers


def count_lines(path):
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def find_corpus_dir():
    tried = []
    for rel in ("data/cache/intel_claims",):
        p = os.path.join(REPO, rel)
        tried.append(p)
        if os.path.isdir(p):
            return p, tried
    return None, tried


def build():
    corpus_dir, paths_tried = find_corpus_dir()
    if corpus_dir is None:
        return {
            "component": "claims_corpus_meta",
            "status": "no_data",
            "paths_tried": paths_tried,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    all_jsonl = sorted(glob.glob(os.path.join(corpus_dir, "*.jsonl")))
    family_files = [
        p for p in all_jsonl
        if not p.endswith(".index.jsonl") and os.path.basename(p) not in NON_FAMILY_FILES
    ]

    families = []
    kind_dist = Counter()
    sport_claims = defaultdict(int)
    sport_families = defaultdict(int)
    total_claims = 0
    total_verified = 0
    total_mismatch = 0
    total_unverifiable = 0
    families_with_sidecar = 0

    for path in family_files:
        fname = os.path.basename(path)
        family = fname[:-len(".jsonl")]
        n_claims = count_lines(path)
        total_claims += n_claims
        sport = infer_sport(fname)
        sport_claims[sport] += n_claims
        sport_families[sport] += 1
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)

        # sample first line's "kind" as representative verdict-kind for the family
        kind = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                first = f.readline()
            if first.strip():
                kind = json.loads(first).get("kind")
        except (OSError, json.JSONDecodeError):
            pass
        if kind:
            kind_dist[kind] += n_claims

        sidecar = os.path.join(corpus_dir, family + "_validation.json")
        validation = None
        if os.path.isfile(sidecar):
            families_with_sidecar += 1
            try:
                vd = json.load(open(sidecar, "r", encoding="utf-8"))
                validation = {
                    "n_claims": vd.get("n_claims"),
                    "n_verified": vd.get("n_verified"),
                    "n_mismatch": vd.get("n_mismatch"),
                    "n_unverifiable": vd.get("n_unverifiable"),
                    "edge_claimed": vd.get("edge_claimed"),
                    "generated_at": vd.get("generated_at"),
                }
                total_verified += vd.get("n_verified") or 0
                total_mismatch += vd.get("n_mismatch") or 0
                total_unverifiable += vd.get("n_unverifiable") or 0
            except (OSError, json.JSONDecodeError):
                validation = {"status": "sidecar_unreadable"}

        families.append({
            "family": family,
            "sport": sport,
            "n_claims": n_claims,
            "kind_sample": kind,
            "mtime": mtime.isoformat(),
            "has_validation_sidecar": os.path.isfile(sidecar),
            "validation": validation,
        })

    families.sort(key=lambda r: r["n_claims"], reverse=True)
    mtimes = [datetime.fromisoformat(r["mtime"]) for r in families]
    now = datetime.now(timezone.utc)

    # the packet rule: "verified" must never silently mean "generated" --
    # report the generated-vs-validated split as first-class numbers.
    n_validated_sample = total_verified + total_mismatch + total_unverifiable
    result = {
        "component": "claims_corpus_meta",
        "status": "ok",
        "generated_at": now.isoformat(),
        "corpus_dir": os.path.relpath(corpus_dir, REPO).replace("\\", "/"),
        "totals": {
            "n_families": len(families),
            "n_claims_generated": total_claims,
            "n_families_with_validation_sidecar": families_with_sidecar,
            "n_families_without_validation_sidecar": len(families) - families_with_sidecar,
        },
        "generated_vs_validated": {
            "n_claims_generated": total_claims,
            "n_claims_sampled_for_validation": n_validated_sample,
            "n_verified": total_verified,
            "n_mismatch": total_mismatch,
            "n_unverifiable": total_unverifiable,
            "pct_of_generated_claims_covered_by_a_validation_sample": (
                round(100.0 * n_validated_sample / total_claims, 2) if total_claims else None
            ),
            "note": "verified counts are sidecar SAMPLE counts, not full-corpus audits; "
                    "'generated' claims outnumber 'verified' claims by design -- see JOB_EVIDENCE_PACKET.md",
        },
        "sport_breakdown": [
            {"sport": s, "n_families": sport_families[s], "n_claims": sport_claims[s]}
            for s in sorted(sport_claims, key=lambda s: sport_claims[s], reverse=True)
        ],
        "kind_distribution_by_claim_count": dict(kind_dist.most_common()),
        "index_freshness": {
            "oldest_family_mtime": min(mtimes).isoformat() if mtimes else None,
            "newest_family_mtime": max(mtimes).isoformat() if mtimes else None,
            "days_since_newest_update": (now - max(mtimes)).days if mtimes else None,
        },
        "families": families,
    }
    return result


def render_png(result, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fams = result["families"][:20]
    fams = fams[::-1]  # largest at top in barh
    names = [f["family"] for f in fams]
    generated = [f["n_claims"] for f in fams]
    verified = [
        (f["validation"]["n_verified"] if f["validation"] and f["validation"].get("n_verified") else 0)
        for f in fams
    ]

    fig, ax = plt.subplots(figsize=(10, 8))
    y = range(len(names))
    ax.barh(y, generated, color="#c9c9c9", label="generated (claim count)")
    ax.barh(y, verified, color="#2b7a78", label="verified (validation sample)")
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=7)
    ax.set_xlabel("claim count")
    ax.set_title("Fact-claims corpus: top 20 families, generated vs. verified-sample")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    result = build()
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    if result["status"] == "ok":
        render_png(result, OUT_PNG)
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_PNG}")
        t = result["totals"]
        gv = result["generated_vs_validated"]
        print(f"families={t['n_families']} claims_generated={t['n_claims_generated']} "
              f"families_with_sidecar={t['n_families_with_validation_sidecar']}")
        print(f"validated_sample={gv['n_claims_sampled_for_validation']} "
              f"verified={gv['n_verified']} mismatch={gv['n_mismatch']} "
              f"unverifiable={gv['n_unverifiable']} "
              f"pct_covered={gv['pct_of_generated_claims_covered_by_a_validation_sample']}")
    else:
        print(f"status=no_data paths_tried={result['paths_tried']}")
        print(f"wrote {OUT_JSON}")


def check():
    assert os.path.exists(OUT_JSON) and os.path.getsize(OUT_JSON) > 0, OUT_JSON
    assert os.path.exists(OUT_PNG) and os.path.getsize(OUT_PNG) > 0, OUT_PNG
    print("OK: claims_corpus_meta self-check passed")


if __name__ == "__main__":
    import sys
    check() if "--check" in sys.argv else main()
