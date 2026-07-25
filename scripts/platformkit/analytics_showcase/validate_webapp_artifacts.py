"""Shape-validate the artifacts the analytics webapp consumes at build time.

The webapp reads these committed JSON files with blind `as T` TypeScript casts,
so a shape drift in an artifact does not fail the build -- it renders wrong. That
is exactly how the entity-joins coverage bug shipped once ("All 0 team cards":
`coverage` is TOP-LEVEL in the artifact, but a reader looked for it under
`packs.<pack>`). This module is the guard the type system cannot be: it asserts
the real committed shape of every webapp-consumed family, and encodes the known
gotchas as explicit assertions so they can never regress silently.

Validates the STAGED copies under webapp/public/data/showcase/ -- the exact bytes
the export reads -- not the out/ originals.

Usage:
    python -m scripts.platformkit.analytics_showcase.validate_webapp_artifacts
    python -m scripts.platformkit.analytics_showcase.validate_webapp_artifacts --check
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
STAGED = os.path.join(ROOT, "webapp", "public", "data", "showcase")


def _req(d, keys, where):
    for k in keys:
        assert k in d, "%s: missing required key '%s'" % (where, k)


def _is(d, k, typ, where):
    assert isinstance(d.get(k), typ), "%s: key '%s' must be %s, got %s" % (
        where, k, typ, type(d.get(k)).__name__)


def v_entity_percentiles(d):
    _req(d, ["packs", "n_entities"], "entity_percentiles")
    _is(d, "packs", dict, "entity_percentiles")
    for pk, pv in d["packs"].items():
        _req(pv, ["n_in_pack", "entities"], "entity_percentiles.packs.%s" % pk)


def v_entity_joins(d):
    # THE gotcha: coverage is top-level and keyed by pack, NOT nested in packs.<pack>.
    _req(d, ["packs", "coverage"], "entity_joins")
    _is(d, "coverage", dict, "entity_joins")
    _is(d, "packs", dict, "entity_joins")
    assert "nba_teams" in d["coverage"], "entity_joins.coverage must be keyed by pack (nba_teams missing)"
    for pk, pv in d["packs"].items():
        assert "entities" in pv, "entity_joins.packs.%s missing 'entities'" % pk


def v_entity_comparables(d):
    _req(d, ["packs"], "entity_comparables")
    _is(d, "packs", dict, "entity_comparables")


def v_ess_ledger(d):
    _req(d, ["corpora", "headline"], "ess_ledger")
    _is(d, "corpora", list, "ess_ledger")
    assert d["corpora"], "ess_ledger.corpora is empty"
    _req(d["corpora"][0], ["sport", "n_rows", "ess_anchor", "infl_anchor"], "ess_ledger.corpora[0]")


def v_verdict_flip(d):
    _req(d, ["flips", "summary", "retracted"], "verdict_flip_anatomy")
    _is(d, "flips", list, "verdict_flip_anatomy")


def v_mlb_leaderboards(d):
    _req(d, ["catcher_ooz", "umpire_ooz", "platoon_splits", "park_factor_null",
             "umpire_totals_gate", "observation_window"], "mlb_descriptive_leaderboards")


def v_two_or_three_groups(d, where, key, n):
    _req(d, [key], where)
    _is(d, key, list, where)
    assert len(d[key]) == n, "%s.%s must have %d entries, got %d" % (where, key, n, len(d[key]))


def v_q4_shift(d):
    _req(d, ["pts_shift", "observation_window", "n_qualified"], "nba_q4_shift")
    _req(d["pts_shift"], ["top_risers"], "nba_q4_shift.pts_shift")


def v_shrinkage(d):
    v_two_or_three_groups(d, "mlb_shrinkage", "groups", 3)
    _req(d["groups"][0], ["pooled_mean", "alpha", "beta", "biggest_regressors"], "mlb_shrinkage.groups[0]")


def v_murphy(d):
    _req(d, ["sports"], "murphy_decomposition")
    _is(d, "sports", dict, "murphy_decomposition")
    assert "mlb" in d["sports"], "murphy_decomposition.sports missing mlb"
    _req(d["sports"]["mlb"], ["model_prob", "market_prob"], "murphy_decomposition.sports.mlb")


def v_search_records(d):
    _req(d, ["records", "counts"], "search_records")
    _is(d, "records", list, "search_records")
    assert d["counts"]["total"] == len(d["records"]), "search_records counts.total != len(records)"
    assert len(d["records"]) >= 1600, "search_records too small (%d)" % len(d["records"])
    for r in d["records"][:50]:
        assert r.get("href", "").startswith("/analytics"), "search_records href not /analytics: %r" % r.get("href")


VALIDATORS = {
    "entity_percentiles.json": v_entity_percentiles,
    "entity_joins.json": v_entity_joins,
    "entity_comparables.json": v_entity_comparables,
    "ess_ledger.json": v_ess_ledger,
    "verdict_flip_anatomy.json": v_verdict_flip,
    "mlb_descriptive_leaderboards.json": v_mlb_leaderboards,
    "tennis_grain_and_myths.json": lambda d: v_two_or_three_groups(d, "tennis_grain_and_myths", "stories", 3),
    "nba_momentum_tested.json": lambda d: v_two_or_three_groups(d, "nba_momentum_tested", "groups", 2),
    "nba_q4_shift.json": v_q4_shift,
    "mlb_shrinkage.json": v_shrinkage,
    "murphy_decomposition.json": v_murphy,
    "search_records.json": v_search_records,
}


def run():
    ok, missing, failed = [], [], []
    for name, fn in sorted(VALIDATORS.items()):
        p = os.path.join(STAGED, name)
        if not os.path.exists(p):
            missing.append(name)
            continue
        try:
            fn(json.loads(open(p, encoding="utf-8").read()))
            ok.append(name)
        except AssertionError as e:
            failed.append((name, str(e)))
        except (ValueError, KeyError, TypeError) as e:
            failed.append((name, "%s: %s" % (type(e).__name__, e)))
    return ok, missing, failed


def build():
    ok, missing, failed = run()
    for name in ok:
        print("  ok   %s" % name)
    for name in missing:
        print("  MISS %s (not staged)" % name)
    for name, err in failed:
        print("  FAIL %s -- %s" % (name, err))
    print("%d ok, %d missing, %d failed" % (len(ok), len(missing), len(failed)))


def check():
    ok, missing, failed = run()
    assert not failed, "artifact shape validation FAILED:\n" + "\n".join(
        "  %s -- %s" % (n, e) for n, e in failed)
    # On this box everything is staged; a clone may lack some. Require the core
    # entity layers + search index to be present and valid at minimum.
    core = {"entity_percentiles.json", "entity_joins.json", "search_records.json"}
    present = set(ok) | set(missing)
    absent_core = core - set(ok)
    assert not absent_core, "core webapp artifacts missing/invalid: %s" % sorted(absent_core)
    assert len(present) == len(VALIDATORS), "validator/file mismatch"
    print("OK (%d validated, %d absent on this checkout)" % (len(ok), len(missing)))


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        build()
