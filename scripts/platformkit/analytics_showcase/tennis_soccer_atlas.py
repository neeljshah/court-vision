"""tennis_soccer_atlas.py -- per-entity DESCRIPTIVE cards straight off two
VERIFIED intel_claims ranking-claim families (read-only, no parquet touched):
  tennis: data/cache/intel_claims/tennis_surface_context_claims.jsonl (ATP
          only -- no WTA claim in this store; 5 metrics x 2 windows:
          {hard,clay,grass}_wr, clay_minus_hard gap, grass_adapt, each x
          {career, recent_form}, each independently floored per its own
          criteria.min_sample)
  soccer: data/cache/intel_claims/soccer_team_form_asof_claims.jsonl (11
          metrics, one window=trailing10_asof_corpus_end, pooled across 6
          divisions 2015-2026, full population -- 0 excluded below floor)

Population = union of entities appearing in ANY metric's ranking (a player/
team only needs to clear ONE metric's own floor to earn a card). A metric
an entity does NOT clear renders as an explicit "n/a" bar and is counted in
that entity's manifest `status` -- never fabricated, never silently
dropped. Floors printed on every card come straight from each claim's own
criteria.min_sample, not retuned or hardcoded here. Per-entity sample sizes
(clay_n, hard_n, n_prior, ...) live in the claim store itself if a deeper
per-number audit is needed -- not duplicated into key_numbers here.

DESCRIPTIVE_ONLY, no edge/ROI/$ claim -- see docs/JOB_EVIDENCE_PACKET.md.

Output: docs/img/atlas/{tennis,soccer}/<slug>.png
        out/atlas_{tennis,soccer}_manifest.json
Usage:
    python -m scripts.platformkit.analytics_showcase.tennis_soccer_atlas          # full build (ONE process, minutes for hundreds of cards)
    python -m scripts.platformkit.analytics_showcase.tennis_soccer_atlas --check  # fast: manifest count == disk PNGs + spot-open 2 cards/sport
"""
import json
from pathlib import Path

try:
    from scripts.platformkit.analytics_showcase.atlas_factory import (
        card_figure, write_manifest, slugify, card_path, resolve_card_path, REPO_ROOT, OUT_DIR)
except ImportError:
    from atlas_factory import card_figure, write_manifest, slugify, card_path, resolve_card_path, REPO_ROOT, OUT_DIR

STORE_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
TENNIS_FAMILY = "tennis_surface_context_claims"
SOCCER_FAMILY = "soccer_team_form_asof_claims"
SPORT_TENNIS, SPORT_SOCCER = "tennis", "soccer"
CARD_DIR_TENNIS = REPO_ROOT / "docs" / "img" / "atlas" / SPORT_TENNIS
CARD_DIR_SOCCER = REPO_ROOT / "docs" / "img" / "atlas" / SPORT_SOCCER
TENNIS_SOURCE = f"data/cache/intel_claims/{TENNIS_FAMILY}.jsonl"
SOCCER_SOURCE = f"data/cache/intel_claims/{SOCCER_FAMILY}.jsonl"
_COLORS = ["#1f77b4", "#d9a021", "#2a9d5c", "#c0392b"]
# short on-card footer (a long per-metric string overlaps the badge) -- full detail -> manifest "floors"
FLOOR_CARD_NOTE = "per-metric min_sample (store's own floors -- see manifest); below floor -> n/a"

TENNIS_SURFACE_METRICS = ("hard_wr", "clay_wr", "grass_wr")
TENNIS_SURFACE_LABELS = ("Hard", "Clay", "Grass")
TENNIS_METRIC_ORDER = TENNIS_SURFACE_METRICS + ("clay_minus_hard", "grass_adapt")

SOCCER_PPG_METRICS, SOCCER_PPG_LABELS = ("ppg_l10", "ppg_home_l10", "ppg_away_l10"), ("all", "home", "away")
SOCCER_GOALS_METRICS, SOCCER_GOALS_LABELS = ("gf_l10", "ga_l10", "gd_l10"), ("GF", "GA", "GD")
SOCCER_RATE_METRICS, SOCCER_RATE_LABELS = ("winrate_l10", "clean_sheet_rate_l10"), ("Win%", "CS%")
SOCCER_CS_METRICS = ("clean_sheet_rate_season", "clean_sheet_rate_home", "clean_sheet_rate_away")
SOCCER_CS_LABELS = ("season", "home", "away")
SOCCER_METRIC_ORDER = SOCCER_PPG_METRICS + SOCCER_GOALS_METRICS + SOCCER_RATE_METRICS + SOCCER_CS_METRICS


def _read_family(stem: str) -> list:
    """Read every line of a *_claims.jsonl ranking-claim family, read-only:
    {claim_id, criteria:{metric,window,min_sample,...}, ranking:[{...}], computed_at, ...}."""
    path = STORE_DIR / f"{stem}.jsonl"
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            assert "criteria" in rec and "ranking" in rec, f"{stem}: unexpected claim shape {sorted(rec)}"
            records.append(rec)
    assert records, f"{stem}: claim store is empty at {path}"
    return records


def _pivot(records: list, id_field: str, name_field: str = None) -> tuple:
    """{(window,metric): {entity_id: value}}, {metric: floor_label}, {entity_id: name}.
    A (window,metric) claimed twice (tennis's asc/desc gap pair, same ranking) de-dupes: first wins."""
    values, floor_of, names = {}, {}, {}
    for rec in records:
        crit = rec["criteria"]
        window, metric = crit["window"], crit["metric"]
        label = " & ".join(f"{k}>={v}" for k, v in sorted(crit["min_sample"].items()))
        assert floor_of.setdefault(metric, label) == label, (
            f"floor drift for {metric}: {floor_of[metric]!r} vs {label!r}")
        key = (window, metric)
        if key in values:
            continue
        vals = {}
        for row in rec["ranking"]:
            eid = row[id_field]
            vals[eid] = row["value"]
            names.setdefault(eid, row[name_field] if name_field else eid)
        values[key] = vals
    return values, floor_of, names


def _population(values: dict) -> list:
    return sorted(set().union(*values.values()))


def _bar_panel_pct(ax, labels, fracs) -> None:
    """fracs: list of float-in-[0,1]-or-None -> % bars, y fixed 0-100, 'n/a' where None."""
    heights = [f * 100 if f is not None else 0.0 for f in fracs]
    bars = ax.bar(labels, heights, color=_COLORS[:len(labels)])
    ax.set_ylim(0, 100)
    for b, f, h in zip(bars, fracs, heights):
        ax.text(b.get_x() + b.get_width() / 2, h + 3, "n/a" if f is None else f"{h:.0f}",
                 ha="center", va="bottom", fontsize=4.5)
    ax.tick_params(axis="x", labelsize=5)


def _bar_panel_signed(ax, labels, vals, fmt: str = "{:+.1f}") -> None:
    """vals: float-or-None on display scale -> bars symmetric around 0 (handles
    negatives like grass_adapt/goal-diff), 'n/a' where None."""
    heights = [v if v is not None else 0.0 for v in vals]
    bars = ax.bar(labels, heights, color=_COLORS[:len(labels)])
    ax.axhline(0, color="#888888", lw=0.6)
    span = max([abs(h) for h in heights] + [1.0]) * 1.3
    ax.set_ylim(-span, span)
    for b, v, h in zip(bars, vals, heights):
        ax.text(b.get_x() + b.get_width() / 2, h, "n/a" if v is None else fmt.format(h),
                 ha="center", va="bottom" if h >= 0 else "top", fontsize=4.5)
    ax.tick_params(axis="x", labelsize=5)


def build_tennis_cards(records: list) -> tuple:
    values, floor_of, names = _pivot(records, "player_id", "player_name")
    population = _population(values)
    floor_label = (" | ".join(f"{m}: {floor_of[m]}" for m in TENNIS_METRIC_ORDER if m in floor_of)
                   + " (per metric, career+recent_form independently; below floor shows n/a)")
    as_of = max(rec["computed_at"] for rec in records)

    def get(window, metric, eid):
        return values.get((window, metric), {}).get(eid)

    entries = []
    for pid in population:
        title = f"{names[pid]} (ATP)"
        career = [get("career", m, pid) for m in TENNIS_SURFACE_METRICS]
        recent = [get("recent_form", m, pid) for m in TENNIS_SURFACE_METRICS]
        gap = [get("career", "clay_minus_hard", pid), get("recent_form", "clay_minus_hard", pid)]
        adapt = [get("career", "grass_adapt", pid), get("recent_form", "grass_adapt", pid)]
        gap_pp = [None if v is None else v * 100 for v in gap]
        adapt_pp = [None if v is None else v * 100 for v in adapt]

        def render_career(ax, v=career):
            _bar_panel_pct(ax, TENNIS_SURFACE_LABELS, v)

        def render_recent(ax, v=recent):
            _bar_panel_pct(ax, TENNIS_SURFACE_LABELS, v)

        def render_gap(ax, v=gap_pp):
            _bar_panel_signed(ax, ("career", "recent"), v, fmt="{:+.0f}")

        def render_adapt(ax, v=adapt_pp):
            _bar_panel_signed(ax, ("career", "recent"), v, fmt="{:+.0f}")

        result = card_figure(
            title=title,
            panels=[("career surf win%", render_career), ("recent surf win%", render_recent),
                    ("clay-hard gap (pp)", render_gap), ("grass adapt (pp)", render_adapt)],
            source_artifact=TENNIS_SOURCE, floors=FLOOR_CARD_NOTE, as_of=as_of,
            out_path=card_path(SPORT_TENNIS, title),
        )

        present = career + recent + gap + adapt
        n_present = sum(v is not None for v in present)
        entries.append({
            "entity": title,
            "card_path": result["path"],
            "key_numbers": {
                "player_id": int(pid),
                "hard_wr_career": career[0], "clay_wr_career": career[1], "grass_wr_career": career[2],
                "hard_wr_recent": recent[0], "clay_wr_recent": recent[1], "grass_wr_recent": recent[2],
                "clay_minus_hard_career": gap[0], "clay_minus_hard_recent": gap[1],
                "grass_adapt_career": adapt[0], "grass_adapt_recent": adapt[1],
            },
            "floors": floor_label,
            "as_of": as_of,
            "status": "complete" if n_present == len(present) else f"partial ({n_present}/{len(present)} metrics)",
        })

    return entries, floor_label


def build_soccer_cards(records: list) -> tuple:
    values, floor_of, _names = _pivot(records, "team")
    windows = {rec["criteria"]["window"] for rec in records}
    assert len(windows) == 1, f"soccer_team_form_asof: expected one window, got {windows}"
    window = next(iter(windows))
    population = _population(values)
    floor_label = (" | ".join(f"{m}: {floor_of[m]}" for m in SOCCER_METRIC_ORDER if m in floor_of)
                   + f" (window={window}; a metric a team doesn't clear shows n/a, never fabricated)")
    as_of = max(rec["computed_at"] for rec in records)

    def get(metric, team):
        return values.get((window, metric), {}).get(team)

    entries = []
    for team in population:
        ppg = [get(m, team) for m in SOCCER_PPG_METRICS]
        goals = [get(m, team) for m in SOCCER_GOALS_METRICS]
        rates = [get(m, team) for m in SOCCER_RATE_METRICS]
        cs = [get(m, team) for m in SOCCER_CS_METRICS]

        def render_ppg(ax, v=ppg):
            _bar_panel_signed(ax, SOCCER_PPG_LABELS, v, fmt="{:.2f}")

        def render_goals(ax, v=goals):
            _bar_panel_signed(ax, SOCCER_GOALS_LABELS, v, fmt="{:+.2f}")

        def render_rates(ax, v=rates):
            _bar_panel_pct(ax, SOCCER_RATE_LABELS, v)

        def render_cs(ax, v=cs):
            _bar_panel_pct(ax, SOCCER_CS_LABELS, v)

        result = card_figure(
            title=team,
            panels=[("ppg L10", render_ppg), ("goals/g L10", render_goals),
                    ("win% / CS% L10", render_rates), ("clean sheet %", render_cs)],
            source_artifact=SOCCER_SOURCE, floors=FLOOR_CARD_NOTE, as_of=as_of,
            out_path=card_path(SPORT_SOCCER, team),
        )

        present = ppg + goals + rates + cs
        n_present = sum(v is not None for v in present)
        entries.append({
            "entity": team,
            "card_path": result["path"],
            "key_numbers": {
                "ppg_l10": ppg[0], "ppg_home_l10": ppg[1], "ppg_away_l10": ppg[2],
                "gf_l10": goals[0], "ga_l10": goals[1], "gd_l10": goals[2],
                "winrate_l10": rates[0], "clean_sheet_rate_l10": rates[1],
                "clean_sheet_rate_season": cs[0], "clean_sheet_rate_home": cs[1], "clean_sheet_rate_away": cs[2],
            },
            "floors": floor_label,
            "as_of": as_of,
            "status": "complete" if n_present == len(present) else f"partial ({n_present}/{len(present)} metrics)",
        })

    return entries, floor_label


def _summary(sport: str, entries: list, manifest_path: Path, card_dir: Path, floor_label: str) -> dict:
    disk_pngs = list(card_dir.glob("*.png"))
    return {
        "sport": sport,
        "manifest_entries": len(entries),
        "disk_pngs": len(disk_pngs),
        "floor": floor_label,
        "card_dir_bytes": sum(p.stat().st_size for p in disk_pngs),
        "manifest_path": str(manifest_path),
        "example_entities": [e["entity"] for e in entries[:3]],
    }


def main() -> dict:
    tennis_entries, tennis_floor = build_tennis_cards(_read_family(TENNIS_FAMILY))
    soccer_entries, soccer_floor = build_soccer_cards(_read_family(SOCCER_FAMILY))
    tennis_manifest = write_manifest(SPORT_TENNIS, tennis_entries)
    soccer_manifest = write_manifest(SPORT_SOCCER, soccer_entries)
    return {
        "tennis": _summary(SPORT_TENNIS, tennis_entries, tennis_manifest, CARD_DIR_TENNIS, tennis_floor),
        "soccer": _summary(SPORT_SOCCER, soccer_entries, soccer_manifest, CARD_DIR_SOCCER, soccer_floor),
    }


def _check_sport(sport: str, card_dir: Path) -> tuple:
    manifest_path = OUT_DIR / f"atlas_{sport}_manifest.json"
    assert manifest_path.exists(), (
        f"{manifest_path} missing -- run `python -m "
        f"scripts.platformkit.analytics_showcase.tennis_soccer_atlas` first")
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    disk_pngs = list(card_dir.glob("*.png"))
    assert manifest["n_entries"] == len(disk_pngs), (
        f"{sport}: manifest says {manifest['n_entries']} entries but {len(disk_pngs)} PNGs on disk in {card_dir}")
    for entry in manifest["entries"][:2]:
        p = resolve_card_path(entry["card_path"])
        assert p.exists() and p.stat().st_size > 0, f"{sport}: card missing/empty: {p}"
    return manifest["n_entries"], len(disk_pngs)


def _check() -> None:
    t_n, t_disk = _check_sport(SPORT_TENNIS, CARD_DIR_TENNIS)
    s_n, s_disk = _check_sport(SPORT_SOCCER, CARD_DIR_SOCCER)
    assert slugify("Novak Djokovic") == "novak_djokovic"  # atlas_factory helper still wired correctly
    print(f"check ok: tennis {t_n}=={t_disk} PNGs, soccer {s_n}=={s_disk} PNGs")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        print(json.dumps(main(), indent=2))
