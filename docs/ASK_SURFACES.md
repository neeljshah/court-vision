# Ask the system anything (it only answers what it can prove)

> **Funnel position:** this sits downstream of stage 6 (INTELLIGENCE) -- it is the read-only
> question-answering surface over the VERIFIED claim corpus described in
> [docs/INTELLIGENCE.md](INTELLIGENCE.md) and the claims-factory pipeline. See
> [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) for what "VERIFIED" is allowed to mean.

Most "ask the AI a question" surfaces work by handing the question to an LLM and trusting
whatever comes back. This one does the opposite. The router is deterministic keyword/regex
matching, not a model call, and every answer is a direct read of a claim row an **independent
validator** already marked `VERIFIED`. If no VERIFIED claim covers the question, the system says
so -- explicitly, with a list of the question shapes it *does* know how to answer -- instead of
computing something plausible on the fly.

That refusal is the product. An LLM bolted on top of raw data will always find a number to
return; this layer is built so that it can't.

## The module map

| Module | Family | What it answers |
|---|---|---|
| `scripts/platformkit/intel_query/ask.py` | `top_n`, `entity_lookup`, `provenance`, `gate_verdict` | Rankings, single-entity lookups, "how do you know", gate pass/fail |
| `scripts/platformkit/intel_query/compose_best.py` | `best` | "Who is the best `<aspect>`, all factors weighed" -- ONE conclusion |
| `scripts/platformkit/intel_query/compose_profile.py` | `shooter_profile` | "What kind of shooter is `<player>`" -- a multi-axis trait vector |
| `scripts/platformkit/intel_query/paper_analytics.py` | (separate ledger surface) | Paper-trading performance questions, gated by channel greenlight status |

`ask()` in `ask.py` is the front door for the first three families; `compose_best` and
`compose_profile` are invoked internally by `ask()` when a question matches their pattern, and
can also be called directly. `paper_analytics.py` is intentionally a **separate** module -- it
answers from a live, unvalidated ledger (`data/frontend/clv_ledger.jsonl`), not from the VERIFIED
claim corpus, and the module docstring says so up front so the two surfaces are never confused.

## The VERIFIED-only contract

`ask.py`'s module docstring states the rule plainly: *"answering ONLY from VERIFIED claims ...
NO LLM call inside this module ... Never falls back to raw computation; never answers from an
UNVERIFIABLE/MISMATCH claim."*

Mechanically, this is `load_verified_claims()`: it walks `CLAIM_SOURCE_PAIRS` -- every
`(validation_summary.json, claims.jsonl)` pair discovered under `data/cache/intel_claims/*.jsonl`
-- and keeps only the claim rows whose `claim_id` appears in that store's validation summary with
`verdict == "VERIFIED"`. A claim a validator marked `MISMATCH` or `UNVERIFIABLE` is not filtered
out at query time; it was never loaded into the answerable set in the first place.

Two failure-handling choices worth naming, because they are what make "VERIFIED-only" durable
rather than aspirational:

- **Discovery is automatic, not hand-registered.** `discover_claim_source_pairs()` globs
  `data/cache/intel_claims/*.jsonl` and pairs each file with its `<stem>_validation.json`
  sibling (falling back to a two-entry legacy override map for stores that predate that naming
  convention). A new claim store lands in `ask()` the moment its producer and validator both
  write to disk -- no per-store registration to forget.
- **Fail-open per file, per line.** A missing or malformed validation JSON is treated as "not
  yet available" for that one store, not a crash for every other store. A single malformed line
  in a `.jsonl` claims file is skipped, not fatal to the rest of the file. One producer caught
  mid-write can never take the whole answer surface down.

## The four families in `ask.py`

Routing is `families.classify()` -- pure regex over the question text, checked in a fixed order
(provenance words first, since a claim_id can otherwise look like a top-N or lookup question).

| Family | Trigger phrasing | Answer shape |
|---|---|---|
| `top_n` | "top N ...", "best N ..." | A ranking slice from one VERIFIED `kind=ranking` claim |
| `entity_lookup` | "where does X rank on ...", "what is X's ..." | Every VERIFIED ranking row that names entity X |
| `provenance` | "how do you know", "show the evidence", "prove", "source for" | The full claim row (criteria, caveats, source files) for a named `claim_id` |
| `gate_verdict` | "what did the ... gate find", "did X beat Y", "what's the verdict" | A VERIFIED `kind=verdict` claim: gate module, verdict, primary number, caveats |

`top_n` questions try a small per-family index sidecar (`ask_index.index_top_n_lookup`) before
falling back to a full parse of `load_verified_claims()` -- a speed optimization, never a
correctness dependency; a miss falls through to the same full-load path unchanged. This matters
because some claim stores are large: `nba_player_box_rate` alone carries 59,268 VERIFIED rows, and
a naive whole-corpus load on every question would not scale.

`gate_verdict` matching is topic-keyword based, not fuzzy: a question must hit a *recognized*
topic alias (`_TOPIC_ALIASES` in `families.py` -- e.g. `tennis_surface`, `mlb_fatigue`,
`nba_fit_validity`) or it matches nothing, honestly, rather than guessing from generic overlap
words like "gate" or "find".

### Worked example: gate_verdict

```
python -m scripts.platformkit.intel_query.ask "What did the tennis surface gate find?"
```

```json
{
  "answerable": true,
  "family": "gate_verdict",
  "answer": {
    "gate_module": "surface hold-prior in-game detail layer (ATP+WTA)",
    "verdict": "REJECT",
    "primary_number": 0.000121,
    "corpus_ids": ["atp_ingame_states", "wta_ingame_states"],
    "planted_null_passed": true,
    "edge_claimed": false,
    "verdict_file": "data/frontend/ingame/surface_hold_verdict.json"
  },
  "evidence": [{
    "claim_id": "tennis_surface_hold_gate_verdict",
    "validator_verdict": "VERIFIED",
    "validator_source": "data/frontend/ops/intel_verdict_claims_validation.json",
    "producer_source": "data/cache/intel_claims/gate_verdict_claims.jsonl"
  }]
}
```

The `REJECT` verdict is not a bug in the answer -- it *is* the answer. A pre-registered gate ran,
the surface-specific prior did not beat the surface-blind base on the real arm, and `ask()` reports
that outcome the same way it would report a `SHIP`. See the no-edge-claims rule
(`.claude/rules/no-edge-claims.md`): an honest REJECT is a recorded success, not a failure to hide.

### Worked example: honest unanswerable

```
python -m scripts.platformkit.intel_query.ask "What is the weather in Boston tomorrow?"
```

```json
{
  "answerable": false,
  "reason": "question did not match a supported family (top_n / entity_lookup / provenance / gate_verdict)",
  "nearest_supported_families": [
    {"family": "top_n", "example": "Who are the top 10 best shooters (composite) in window=last_20?"},
    {"family": "entity_lookup", "example": "Where does Stephen Curry rank on fg3_pct in window=season_2024-25?"},
    {"family": "provenance", "example": "How do you know? Show the evidence for nba_shooting_composite_last_20."},
    {"family": "gate_verdict", "example": "What did the tennis surface gate find?"}
  ]
}
```

This is not a special case in the code -- it is the same `_unanswerable()` helper every family
falls back to when its match fails: no candidate claim, no metric alias, no recognized topic. The
`nearest_supported_families` list is generated from `describe_families()`, not hand-copied, so it
can never drift from what the router actually supports.

## Composer 1: `compose_best` -- one conclusion, honestly

"Who is the best shooter" is a *different question* from "top 5 best shooters" -- singular,
all-factors-weighed, one name out. `ask.py` checks for this pattern (`_BEST_SINGLE_RE`, guarded
against also matching a "top N" phrasing) before its normal family dispatch, and routes it to
`compose_best()`.

`compose_best()` follows a declared, auditable rule (`COMPOSITION_RULE`, emitted verbatim in every
answer) instead of a re-weighted score:

0. **Domain filter** (if declared for the aspect) restricts the primary ranking pool to a
   pre-declared external qualification minimum -- e.g. the NBA's own 3P%-title minimum,
   season `fg3m >= 82` -- never a tuned threshold. The unfiltered #1 is still reported for
   transparency.
1. **Primary axis** = the pre-registered predictive-validity gate's verdict, read live from its
   verdict file, selects which VERIFIED ranking claim is canonical. If the gate ever flips, the
   composer follows it; nothing is hardcoded.
2. **Attribution axes** annotate the primary axis's #1 player with other VERIFIED claims'
   rank/value for that same player. They add context; they never override the primary axis.
3. **Honest disagreement**: when an attribution axis's own #1 differs from the primary axis's #1,
   that disagreement is surfaced explicitly, with the gate citation explaining why the primary
   axis still wins.

### Worked example: compose_best

```
python -m scripts.platformkit.intel_query.ask "who is the best shooter"
```

Condensed real output:

```json
{
  "aspect": "shooter",
  "conclusion": "Jarrett Allen",
  "primary": {
    "claim_id": "nba_canonical_shooter_leaderboard_full_season_2024_25",
    "rank1": "Jarrett Allen",
    "score": 0.7183,
    "gate_verdict": "REJECT_NAIVE_STAYS_CANONICAL"
  },
  "disagreements": [
    {"axis": "shooter_quality_v1_rank", "top_name": "Kevin Durant",
     "why_primary_wins": "primary axis is selected by gate verdict 'REJECT_NAIVE_STAYS_CANONICAL' ..."},
    {"axis": "fg3a_share_of_team", "top_name": "Malik Beasley", "why_primary_wins": "..."}
  ],
  "caveats": [
    "NAIVE-METRICS-DO-NOT-CAPTURE-DIFFICULTY/GRAVITY: ... Concretely on this pool: Stephen Curry "
    "ranks #29/329 while Keon Ellis (a low-usage catch-and-shoot role player) ranks #5/329 -- naive "
    "TS%/eFG%/FT% cannot see that Curry's shots are vastly harder to create/defend than Ellis's, "
    "because difficulty/gravity are not in the formula at all. This is the exact known limitation, "
    "not an incidental artifact."
  ],
  "edge_claimed": false
}
```

This is the honest surprise the composer is built to survive: the naive efficiency composite
really does rank a low-usage catch-and-shoot role player above Stephen Curry, because TS%/eFG%
carry no shot-difficulty or gravity signal. A pre-registered gate already tested whether a richer,
difficulty-aware index (`nba_shooter_quality_v1`) predicts better out-of-sample, and it did not
(`REJECT_NAIVE_STAYS_CANONICAL`) -- so the composer keeps the naive composite canonical *and*
prints the Curry/Ellis diagnostic as a caveat on every single answer, rather than quietly
re-weighting toward the name a human would expect. **The rule stayed fixed; the domain-fix path
(add a shot-difficulty axis) is the only way this changes -- never re-weighting toward a preferred
name.** Section 3.1 of the caveats above cites the exact bootstrap delta and fold counts behind
the gate's `REJECT`.

## Composer 2: `compose_profile` -- a trait vector, never a scalar

`compose_best` answers "who is the best" with one name. `compose_profile` answers a structurally
different question -- "**what kind of** shooter is X" -- and its module docstring names the
reason it exists: *"A shooter is a VECTOR of traits, never one re-weighted scalar ... Luka Doncic
is the canonical case: mediocre fg3_pct but extreme self-created shot difficulty, huge volume,
real gravity."* Collapsing that into a single score is exactly the failure mode `compose_best`'s
Curry/Ellis caveat documents above. So this composer never does it.

Ten axes, grouped `volume | efficiency | difficulty | gravity | context`, each citing its own
VERIFIED claim independently -- `fg3a_per_game`, `fg3a_share_of_team`, `fg3_pct`, `ts_pct`,
`canonical_composite`, `pullup_combined_freq`, `unassisted_share_3pm`, `late_clock_shots_pg`,
`gravity_score`, `fg3_pct_rest_split`. Each axis reports its own `value`, `rank`, and two
percentiles: `pct_pool` (within the claim's full population) and `pct_qualified` (within the
NBA's own `fg3m >= 82` qualification subset). A `trait_line` -- one plain-language sentence --
is built by mapping four of those percentiles through a **declared, frozen** band table
(`elite/high/mid/low` at 90/70/40/0), never by averaging or weighting the axes together.

Missing data is reported, not faked. Two axes the survey found no local corpus for --
`avg_shot_distance` (no 2024-25 shot-location parquet) and true `on_off_gravity` (no lineup
on/off parquet; the `gravity_score` axis instead cites a *modeled* atlas composite, not a
measurement) -- are listed under `unbuilt_axes` with the reason spelled out, on every answer.

### Worked example: compose_profile

```
python -m scripts.platformkit.intel_query.ask "what kind of shooter is Stephen Curry"
```

Condensed real output (10 axes trimmed to the ones behind the trait line):

```json
{
  "status": "OK",
  "player": "Stephen Curry",
  "qualifies_fg3m82": true,
  "axes": [
    {"axis": "fg3a_per_game", "group": "volume", "status": "ok",
     "value": 11.1714, "rank": 1, "pct_qualified": 100.0},
    {"axis": "fg3_pct", "group": "efficiency", "status": "ok",
     "value": 0.3964, "rank": 45, "pool_n": 174, "pct_qualified": 74.6},
    {"axis": "unassisted_share_3pm", "group": "difficulty", "status": "ok",
     "value": 0.296, "rank": 47, "pct_qualified": 76.9},
    {"axis": "gravity_score", "group": "gravity",
     "status": "not_in_pool",
     "note": "absent from this claim's ranking (below its floor or no data)"}
  ],
  "durability": {"status": "ok", "games": 70, "fg3m": 310, "fg3a": 782},
  "trait_line": "elite-volume, high-efficiency shooter; self-creation high, gravity unknown",
  "note": "DESCRIPTIVE trait vector assembled from VERIFIED claims only -- axes are never combined into one score; no forecasting/market claim.",
  "edge_claimed": false
}
```

Note `gravity_score` reads `not_in_pool`, and `trait_line` says `gravity unknown` rather than
silently dropping that clause or guessing a band from a related axis. That is the same discipline
`ask()`'s top-level family dispatch applies at the whole-question level, pushed down to the level
of a single axis inside one answer.

`compose_fit(player, team)` (also in `ask.py`) follows the identical pattern for a different
question -- archetype profile x team scheme identity x role vacancy, joined into one SCOUTING
composition, with the pre-registered fit-validity gate's `REJECT` verdict cited on every answer so
the composition never implies a predictive validity it does not have. A forbidden-word guard
(`predict`, `will improve`, `expected gain`, `edge`) scans the composed answer text before it is
returned, and refuses rather than ship a sentence that would read like a forecast.

## The ledger surface: `paper_analytics.py`

This is the one module in this doc that does **not** read the VERIFIED claim corpus -- it answers
from `data/frontend/clv_ledger.jsonl`, the live paper-trading ledger, streamed line-by-line so a
multi-thousand-row ledger is never loaded whole into memory (one malformed line is skipped, the
same fail-open discipline as `ask.py`'s claim loader).

```
python -m scripts.platformkit.intel_query.paper_analytics "this week by channel"
python -m scripts.platformkit.intel_query.paper_analytics "arb lane"
python -m scripts.platformkit.intel_query.paper_analytics "settlement backlog"
```

Every answer carries `edge_claimed: false` and its source file path, and any `net_units` figure
is a **units** count, never a dollar figure. Critically, a positive `net_units` number is never
shown on its own: `_load_greenlight()` reads `data/frontend/ops/edge_greenlight.json` and every
grouped answer is meant to be read alongside that channel's RED/AMBER/GREEN gate status -- an
unknown-status channel defaults to `"unknown"`, never a silent `"GREEN"`. A units figure without
its gate status attached is not a complete answer; the module is built so that pairing is the
default, not an opt-in.

## Why this shape, not an LLM in the loop

An LLM-in-the-loop "ask anything" surface can always produce *an* answer -- fluent, plausible, and
occasionally wrong in ways that are hard to audit after the fact. This surface is deliberately
narrower: four claim families plus two composers plus one ledger surface, each one a fixed
function over a validated data structure, each one capable of saying "I don't know" in a
structured, machine-readable way (`answerable: false` + `nearest_supported_families`, or
`status: "UNANSWERABLE"` + `missing: [...]`).

The tradeoff is coverage: a question outside these families gets a template refusal, not a
best-effort guess. That is the intended tradeoff. `ask()`'s own docstring calls the discipline out
directly -- *"Never falls back to raw computation"* -- and every worked example above shows what
that looks like in practice: a real answer with its evidence trail attached, or an honest
`answerable: false` with a pointer toward what *is* supported.

---

*Related: [`docs/INTELLIGENCE.md`](INTELLIGENCE.md) - [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md) - [`docs/SPORTS_COVERAGE.md`](SPORTS_COVERAGE.md) - [`.claude/rules/no-edge-claims.md`](../.claude/rules/no-edge-claims.md)*

*Last verified: 2026-07-10*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
