# CourtVision MCP -- Tool Reference

The CourtVision MCP server exposes the **fail-closed sports-intelligence engine** over
stdio JSON-RPC 2.0. It is a thin, honest interface on top of the answer engine
(`scripts/platformkit/answers/resolver_registry.py`) and its sibling resolvers -- it
**authors no numbers**. Every tool reads a value verbatim off a named source artifact,
or fails closed. The binding client rules are in
[docs/AI_CONSUMER_CONTRACT.md](AI_CONSUMER_CONTRACT.md); the no-edge rule is
[.claude/rules/no-edge-claims.md](../.claude/rules/no-edge-claims.md).

- **Server entry:** `python -m scripts.platformkit.mcp_server.server` (registered as
  `courtvision` in `.mcp.json`; launch from repo root).
- **Wire protocol:** newline-delimited JSON-RPC 2.0 -- `initialize`, `tools/list`,
  `tools/call`, `ping`, `notifications/*`. No `mcp` SDK dependency.
- **9 tools:** `ask`, `scouting_report`, `comparables`, `matchup_preview`,
  `win_probability`, `injury_report`, `analytics_receipts`, `run_burst`,
  `system_health`.
- **Every result is an envelope** carrying `status` + `source_artifact` + `as_of`.
  Honor `status` verbatim (see the [Envelope Contract](#envelope-contract) below).
- **Fresh-clone note:** `data/` and `vault/` are gitignored, so on a bare clone many
  tools return `no_data` by design. `ask` with an `atlas_card`, `mechanism_effect`, or
  edge-language (`refused`) query works from committed artifacts; the rest need the
  local caches built. `no_data` / `not_supported` are **honest successes**, never errors.

Paths shown in `source_artifact` are **repo-relative** -- rejoin against the runtime repo
root; a `data/cache/...` path meaning the local cache is absent on a fresh clone.

---

## Tool: `ask`

**Purpose:** Universal front door -- route any natural-language sports question through the
fail-closed answer engine (`resolver_registry.resolve`). Covers 20+ registered categories
(player_stat, rating_attribute, concept_rating, prediction_winprob, calibration_number,
historical_result, mechanism_effect, ranking, injury_report, news_context,
schedule_context, scouting_report, comparables, matchup_preview, verified_claims,
atlas_card, h2h_history, conditional_winprob, player_comparison, and the analytics
receipts). The query is classified into exactly one category (or you may force one).

**Parameters:**

| name | type | required | description |
|------|------|----------|-------------|
| `query` | string | yes | the natural-language question |
| `sport` | string | no | `nba` \| `mlb` \| `soccer` \| `tennis` (default `nba`) |
| `category` | string | no | force a category, bypassing `classify()` |

**Example call:**
```json
{"name": "ask", "arguments": {"query": "show me the atlas card for mlb inning 1", "sport": "mlb"}}
```

**Example envelope** (`atlas_card` -- works on a bare clone off the committed manifest):
```json
{
  "status": "ok",
  "category": "atlas_card",
  "sport": "mlb",
  "source_artifact": "scripts/platformkit/analytics_showcase/out/atlas_calibration_manifest.json",
  "as_of": "2026-07-23T01:39:22.086535+00:00",
  "entity": "mlb inning 1",
  "card_path": "docs/img/atlas/calibration/mlb_inning_1.png",
  "key_numbers": {"market_ece": 0.0903, "model_ece": 0.1329, "n": 7646},
  "floors": "n>=30 rows required for a checkpoint/band card to render (declared floor, not tuned to today's data)",
  "descriptive_only": true,
  "edge_claimed": false
}
```

**Example envelope** (`mechanism_effect` -- verbatim validation-ledger row(s)):
```json
{
  "status": "ok",
  "category": "mechanism_effect",
  "sport": "nba",
  "source_artifact": "domains/basketball_nba/knowledge/validation_ledger.jsonl",
  "as_of": "2026-07-22T...",
  "hypothesis": "clutch_usage_compression",
  "findings": [
    {"verdict": "CONFIRMED_LOCAL", "effect_local": 0.041, "n": 812, "p": 0.03,
     "corpus": "nba_2023_24", "note": "AMPLIFYING direction, not the claimed compression"}
  ],
  "framing": "LOCAL single-corpus finding(s) -- not a market-beating or causal claim"
}
```

**Failure modes:**
- `not_supported` -- no resolver registered for the classified type (`category` is `null` or
  unknown). Stop; do not improvise. `note` lists the registered categories.
- `no_data` -- the backing artifact is absent/empty (e.g. `calibration_number` on a clone
  where `vault/` is gitignored). Say NO_DATA; never fill from model memory.
- `refused` -- edge/ROI/retracted-number language (`edge`, `roi`, `+ev`, `18.38`, `0.119`,
  `78.11`, ...). `source_artifact` cites `.claude/rules/no-edge-claims.md`.
- `ambiguous` -- multiple entities/mechanisms match; a `candidates` list is returned.
  Disambiguate before answering.

**Source-artifact provenance:** one declared artifact per category, in
`resolver_registry.RESOLVERS` (e.g. `data/cache/profiles/<sport>_*_profiles.parquet` for
stats, `domains/<sport>/knowledge/validation_ledger.jsonl` for mechanisms,
`scripts/platformkit/analytics_showcase/out/atlas_*_manifest.json` for atlas cards). If a
branch omits `source_artifact`, the server backfills it from that registry entry.

---

## Tool: `scouting_report`

**Purpose:** Multi-axis descriptive scouting **vector** for one player -- per-concept
rating + percentile, an NBA shooting facet, and top raw-attribute percentiles. Axes are
reported independently and **never collapsed into one score**. Descriptive only, no
prediction.

**Parameters:**

| name | type | required | description |
|------|------|----------|-------------|
| `sport` | string | yes | `nba` \| `mlb` \| `soccer` \| `tennis` |
| `player` | string | yes | player name (fuzzy-matched) |
| `top_n` | integer | no | raw-attribute axes to return (default 8) |

**Example call:**
```json
{"name": "scouting_report", "arguments": {"sport": "nba", "player": "LeBron James", "top_n": 8}}
```

**Example envelope** (`ok`):
```json
{
  "status": "ok",
  "category": "scouting_report",
  "sport": "nba",
  "kind": "player",
  "player": "LeBron James",
  "source_artifact": "data/cache/profiles/nba_player_profiles.parquet",
  "as_of": "2026-07-20T14:03:11+00:00",
  "answerable": true,
  "concept_axes": [
    {"axis": "rim_pressure", "status": "ok", "rating": 88.4,
     "rating_scale": "weighted-percentile composite in [0,100] (higher = stronger on this concept)",
     "percentile": 96.1, "rank": 12, "pool_n": 305, "n": 71, "confidence": "high",
     "status_mix": {"...": "..."},
     "citation": {"concept_registry": "domains.basketball_nba.concepts.concept_registry",
                  "signals": ["...", "..."],
                  "source_artifact": "data/cache/profiles/nba_player_profiles.parquet"}},
    {"axis": "spacing", "status": "not_in_pool", "pool_n": 305,
     "note": "player absent from this concept's ranking (below its min-n floor or no signals)",
     "citation": {"...": "..."}}
  ],
  "shooting_facet": {"status": "OK", "...": "..."},
  "raw_attributes": {"status": "ok", "top_n": 8, "source_artifact": "data/cache/profiles/nba_player_profiles.parquet",
    "attributes": [{"attribute": "drives_per_75", "percentile": 91.2, "raw_value": 14.7, "n": 71, "status": "..."}]},
  "injury_context": {"injury_facts": {"status": "no_data", "...": "..."},
                     "mlb_injury_recency": {"status": "not_applicable", "...": "..."}},
  "axes_hit": {"concepts": 6, "concepts_total": 9, "shooting_facet": true, "raw_attributes": true},
  "note": "DESCRIPTIVE multi-axis scouting vector -- each axis reported with its own rating, percentile, and citation; axes are NEVER combined into one score. No forecast/$ claim.",
  "edge_claimed": false,
  "computed_at": "2026-07-23T..."
}
```

**Failure modes:**
- `no_data` -- sport has no wired concept registry (`note` lists available sports); OR the
  player resolves on **no axis** (`answerable: false`, `missing` names the miss: `0/N`
  concept ratings, no shooter facet, no raw rows); OR the profiles parquet is absent on a
  clone.
- `ambiguous` -- name matches 2+ distinct `entity_id`s (`candidates` list). Narrow the query.

**Source-artifact provenance:** `data/cache/profiles/<sport>_player_profiles.parquet`
(`as_of` = parquet mtime -- a season snapshot, no live-freshness SLA). Concept ratings come
from `contracts.answer_superlative` (one weight formula, never re-derived here); shooting
facet from `compose_profile` (NBA VERIFIED claims).

---

## Tool: `comparables`

**Purpose:** The K nearest players to a target by **RMS-normalized Euclidean distance** over
shared attribute percentiles. "Statistically similar profile" -- descriptive, never a
projection.

**Parameters:**

| name | type | required | description |
|------|------|----------|-------------|
| `sport` | string | yes | `nba` \| `mlb` \| `soccer` \| `tennis` |
| `player` | string | yes | target player name (fuzzy-matched) |
| `k` | integer | no | neighbors to return (default 5) |

**Example call:**
```json
{"name": "comparables", "arguments": {"sport": "nba", "player": "Nikola Jokic", "k": 5}}
```

**Example envelope** (`ok`):
```json
{
  "status": "ok",
  "category": "player_comparables",
  "sport": "nba",
  "source_artifact": "data/cache/profiles/nba_player_profiles.parquet",
  "as_of": "2026-07-23T...",
  "player": "Nikola Jokic",
  "entity_id": 203999,
  "k": 5,
  "floor": 5,
  "neighbors": [
    {"entity_id": 201142, "entity_name": "Kevin Durant", "distance": 12.4831, "n_attrs": 18,
     "attributes_used": [{"attribute": "ts_pct", "description": "true shooting %"}]}
  ],
  "note": "statistically similar profile (Euclidean over shared percentile attributes) -- descriptive only, never a projection"
}
```

**Failure modes:**
- `no_data` -- no player parquet built for the sport (clone), or the name resolves to no
  unique entity.
- `ambiguous` -- name matches 2+ distinct players (`candidates` list).
- `refused` -- target has fewer than `floor` (=5) registered attributes on file, OR no
  candidate clears the >=5 shared-attribute intersection floor (`entity_id` + `floor`
  echoed). This is an honesty gate, not an error: a thin profile is never distance-padded
  with guessed values.

**Source-artifact provenance:** `data/cache/profiles/<sport>_player_profiles.parquet`
(kind=`player` rows only). Distance is `sqrt(mean(delta**2))` over shared non-null
percentiles; attribute descriptions enriched from
`domains/<domain>/profiles/attribute_registry.py` (presentation-only).

---

## Tool: `matchup_preview`

**Purpose:** Descriptive matchup preview -- a fan-out envelope wrapping 8 sub-resolvers
(win prob, both team profiles, style matchup, both injury reports, both schedule contexts),
each quoted verbatim under its own block. **Not a betting recommendation.** The overall
status stays `ok` even when individual blocks are `no_data`; `blocks_ok` / `blocks_absent`
name which landed.

**Parameters:**

| name | type | required | description |
|------|------|----------|-------------|
| `sport` | string | yes | `nba` \| `mlb` \| `soccer` \| `tennis` |
| `home` | string | yes | home team |
| `away` | string | yes | away team |
| `date` | string | no | optional `YYYY-MM-DD` (default today, UTC) |

**Example call:**
```json
{"name": "matchup_preview", "arguments": {"sport": "nba", "home": "LAL", "away": "BOS", "date": "2025-11-01"}}
```

**Example envelope** (overall `ok`, most blocks absent on a clone):
```json
{
  "status": "ok",
  "category": "matchup_preview",
  "sport": "nba",
  "source_artifact": "scripts/platformkit/intel_query/compose_matchup.py",
  "as_of": "2026-07-23T...",
  "home": "LAL", "away": "BOS", "date": "2025-11-01",
  "blocks": {
    "win_prob": {"status": "no_data", "category": "winprob", "source_artifact": "scripts/platformkit/predict_matchup.py", "note": "predict_matchup produced no JSON: ...corpus unavailable..."},
    "home_profile": {"status": "no_data", "category": "team_profile_summary", "...": "..."},
    "away_profile": {"status": "no_data", "...": "..."},
    "style_matchup": {"status": "no_data", "category": "style_matchup", "...": "..."},
    "home_injury_report": {"status": "no_data", "category": "edge_facts_injury_report", "...": "..."},
    "away_injury_report": {"status": "no_data", "...": "..."},
    "home_schedule_context": {"status": "no_data", "...": "..."},
    "away_schedule_context": {"status": "no_data", "...": "..."}
  },
  "blocks_ok": [],
  "blocks_absent": ["win_prob", "home_profile", "away_profile", "style_matchup",
                    "home_injury_report", "away_injury_report", "home_schedule_context", "away_schedule_context"],
  "note": "DESCRIPTIVE matchup preview assembled from independently fail-closed sub-resolvers -- each block carries its own source_artifact/as_of; a block's own no_data/refused/not_supported marks it absent without failing the overall preview. No forecast/$ edge claim beyond win_prob's own quoted probability.",
  "edge_claimed": false
}
```
When caches are present, an `ok` block (e.g. `win_prob`) appears in `blocks_ok` and carries
the full sub-envelope of the corresponding standalone tool.

**Failure modes:** The preview itself effectively never fails -- it returns `ok` if it ran.
Absence lives **inside** the blocks (`blocks_absent`). Read each block's own `status` before
quoting it. A `style_matchup` block for an unwired sport returns `not_supported` inside the
block.

**Source-artifact provenance:** the composer authors nothing -- top-level `source_artifact`
is the composer module; each block cites its own artifact
(`predict_matchup.py`, `<sport>_team_profiles.parquet`, VERIFIED style claim stores,
`injury_facts_<sport>.jsonl`, the games calendar).

---

## Tool: `win_probability`

**Purpose:** Calibrated **pre-game (or in-game) win probability**, quoted verbatim off
`predict_matchup.py` (run as a subprocess -- authors no new number). Pass `ingame_state`
for a live re-priced number.

**Parameters:**

| name | type | required | description |
|------|------|----------|-------------|
| `sport` | string | yes | `nba` \| `mlb` \| `soccer` \| `tennis` |
| `home` | string | yes | home team/player |
| `away` | string | yes | away team/player |
| `ingame_state` | object | no | live score state; **must be complete for the sport or it is silently ignored** and pregame is returned |

**Required `ingame_state` keys per sport (all must be present):**
- `nba` / `wnba` / `soccer`: `elapsed`, `home_score`, `away_score`
- `mlb`: `inning`, `half` (`"top"`|`"bottom"`), `home_score`, `away_score`
- `tennis`: `sets_home`, `sets_away` (optional `games_home`, `games_away`, `surface`)

An incomplete state is dropped, not rejected -- check the response for `ingame` vs
`ingame_note` to tell which path ran.

**Example call:**
```json
{"name": "win_probability", "arguments": {"sport": "mlb", "home": "NYY", "away": "BOS",
  "ingame_state": {"inning": 7, "half": "top", "home_score": 3, "away_score": 2}}}
```

**Example envelope** (`ok`, with caches present):
```json
{
  "status": "ok",
  "category": "winprob",
  "sport": "mlb",
  "source_artifact": "scripts/platformkit/predict_matchup.py",
  "as_of": "2026-07-23T...",
  "home": "NYY", "away": "BOS",
  "edge_claimed": false,
  "framing": "calibrated probability, not a dollar edge or beat-the-market claim",
  "pregame": {"p_home_win": 0.5412, "...": "..."},
  "ingame": {"p_home_win": 0.6180, "...": "..."},
  "p_home_win": 0.6180,
  "state_bucket": "mlb_mid_close",
  "bucket_calibration": {"can_price": true, "state_bucket": "mlb_mid_close", "...": "..."}
}
```
On a fresh clone (no forecast corpus), `predict_matchup` prints a plain "corpus unavailable"
line and this returns `no_data` cleanly.

**Failure modes:**
- `no_data` -- predict_matchup exited nonzero, timed out (60s), or produced no JSON
  (including the clone "corpus unavailable" case). `note` carries the stdout/stderr tail.
- Incomplete `ingame_state` does **not** fail -- it is silently dropped and the response
  carries `ingame_note` (not `ingame`) with the same `p_home_win` as omitting it.

**Source-artifact provenance:** `scripts/platformkit/predict_matchup.py` ->
`domains/<sport>/predictor.py`. The probability, `framing`, `edge_claimed`, and any
component blocks are quoted verbatim. This is a **calibrated probability, not a dollar
edge** (see the [never-do](#what-this-server-will-never-do) section).

---

## Tool: `injury_report`

**Purpose:** Newest-first injury-status rows for a team or player, verbatim off the fact
store, with a **7-day staleness gate**.

**Parameters:**

| name | type | required | description |
|------|------|----------|-------------|
| `sport` | string | yes | `nba` \| `mlb` \| `soccer` \| `tennis` |
| `team_or_player` | string | yes | a team name or a player name (resolver filters verbatim) |

**Example call:**
```json
{"name": "injury_report", "arguments": {"sport": "nba", "team_or_player": "Trae Young"}}
```

**Example envelope** (`ok`):
```json
{
  "status": "ok",
  "category": "edge_facts_injury_report",
  "sport": "nba",
  "source_artifact": "data/cache/edge_engine/injury_facts_nba.jsonl",
  "as_of": "2026-07-22T09:14:00+00:00",
  "team": null, "player": "Trae Young", "matched_entity": "Trae Young",
  "n": 1,
  "rows": [
    {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "Questionable",
     "detail": "right shoulder", "report_date": "2026-07-22", "source": "...",
     "source_url": "...", "fetched_at": "2026-07-22T09:14:00+00:00"}
  ]
}
```

**Failure modes:**
- `no_data` -- injury facts store not built in this clone; OR neither team nor player
  supplied; OR zero rows matched (`note` echoes the query); OR matched rows carry no
  parseable timestamp.
- `refused` -- the newest matched row is older than the 7-day staleness bound (`as_of` =
  that row's timestamp; `note` gives the age). A stale injury answer is worse than none.

**Source-artifact provenance:** `data/cache/edge_engine/injury_facts_<sport>.jsonl` via
`facts_store.path_for`. Rows are read verbatim (`player_name`, `team`, `status`, `detail`,
`report_date`, `source`, `source_url`, `fetched_at`); capped at 50.

---

## Tool: `analytics_receipts`

**Purpose:** The verified-analytics receipts ledger. `kind` selects the view. Fail-closed:
absent artifact -> `no_data`; artifact not stamped `edge_claimed:false` -> `refused`;
receipt older than 48h -> `refused`.

**Parameters:**

| name | type | required | description |
|------|------|----------|-------------|
| `kind` | string (enum) | yes | `attribution` \| `claim_survival` \| `verification` \| `contradictions` \| `system_map` |
| `sport` | string | no | sport or `all` (default `all`) |

`kind` meanings: `attribution` (which card produced which claim), `claim_survival` (how many
claims survive re-grading), `verification` (independent-corpus re-checks), `contradictions`
(claims that disagree -- can be a large payload, the full conflict dump, no paging),
`system_map` (how the pieces connect).

**Example call:**
```json
{"name": "analytics_receipts", "arguments": {"kind": "claim_survival", "sport": "all"}}
```

**Example envelope** (`ok`, `claim_survival`):
```json
{
  "status": "ok",
  "category": "analytics_claim_survival",
  "sport": "all",
  "source_artifact": "data/cache/analytics_verify/claim_survival.json",
  "as_of": "2026-07-23T00:12:00+00:00",
  "honest_note": "DECAYED means stop trusting that card",
  "n_cards_total": 84, "n_eligible": 61,
  "verdict_counts": {"SURVIVING": 52, "DECAYED": 6, "INSUFFICIENT": 23},
  "survival": {"7d": 0.93, "30d": 0.88, "60d": 0.85},
  "decayed_cards": ["..."], "insufficient_cards": ["..."]
}
```
(Other kinds return their own fields -- e.g. `verification` returns
`overall`/`n_verified`/`n_discrepant`/`checks`; `system_map` returns
`n_nodes`/`n_edges`/`nodes`; `attribution` returns `families`/`cards`/`receipt`;
`contradictions` returns `conflicts`/`by_family_consistency`.)

**Failure modes:**
- `not_supported` -- `kind` not one of the five (`note` lists the valid set).
- `no_data` -- the analytics-verify artifact is absent/unreadable in this clone; OR a
  filtered lookup (`family=`, `card_id=`, `stat=`) matched no row.
- `refused` -- the artifact is missing an explicit `edge_claimed:false` stamp, has no
  parseable `generated_at`/`as_of`, or is older than the 48h staleness bound.

**Source-artifact provenance:** `data/cache/analytics_verify/{attribution_rollup,
claim_survival,sentinel_report,contradiction_report,system_map}.json`. Every number is read
verbatim -- recomputation is each producer's own job, never done here.

---

## Tool: `run_burst`

**Purpose:** **Executes a maintenance burst** -- takes minutes, hits the network, writes to
disk. Not a query. Runs the one-shot burst in a single RSS-guarded process and returns the
report. Prefer `system_health` for a read that touches nothing.

**Parameters:**

| name | type | required | description |
|------|------|----------|-------------|
| `steps` | string | no | comma list: `line_snapshot,settle_sweep,pnl_bestbets,analytics_verify,feed_health,freshness_sla` (first three are network/slow) |
| `skip_slow` | boolean | no | run only the cheap local-only steps (`pnl_bestbets`, `analytics_verify`, `freshness_sla`) |

**Example call:**
```json
{"name": "run_burst", "arguments": {"skip_slow": true}}
```

**Example envelope** (`ok`):
```json
{
  "status": "ok",
  "started": "2026-07-23T...",
  "steps": [
    {"name": "pnl_bestbets", "status": "ok", "secs": 1.4, "rss_mb_after": 210},
    {"name": "analytics_verify", "status": "ok", "secs": 3.1, "rss_mb_after": 240},
    {"name": "freshness_sla", "status": "ok", "secs": 0.6, "rss_mb_after": 244}
  ],
  "edge_claimed": false,
  "honest_note": "..."
}
```
If the burst aborts (e.g. an RSS guard trips), `status` is `aborted` and `aborted_reason`
is set.

**Failure modes:** `aborted` -- the RSS guard tripped or a step raised. On a fresh clone the
cheap steps run but the payload is largely empty (nothing to summarize). The three network
steps require live connectivity and local corpora.

**Caution:** This is the only non-read-only tool -- it fetches over the network and writes
`data/`. Do not fire it on a recruiter clone. Use `skip_slow: true` (or a `steps` subset) to
avoid the minutes-long network work.

**Source-artifact provenance:** writes/refreshes
`data/cache/analytics_verify/burst_report.json` and the per-step outputs. The top-level
`status` field is added at the MCP boundary (the underlying `burst_run` report has no
`status` of its own).

---

## Tool: `system_health`

**Purpose:** Cheap **read-only** status -- last burst report, freshness-SLA summary, and
fleet on/off state. No network, no compute; reads cached JSON only. UNITS only, no $/edge.

**Parameters:** none.

**Example call:**
```json
{"name": "system_health", "arguments": {}}
```

**Example envelope** (`ok`, fleet off by design, blocks absent on a clone):
```json
{
  "status": "ok",
  "category": "system_health",
  "fleet_on": false,
  "fleet_phase": null,
  "burst_report": {"status": "no_data", "source_artifact": "data/cache/analytics_verify/burst_report.json", "note": "absent"},
  "freshness": {"status": "no_data", "source_artifact": "data/frontend/ops/freshness_sla.json", "note": "absent"},
  "honest_note": "cheap reads only; no live probe. UNITS only, no $/edge."
}
```
When caches exist, `burst_report` is the last `run_burst` report, `freshness` is
`{overall, n_red, n_daemons, generated_at}`, and `fleet_on`/`fleet_phase` reflect
`.bot_state/live_status.json`.

**Failure modes:** the tool itself always returns `status: ok` -- absence lives in the
individual blocks (each an inline `{status:"no_data", source_artifact, note}`).
`fleet_on: false` is the **by-design** resident-server default, not an error.

**Source-artifact provenance:** `data/cache/analytics_verify/burst_report.json`,
`data/frontend/ops/freshness_sla.json`, `.bot_state/live_status.json` (all repo-relative,
anchored to the repo root). It replays the **last** `run_burst` report -- it does not
refresh `feed_health` itself.

---

## Envelope Contract

Every tool result is a JSON object carrying a `status`, plus `category`, `source_artifact`,
and `as_of` on any answer with a number. **Honor `status` verbatim -- never soften it into a
hedge.**

| status | meaning | how the caller must respond |
|--------|---------|-----------------------------|
| `ok` | the backing artifact answered | use the numbers **verbatim**; cite `source_artifact` + `as_of`. Do not re-round or re-derive. |
| `no_data` | the artifact is absent/empty/zero-row | say **NO_DATA** and name the reason; do **not** fill the gap from model memory. |
| `not_supported` | no resolver registered for this question type | say NOT_SUPPORTED and **stop**; never improvise. |
| `refused` | edge/ROI/retracted-number language, or a stale receipt | **refuse**; cite `.claude/rules/no-edge-claims.md`. |
| `ambiguous` | multiple candidates match | disambiguate (a `candidates` list is provided) before answering. |
| `error` | a handler raised (wrapped by the server; `isError: true`) | surface the error; the loop never crashes. |

Common fields: `category` (the resolver category), `sport`, `source_artifact`
(**repo-relative** -- rejoin against the runtime repo root), `as_of` (ISO-8601 UTC;
for pinned artifacts this is the file mtime -- the answer is only as fresh as that file),
and, where relevant, `edge_claimed: false` / `framing` / `note`. Numbers are quoted exactly
as the resolver returned them.

**Binding client rules** (from [docs/AI_CONSUMER_CONTRACT.md](AI_CONSUMER_CONTRACT.md)):
route every sports question through a tool, never model memory; quote numbers verbatim;
cite artifact + as-of on every number; apply refusal rules verbatim; never mix engine
numbers with model-memory numbers in one answer.

---

## What this server will never do

This is a **calibrated predictor and verified-analytics engine, not a betting-edge / ROI
product.** The following are refused by design, and no tool will ever return them:

- **No dollar edge / ROI / profit / bankroll claim, and no "beat the market / beat the
  close" claim.** Any query using that language classifies to `edge_language` and returns
  `status: refused` citing `.claude/rules/no-edge-claims.md`. `win_probability` returns a
  **calibrated probability only** (`edge_claimed: false`); every descriptive tool carries
  `edge_claimed: false`.
- **No retracted measurement artifacts as current numbers.** The strings `18.38`, `0.119`,
  `+54%`/`54%`, `78.11`, `8.94`, `54.57` are hard-blocked in `ask` and never re-surfaced --
  they exist only inside explicit retraction context in
  [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).
- **No fabricated values to cover a gap.** An absent artifact is `no_data`, an unregistered
  question is `not_supported`, a thin/stale profile is `refused`. An honest NO_DATA / REJECT
  is a **success**, not a failure.
- **No number without provenance.** Every returned number names its `source_artifact` and
  `as_of`; the engine authors nothing it cannot cite.

The honest, defensible claim is: **calibrated forecasts that match the devigged close within
noise, plus verified, adversarially-audited analytics receipts** -- never a profit claim.
