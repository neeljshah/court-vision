# Memory Graph — Multi-Sport Obsidian Intelligence Graph

> **What this is:** a sport-blind, reproducible, PERSON-FREE Obsidian knowledge
> graph generated from real corpora. It models playstyles, archetypes, team
> patterns, and tactical dimensions — NOT individual athletes. No edge or
> betting-product claims are made; the signal catalogs run candidates through
> the real leak-free gate and all REJECT (markets are efficient).

---

## Overview

The platform maintains a linked Obsidian note graph at `vault/Sports/` (local,
gitignored). The generators that produce it are committed source code. The split
is intentional: the vault is reproducible on demand; only the code travels.

Four sports are currently wired:

| Sport ID        | Display folder      | Corpus hint              | Primary entry module                           |
|-----------------|---------------------|--------------------------|------------------------------------------------|
| `tennis_atp`    | `Tennis/`           | `data/domains/tennis`    | `domains.tennis.atlas`                         |
| `soccer_fd`     | `Soccer/`           | `data/domains/soccer`    | `domains.soccer.atlas`                         |
| `mlb_sbro`      | `MLB/`              | `data/domains/mlb`       | `domains.mlb.atlas`                            |
| `basketball_nba`| `Basketball_NBA/`   | `data/`                  | `domains.basketball_nba.memory_atlas`          |

Each sport folder lives under `vault/Sports/<DisplayName>/`. A cross-sport
`_Hub.md` sits at `vault/Sports/_Hub.md` and links every sport's `_Index` note.

---

## Note Types

### Per-sport core notes (all sports)

| Subfolder       | Description                                                                 | Who writes it                                    |
|-----------------|-----------------------------------------------------------------------------|--------------------------------------------------|
| `_Index.md`     | Hub: corpus span, top-entity table, link registry                           | `build_atlas()` in each domain's `atlas.py`      |
| `Teams/`        | One note per team (soccer / MLB / NBA). Archetype composition, not rosters. | `build_atlas()` in each domain's `atlas.py`      |
| `Leagues/`      | One note per league division (soccer)                                        | `domains.soccer.atlas`                           |
| `Surfaces/`     | Hard / Clay / Grass surface breakdowns (tennis)                              | `domains.tennis.atlas`                           |
| `Matchups/`     | H2H pattern matrices (tennis, soccer, MLB)                                   | `atlas_h2h.build_h2h()`                          |
| `Tournaments/`  | Per-tournament intelligence notes (tennis only)                              | `domains.tennis.atlas_tournaments.build_tournaments()` |
| `Seasons/`      | Season-level narrative notes (soccer, MLB, NBA)                              | `atlas_seasons.build_seasons()`                  |
| `Playstyles/`   | Tactical scheme definitions (soccer, MLB, tennis)                            | `atlas_playstyles.build_playstyles()`            |
| `Archetypes/`   | Stat-signature archetype definitions, NO names (NBA)                         | `memory_atlas_archetypes.build_archetypes()`     |

### Per-sport extra notes (`--full` build only)

| Subfolder          | Description                                                        | Sports           | Key function                        |
|--------------------|--------------------------------------------------------------------|------------------|-------------------------------------|
| `StyleMatchups/`   | Cross-scheme matchup intelligence                                  | tennis, soccer, MLB | `build_style_matchups()`         |
| `StyleTrends/`     | Temporal trend analysis per scheme                                 | tennis, soccer, MLB | `build_style_trends()`           |
| `Scouting/`        | Pattern-level scouting breakdowns (NO individual names)            | all 4 sports     | `build_scouting()`                  |
| `SchemeTransitions/` | Tactical transition patterns across seasons (soccer only)        | soccer           | `build_scheme_transitions()`        |
| `HomeEnvironment/` | Venue / home-field structural effects (MLB only)                   | MLB              | `build_home_environment()`          |
| `Trends/`          | Multi-season trend notes (NBA)                                     | NBA              | `build_trends()`                    |
| `Signals/`         | Per-sport signal catalog (REJECT-first honest gate readout)        | all 4 sports     | written by signal-discovery agents  |

### Cross-sport meta notes (`--full` build only)

These live directly in `vault/Sports/` rather than inside a sport subfolder.

| Note filename             | Content                                                    | Function                                |
|---------------------------|------------------------------------------------------------|-----------------------------------------|
| `_Hub.md`                 | Registry of all sports + note counts                       | `build_all.write_hub()`                 |
| `_GraphStats.md`          | Per-sport note counts, link density, freshness, PERSON-FREE check | `graph_report.build_graph_report()` |
| `_Signals_Hub.md`         | Cross-sport signal-discovery summary (REJECT tallies)      | `signals_hub.build_signals_hub()`       |
| `_Archetype_Taxonomy.md`  | Cross-sport archetype grouping under 7 sport-blind themes  | `archetype_taxonomy.build_taxonomy()`   |
| `_Intelligence_Overview.md` | Synthesis: coverage + themes + edge readout + tactical dims | `intelligence_overview.build_intelligence_overview()` |
| `_Graph_Health.md`        | Dangling-link audit (intentional vs fixable), GRAPH-INTEGRITY verdict | `graph_health.build_graph_health()` |
| `_World_Model.md`         | Cross-sport platform knowledge synthesis (playstyle + archetype landscape) | `world_model.build_world_model()` |
| `_Base_Rates.md`          | Cross-sport unconditional outcome base rates from real corpora (descriptive only) | `base_rates.build_base_rates()` |
| `_Calibration_Segments.md` | Per-sport reliability diagnostics: probability decile bins + per-season ECE | `calibration_segments.build_calibration_segments()` |

---

## Node / Edge Schema

The graph is an Obsidian note graph: every `.md` file is a **node**; every `[[wikilink]]` is a
directed **edge**. The schema is deliberately thin and uniform so it is queryable by plain text
tooling and by Obsidian's own graph view.

### Node anatomy

Each note carries YAML frontmatter (the node's typed attributes) and a body of sections and links:

```
---
tags: [sport, archetype, ...]     # node-type discriminator(s)
updated: 2026-06-18               # freshness stamp
generated: 2026-06-18             # build date (meta notes)
---
# <Title>                         # node label (a scheme / archetype / theme — never a person)
> framing line                    # honest-scope / person-free / no-edge disclaimer
... sections, tables ...
[[Other/Note]] · [[_Hub]]         # outbound edges
```

| Node type | `tags` discriminator | Example node label |
|---|---|---|
| Sport index | `sport, index` | `Tennis/_Index` |
| Archetype / Playstyle | `archetype` / `playstyle` | `3_and_D_Wing`, `Drop_Coverage` |
| Team (composition, not roster) | `team` | a team note keyed by tricode |
| Scheme / Position (cross-sport) | `scheme` / `position` | `Schemes/...`, `Positions/...` |
| Meta synthesis | `meta` / `hub` | `_World_Model`, `_Base_Rates` |
| Signal catalog | `signals, honest` | `<Sport>/Signals/_Catalog` |

### Edge types

| Edge | Direction | Meaning |
|---|---|---|
| `[[<Sport>/_Index]]` | node -> sport hub | "belongs to this sport" |
| `[[_Hub]]` / `Up: [[...]]` | node -> parent | breadcrumb / containment |
| `[[Archetype]]` inside a theme note | taxonomy -> member | "this archetype is in this theme" |
| `[[<Sport>/<Dim>/_..._Index]]` | overview -> dimension index | tactical-dimension drill-down |
| Cross-vault shortcut | node -> outside `vault/Sports/` | intentional dangling (`[[Home]]`, `[[MOC-*]]`) |

### Two graphs, one discipline

There are two related graphs, and the **person-free** invariant applies to the platform graph:

- **`vault/Sports/`** — the multi-sport platform graph: **PERSON-FREE by default**
  (`hub_data.PERSON_FREE`). NAMED generators (Teams / Matchups / Seasons / Tournaments / Scouting)
  are gated OFF unless `--with-named`; only archetype/scheme/style families are emitted.
- **`vault/` (NBA Intelligence)** — the pre-platform NBA brain: the **~690-node knowledge graph
  (660 player + 30 team)** plus the **48 deep atlas-section builders (30 `player_*` + 18 `team_*`)** referenced from
  [INTELLIGENCE.md](INTELLIGENCE.md). The cross-sport `_Hub.md` links to it but does not import
  its person-bearing notes into the person-free `Sports/` graph.

The highest-level **person-free MOC** that stitches the platform families together is
`vault/_Index/_Brain.md`, emitted by `build_brain_index.py`. It links only playstyles, archetypes,
schemes, positions, style-matchups and trends; any `<player-id>_name` or bare `firstname_lastname`
note found while scanning is **skipped and counted** as "skipped (non-person-free)", so the
person-free property is measured on every build, not assumed.

---

## How the Graph Is Queried

The graph is consumed three ways, in increasing structure:

1. **Obsidian graph view / backlinks** — open `_Hub.md` or `_Brain.md` and traverse. Dense hubs
   (the brain MOC + each sport family) keep the constellation legible instead of a 3,000-note hairball.
2. **Meta-note synthesis (build-time queries).** The cross-sport meta generators *are* the query
   layer: they parse the markdown tables out of sibling notes and re-aggregate. For example
   `intelligence_overview.build_intelligence_overview()` parses `_GraphStats.md` (per-sport note
   counts), `_Archetype_Taxonomy.md` (theme link counts), and `_Signals_Hub.md` (REJECT/DEFER/SHIP
   tallies) into one synthesis note — a deterministic, regex-driven read over the graph's own tables.
3. **Grounded LLM access (NBA brain).** `ai_chat_facts.json` + `ai_chat_index.json` (see
   [INTELLIGENCE.md](INTELLIGENCE.md) section 9) route a topic to the right artifact so an LLM
   answers from pre-extracted facts rather than free-associating.

All build-time queries are **read-only over the emitted markdown** and re-derivable; nothing in the
query path asserts a market lift.

---

## How to (Re)Build

One command rebuilds the entire graph from the committed corpora:

```bash
python scripts/platformkit/atlas/build_all.py --sport all --full
```

**What it does, in order:**

1. For each sport, calls `build_atlas()` from its adapter module to emit
   `_Index.md` + entity notes.
2. Calls optional per-sport builders (H2H, Playstyles/Archetypes, Tournaments,
   Seasons) via signature-probed kwargs (`corpus_dir` or `data_dir`).
3. With `--full`, runs the `_EXTRA_GENS` table (StyleMatchups, StyleTrends,
   Scouting, SchemeTransitions, HomeEnvironment, Trends).
4. Writes `vault/Sports/_Hub.md`.
5. With `--full`, runs the eight `_META_GENS` in order: `build_graph_report`,
   `build_signals_hub`, `build_taxonomy`, `build_intelligence_overview`,
   `build_graph_health`, `build_world_model`, `build_base_rates`,
   `build_calibration_segments`.

**Single-sport rebuild:**

```bash
python scripts/platformkit/atlas/build_all.py --sport tennis --full
python scripts/platformkit/atlas/build_all.py --sport nba
```

Valid `--sport` values: `tennis`, `soccer`, `mlb`, `nba`, `basketball_nba`, `all`.

**Output directory:** `vault/Sports/` (relative to repo root, gitignored).

All builders are idempotent: rerunning overwrites with identical content.

---

## Code Layout

```
scripts/platformkit/atlas/          # cross-sport drivers + meta generators
    build_all.py                 # main entry; _SPORT_MANIFEST, _EXTRA_GENS, _META_GENS
    obsidian_emit.py             # shared primitives: slug(), frontmatter(), write_note(), md_table()
    graph_report.py              # build_graph_report()
    signals_hub.py               # build_signals_hub()
    archetype_taxonomy.py        # build_taxonomy()
    intelligence_overview.py     # build_intelligence_overview()
    graph_health.py              # build_graph_health()
    world_model.py               # build_world_model()
    base_rates.py                # build_base_rates()
    calibration_segments.py      # build_calibration_segments()

domains/<sport>/                 # per-sport adapter modules
    atlas.py                     # build_atlas() — entry point called by build_all
    atlas_render.py              # rendering helpers (used by atlas.py)
    atlas_h2h.py                 # build_h2h()
    atlas_playstyles.py          # build_playstyles()  (soccer, MLB, tennis)
    atlas_style_matchups.py      # build_style_matchups()
    atlas_style_trends.py        # build_style_trends()
    atlas_scouting.py            # build_scouting()
    atlas_seasons.py             # build_seasons()  (soccer, MLB)
    atlas_scheme_transitions.py  # build_scheme_transitions()  (soccer)
    atlas_home_environment.py    # build_home_environment()  (MLB)

domains/basketball_nba/          # NBA uses memory_atlas* prefix (pre-platform naming)
    memory_atlas.py              # build_atlas()
    memory_atlas_archetypes.py   # build_archetypes()
    memory_atlas_seasons.py      # build_seasons()
    memory_atlas_trends.py       # build_trends()
    memory_atlas_data.py         # shared data-loading helpers
    memory_atlas_render.py       # rendering helpers

tests/platform/
    test_graph_invariants.py     # regression guards for PERSON-FREE + LINK-INTEGRITY
    test_generators_person_free.py  # per-generator invariant tests (hermetic, tmp_path)
    test_graph_report.py
    test_graph_health.py
    test_obsidian_emit.py
```

---

## Invariants

### PERSON-FREE

No individual athlete names appear in any emitted note. The graph models
playstyle archetypes, tactical schemes, team compositions, and market patterns.

Enforcement: `graph_health._is_person_bearing()` flags notes containing any of:
- `[[Players/...]]` wikilinks
- `player_name:` or `display_name:` YAML frontmatter keys
- `## Players`, `## Roster`, or `## Squad` section headers

Two test suites guard this invariant:

- `test_graph_invariants.TestPersonFreeInvariant` — vault-level regression guard
- `test_generators_person_free` — per-generator hermetic guard (synthetic
  DataFrames, `tmp_path` only, never touches the real vault)

### GRAPH-INTEGRITY

Target: **0 fixable dangling wikilinks** in `vault/Sports/`.

`graph_health.build_graph_health()` classifies every dangling link as either:
- **Intentional** — cross-vault shortcuts (`[[Home]]`, `[[MOC-*]]`,
  `[[Intelligence/...]]`) that legitimately resolve outside `vault/Sports/`
- **Fixable** — slug mismatches or missing targets that represent real integrity gaps

The GRAPH-INTEGRITY verdict is PASS when fixable dangling count is 0.

### Code discipline

- Max 300 LOC per file
- `from __future__ import annotations` + type hints on all public functions
- **F5 import allowlist:** every domain module imports only stdlib, numpy,
  pandas, and its own domain siblings. Zero cross-domain imports.
  `obsidian_emit.py` imports stdlib only.
- Shared primitives (`slug`, `frontmatter`, `write_note`, `md_table`) live in
  `obsidian_emit.py`; per-sport duplicates are removed.
- No edge / betting language in any generator output.

---

## Honest Signal Framing

Each sport can generate a `vault/Sports/<Sport>/Signals/_Catalog.md` containing
a verdict table of candidate signals run through the real, leak-free gate.

**Observed result across all four sports: all REJECT.**

The `_Signals_Hub.md` meta-note aggregates these verdicts. A REJECT is the
honest success criterion: it confirms the gate functions correctly and that no
spurious lift has been claimed. The graph is descriptive scouting intelligence,
not a betting product.

If the hub ever shows a SHIP verdict, it is flagged as an **unverified
candidate** requiring multi-fold walk-forward, independent corpus, CLV grading,
and cross-season holdout before any edge claim is permitted.

**Measured-lift honesty.** This graph — like the NBA atlas/intelligence layer it links — is a
**descriptive scouting + correlation asset**. Its measured point-accuracy lift on the served
predictor is **~0 today**, and against devigged closing lines CLV is **~0** (markets are
efficient). Every count, density, and base-rate on these notes is a **descriptive / calibration**
statistic; none is a dollar edge. The graph models playstyles and schemes, **never people**.

---

## Adding a Fifth Sport

1. Create `domains/<sport>/` with a `build_atlas(out_dir, corpus_dir)` function.
2. Add a row to `_SPORT_MANIFEST` in `scripts/platformkit/atlas/build_all.py`.
3. Optionally add `_EXTRA_GENS` rows for the optional builders you implement.
4. Ensure all emitted notes pass `test_generators_person_free` and
   `test_graph_invariants`.

No changes to `kernel/`, `src/`, or any other sport's code are required.

---

## Vault Layout (after a full build)

```
vault/Sports/
    _Hub.md
    _GraphStats.md
    _Signals_Hub.md
    _Archetype_Taxonomy.md
    _Intelligence_Overview.md
    _Graph_Health.md
    _World_Model.md
    _Base_Rates.md
    _Calibration_Segments.md
    Tennis/
        _Index.md
        Surfaces/{Hard,Clay,Grass}.md
        Matchups/…
        Tournaments/…
        Seasons/…
        Playstyles/…
        StyleMatchups/…
        StyleTrends/…
        Scouting/…
    Soccer/
        _Index.md
        Teams/…
        Leagues/…
        Matchups/…
        Seasons/…
        Playstyles/…
        StyleMatchups/…
        StyleTrends/…
        SchemeTransitions/…
        Scouting/…
    MLB/
        _Index.md
        Teams/…
        Leagues/…
        Matchups/…
        Seasons/…
        Playstyles/…
        StyleMatchups/…
        StyleTrends/…
        HomeEnvironment/…
        Scouting/…
    Basketball_NBA/
        _Index.md
        Teams/…
        Archetypes/…
        Seasons/…
        Trends/…
        Scouting/…
```

---

*Auto-maintained by the platform build. Re-run
`python scripts/platformkit/atlas/build_all.py --sport all --full`
to refresh the vault. This doc describes the generators; the vault output is
gitignored and local-only.*

**Siblings:** [INTELLIGENCE.md](INTELLIGENCE.md) (80-artifact NBA manifest) ·
[PLAYER_INTELLIGENCE.md](PLAYER_INTELLIGENCE.md) (dossier showcase + scope) ·
[signal-inventory.md](signal-inventory.md) (feature catalog + SHIP/REJECT verdicts) ·
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) · [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) ·
[full doc map](INDEX.md).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
