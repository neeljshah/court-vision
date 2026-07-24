"""Joins already-committed NBA module artifacts onto the atlas entity cards
they never reached.

Reads ONLY files already in scripts/platformkit/analytics_showcase/out/.
Zero new science, zero new data -- pure composition: for each atlas entity
(30 nba_teams, 482 nba_players) pulls in the rows/badges from the six NBA
module artifacts keyed on that same entity. on_off_showcase.json is dropped
(no per-entity rows to join).

Usage:
    python -m scripts.platformkit.analytics_showcase.entity_joins
    python -m scripts.platformkit.analytics_showcase.entity_joins --check
"""
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
OUT_DIR = os.path.join(SHOWCASE, "out")
OUT_JSON = os.path.join(OUT_DIR, "entity_joins.json")

# slug -> manifest filename. Slugs are BINDING -- must match the webapp
# route param [pack] exactly. Only these two packs are in scope here.
PACKS = {
    "nba_teams": "atlas_nba_teams_manifest.json",
    "nba_players": "atlas_nba_manifest.json",
}

METHOD = (
    "Joins of already-committed module artifacts in "
    "scripts/platformkit/analytics_showcase/out/ onto the atlas entity cards "
    "they key on; no new computation, no new data."
)

def _src(fn):
    return f"scripts/platformkit/analytics_showcase/out/{fn}"

def _load(fn):
    return json.loads(open(os.path.join(OUT_DIR, fn), encoding="utf-8").read())

def _slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")

def _entity_slug(entry, seen):
    """Must byte-match webapp/app/(analytics)/analytics/players/[pack]/[slug]/page.tsx:
    slug = basename of card_path, trailing .ext stripped; on collision with a
    prior slug in this pack, fall back to slugify(entity).
    """
    base = re.split(r"[/\\]", entry.get("card_path") or "")[-1]
    stem = os.path.splitext(base)[0]
    slug = stem if stem not in seen else _slugify(entry.get("entity"))
    seen.add(slug)
    return slug

def _slug_map(entries, key_fn):
    seen = set()
    return {key_fn(e): _entity_slug(e, seen) for e in entries}


# --------------------------- team joins ---------------------------

def _join_sft(slug_by_code):
    fn = "novel_schedule_fatigue_tax.json"
    d = _load(fn)
    confound = "; ".join(d["declared_confounds"])
    latest = {}
    for row in d["results"]:
        prev = latest.get(row["team"])
        if prev is None or row["season"] > prev["season"]:
            latest[row["team"]] = row
    items = {}
    for team, row in latest.items():
        items[slug_by_code[team]] = {
            "key": "schedule_fatigue_tax",
            "label": "Schedule Fatigue Tax (latest season)",
            "value": f"{row['sft_credible_pts_per100_ortg']:+.4f} pts/100 ORtg ({row['season']})",
            "detail": (f"b2b_freq={row['b2b_freq']}, b2b_games={row['b2b_games']}, "
                       f"descriptive composite/36={row['sft_descriptive_composite_per36']:+.4f}"),
            "source_artifact": _src(fn), "confound": confound,
        }
    return items

def _join_lbi(slug_by_code):
    fn = "novel_load_bearing_index.json"
    d = _load(fn)
    confound = "; ".join(d["declared_confounds"]) + "; " + d["metric_definition"]
    items = {}
    for row in d["results"]:
        a, b = row["estimator_a_elo_onoff"], row["estimator_b_raw_withwithout"]
        items[slug_by_code[row["team"]]] = {
            "key": "load_bearing_index",
            "label": "Load-Bearing Index (most-indispensable player)",
            "value": (f"Elo on/off: {a['player_name']} (delta_winprob {a['delta_winprob']:+.4f}); "
                      f"raw with/without: {b['player_name']} (delta_win_rate {b['delta_win_rate']:+.4f}); "
                      f"agreement={row['agreement_same_player']}"),
            "detail": (f"on/off net rating delta {a['on_off_net_rating_delta']:+.3f}; "
                      f"n_active={b['n_active']}, n_missed={b['n_missed']}"),
            "source_artifact": _src(fn), "confound": confound,
        }
    return items

def _join_matchup_extremes(slug_by_code):
    fn = "nba_matchup_grid.json"
    d = _load(fn)
    confound = "; ".join(d["methodology"]["not_this"]) + f"; {d['mask']['rule']}"
    by_team = {}
    for row in d["pairings"]:
        for team, opp in ((row["row"], row["col"]), (row["col"], row["row"])):
            cur = by_team.setdefault(team, {"high": None, "low": None})
            cand = {"opponent": opp, "mean_total": row["mean_total"], "n_meetings": row["n_meetings"]}
            if cur["high"] is None or cand["mean_total"] > cur["high"]["mean_total"]:
                cur["high"] = cand
            if cur["low"] is None or cand["mean_total"] < cur["low"]["mean_total"]:
                cur["low"] = cand
    items = {}
    for team, ex in by_team.items():
        h, low = ex["high"], ex["low"]
        items[slug_by_code[team]] = {
            "key": "matchup_grid_extremes",
            "label": "Highest/lowest scoring pairing (pooled 2023-24..2025-26)",
            "value": (f"highest: vs {h['opponent']} mean_total {h['mean_total']} (n={h['n_meetings']}); "
                      f"lowest: vs {low['opponent']} mean_total {low['mean_total']} (n={low['n_meetings']})"),
            "source_artifact": _src(fn), "confound": confound,
        }
    return items


# --------------------------- player joins ---------------------------

def _join_lineup_proxy(slug_by_id):
    fn = "ctx_lineup_proxy.json"
    items = {}
    for row in _load(fn)["players"]:
        slug = slug_by_id.get(row["player_id"])
        if slug is None:
            continue
        items[slug] = {
            "key": "ctx_lineup_proxy",
            "label": "Team win rate with/without this player",
            "value": (f"{row['team']}: active {row['win_rate_active']:.4f} vs missed "
                      f"{row['win_rate_missed']:.4f} (delta {row['delta_win_rate']:+.4f})"),
            "detail": f"n_active={row['n_active']}, n_missed={row['n_missed']}, ci95_offset={row['ci95_offset']}",
            "source_artifact": _src(fn), "confound": row["confound"],
        }
    return items

def _join_badges(fn, lists, key, label_prefix, slug_by_name, value_fn, detail_fn):
    """Shared shape for the three top-N leaderboard artifacts: a player either
    appears (gets a rank/standing badge) or does not (majority, no item)."""
    d = _load(fn)
    confound = "; ".join(d["not_this"])
    items = {}
    for list_name in lists:
        for i, row in enumerate(d[list_name], start=1):
            slug = slug_by_name.get(row["player_name"])
            if slug is None:
                continue
            items[slug] = {
                "key": key,
                "label": f"{label_prefix} -- {list_name} #{i}",
                "value": value_fn(row), "detail": detail_fn(row),
                "source_artifact": _src(fn), "confound": confound,
            }
    return items

def _join_box_value_badges(slug_by_name):
    fn = "box_value_index.json"
    d = _load(fn)
    confound = "; ".join(d["not_this"])
    items = {}
    for row in d["top_30"]:
        slug = slug_by_name.get(row["player_name"])
        if slug is None:
            continue
        items[slug] = {
            "key": "box_value_badge",
            "label": f"Box Value Index -- top_30 #{row['rank']}",
            "value": f"box_value_index_per36={row['box_value_index_per36']}",
            "detail": f"games={row['games']}",
            "source_artifact": _src(fn), "confound": confound,
        }
    return items


# --------------------------- assembly ---------------------------

def build():
    team_entries = _load(PACKS["nba_teams"])["entries"]
    player_entries = _load(PACKS["nba_players"])["entries"]
    slug_by_code = _slug_map(team_entries, lambda e: e["entity"])
    slug_by_id = _slug_map(player_entries, lambda e: e["key_numbers"]["player_id"])
    slug_by_name = _slug_map(player_entries, lambda e: e["entity"])

    team_joins = [_join_sft(slug_by_code), _join_lbi(slug_by_code), _join_matchup_extremes(slug_by_code)]
    player_joins = [
        _join_lineup_proxy(slug_by_id),
        _join_badges("nba_consistency_profiles.json", ["most_consistent_top15", "least_consistent_top15"],
                     "consistency_badge", "Consistency profile", slug_by_name,
                     lambda r: f"composite_cv_shrunk={r['composite_cv_shrunk']}", lambda r: f"games={r['games']}"),
        _join_badges("nba_form_curves.json", ["top_movers_risers", "top_movers_fallers"],
                     "form_curve_badge", "Form curve mover", slug_by_name,
                     lambda r: f"delta={r['delta']:+.3f}", lambda r: f"n_qual_games={r['n_qual_games']}"),
        _join_box_value_badges(slug_by_name),
    ]

    team_entities = {slug: {"items": [src[slug] for src in team_joins if slug in src]}
                     for slug in slug_by_code.values()}
    team_entities = {s: v for s, v in team_entities.items() if v["items"]}
    player_entities = {slug: {"items": [src[slug] for src in player_joins if slug in src]}
                        for slug in set(slug_by_id.values())}
    player_entities = {s: v for s, v in player_entities.items() if v["items"]}

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "method": METHOD,
        "coverage": {
            "nba_teams": {
                "n_in_pack": len(team_entries),
                "schedule_fatigue_tax": len(team_joins[0]),
                "load_bearing_index": len(team_joins[1]),
                "matchup_grid_extremes": len(team_joins[2]),
            },
            "nba_players": {
                "n_in_pack": len(player_entries),
                "with_without": len(player_joins[0]),
                "consistency_badge": len(player_joins[1]),
                "form_badge": len(player_joins[2]),
                "box_value_badge": len(player_joins[3]),
            },
        },
        "dropped": [{
            "artifact": "on_off_showcase.json",
            "reason": ("carries only season-level distribution stats "
                       "(seasons.<season>.distribution), no per-entity rows -- "
                       "nothing to join onto an atlas card."),
        }],
        "packs": {
            "nba_teams": {"entities": team_entities},
            "nba_players": {"entities": player_entities},
        },
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload

def _print_summary(payload):
    print("entity_joins:")
    t = payload["coverage"]["nba_teams"]
    print(f"  nba_teams n_in_pack={t['n_in_pack']} schedule_fatigue_tax={t['schedule_fatigue_tax']} "
          f"load_bearing_index={t['load_bearing_index']} matchup_grid_extremes={t['matchup_grid_extremes']}")
    p = payload["coverage"]["nba_players"]
    print(f"  nba_players n_in_pack={p['n_in_pack']} with_without={p['with_without']} "
          f"consistency_badge={p['consistency_badge']} form_badge={p['form_badge']} "
          f"box_value_badge={p['box_value_badge']}")
    print(f"  dropped: {[d['artifact'] for d in payload['dropped']]}")

def check():
    assert os.path.exists(OUT_JSON), f"missing {OUT_JSON}"
    payload = json.loads(open(OUT_JSON, encoding="utf-8").read())

    t = payload["coverage"]["nba_teams"]
    assert t["n_in_pack"] == 30, t["n_in_pack"]
    assert t["schedule_fatigue_tax"] == 30, t["schedule_fatigue_tax"]
    assert t["load_bearing_index"] == 30, t["load_bearing_index"]
    assert t["matchup_grid_extremes"] == 30, t["matchup_grid_extremes"]

    p = payload["coverage"]["nba_players"]
    assert p["n_in_pack"] == 482, p["n_in_pack"]
    assert p["with_without"] == 330, p["with_without"]
    assert p["consistency_badge"] >= 20, p["consistency_badge"]
    assert p["form_badge"] >= 20, p["form_badge"]
    assert p["box_value_badge"] >= 20, p["box_value_badge"]

    manifests = {slug: _load(fn)["entries"] for slug, fn in PACKS.items()}
    for pack_slug, pack in payload["packs"].items():
        valid_slugs = set(_slug_map(manifests[pack_slug], lambda e: e["entity"]).values())
        for ent_slug, body in pack["entities"].items():
            assert ent_slug in valid_slugs, f"{pack_slug}: unknown entity slug {ent_slug!r}"
            for item in body["items"]:
                assert item.get("confound"), f"{pack_slug}.{ent_slug}: empty confound in {item.get('key')}"
                src_path = os.path.join(ROOT, item["source_artifact"].replace("/", os.sep))
                assert os.path.exists(src_path), f"{pack_slug}.{ent_slug}: missing {item['source_artifact']}"

    assert len(payload["dropped"]) == 1 and payload["dropped"][0]["artifact"] == "on_off_showcase.json"
    print("OK")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        _print_summary(build())
