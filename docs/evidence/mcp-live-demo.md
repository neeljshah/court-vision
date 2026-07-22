# Connect Your Own Claude to My Forecaster -- Live MCP Demo

> Every number below arrives inside a fail-closed MCP envelope with a verdict, an `n`, a
> p-value, a `source_artifact`, an `as_of` date, and `edge_claimed: false`. The AI cannot
> improvise -- it can only relay what the engine returns or say `no_data`. The single
> truth-source for any figure is [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).
> The three exchanges below were captured live on 2026-07-22 and are quoted verbatim.

---

## The claim

Any Claude -- Claude Code, Claude Desktop, or an SDK agent -- can connect to this system's
MCP server and get receipt-backed answers. The server does not hand the model a paragraph to
paraphrase. It hands back a structured envelope: a `status` the model must honor verbatim
(`ok` / `no_data` / `not_supported` / `refused` / `ambiguous`), a verdict, sample sizes,
p-values, the exact file the number came from, and the snapshot date. There is no room for
the model to round up, borrow a stale number, or invent a dollar edge. When the data is
absent, the honest answer is `no_data`, and the model is instructed to say so rather than
fill the gap. Below are three real exchanges. Each one shows a different reason this matters.

---

## Exchange 1 -- the mechanism receipt (anti-folklore)

Ask: *"does b2b_rest_penalty hold up"*, sport = nba.

```json
{"status": "ok", "category": "mechanism_effect", "sport": "nba", "source_artifact": "domains/basketball_nba/knowledge/validation_ledger.jsonl", "as_of": "2026-07-16T04:09:44.644893+00:00", "hypothesis": "b2b_rest_penalty", "findings": [{"verdict": "CONFIRMED_LOCAL", "effect_local": -1.73, "n": 4732, "p": 0.005645490426098632, "corpus": "player_boxscores_2024_25_2025_26", "note": "avg margin on 0-rest (-1.41, n=856) vs >=1-day rest (0.32, n=3876)"}, {"verdict": "CONFIRMED_LOCAL", "effect_local": -1.955, "n": 7192, "p": 0.0001174325580081608, "corpus": "player_boxscores_2024_25_2025_26", "note": "avg margin on 0-rest (-1.61, n=1278) vs >=1-day rest (0.35, n=5914)"}], "framing": "LOCAL single-corpus finding(s) -- not a market-beating or causal claim"}
```

"Back-to-backs hurt" is basketball folklore. Here it comes back with two independent splits,
each with its own `n` and `p`, the exact margins on both sides, and the ledger file the
finding lives in -- and the envelope's own `framing` field caps the claim at *"LOCAL
single-corpus finding -- not a market-beating or causal claim."* The engine confirms the
effect and refuses to let it be inflated into an edge in the same breath.

## Exchange 2 -- the caveat ladder and honest axis disagreement

Ask: *"who are the best shooters this season"*, sport = nba. Status `ok`, category
`verified_claims`, source `data/cache/intel_claims/shooter_composite_v2_asof_approx_snapshot.parquet`,
as_of 2026-07-19. The verified conclusion is **Jamal Murray**. Selected caveats, verbatim:

> "ATLAS-UNAVAILABLE-2025-26: shooter_composite_v2's other 4 ingredients ... unavailable for
> 2025-26 (NBA API blocked, cannot re-harvest) -- never silently reused."
>
> "DESCRIPTIVE/SCOUTING ranking only -- no forecast, no market claim, no dollar edge."
>
> "validity ladder [T2_PREDICTIVE] ... verdict=PREDICTIVE_VERIFIED mean_rho_metric=0.2889 n_folds=6"
>
> "Weights DECLARED and FROZEN before scoring ... never tuned to a named player's rank."

The pitch here is what the envelope does *not* hide. The composite says Murray, but the
engine surfaces that its component axes disagree: `shooter_quality_v1` tops out at Kevin
Durant (flagged `not_qualifying`), `fg3a_share` tops at Malik Beasley, and the rest-split
axis tops at Christian Braun. A confident single-name answer would have buried three rival
conclusions; instead they ride along with the answer. And `edge_claimed: false`, with weights
frozen before scoring so the ranking can't be reverse-fit to a name.

## Exchange 3 -- in-game repricing that tells on itself

Ask: `win_probability(nba, Nuggets vs Lakers)`, in-game, 36 minutes elapsed, score 88-95.

- Pregame `p_home_win` **0.5855**, framed *"Pregame MATCHES the devigged close ... No $ edge."*
- In-game `p_home_win` **0.3013** -- down 7 entering Q4 flips the favorite -- in state bucket
  `lead_-05_10|rem_12_24|reg`.
- `bucket_calibration`: `can_price` true, `n_games` 615, **model_brier 0.2328**, **market_brier 0.1985**.
- `honest_note`: *"A live book also sees the score. Forecaster quality, no $ edge."*

This is the whole demo in one envelope. The system reprices the game live -- and in the same
response discloses that in *this* bucket, over 615 games, the market's Brier (0.1985) is
lower than the model's (0.2328). The market is sharper here, and the engine says so, out
loud, in real time, unprompted. A system that reports its own losses against the benchmark is
one you can trust when it reports a win.

---

## How to reproduce

Full instructions: [docs/USE_WITH_CLAUDE.md](../USE_WITH_CLAUDE.md). In short:

1. **Clone** `git clone https://github.com/neeljshah/court-vision.git && cd court-vision`.
   A fresh clone ships with no `data/`.
2. **Install the data-pack** (one command):
   `python scripts/platformkit/publish_pack/install_pack.py`. It downloads the latest
   published snapshot into `data/`, refuses to overwrite anything you have, and prints your
   env setup plus the exact Claude config snippet.
3. **Connect Claude.** For Claude Code, save the printed JSON as `.mcp.json` at the repo root
   (it's gitignored, so a clone ships none) and approve `courtvision` when prompted. For
   Claude Desktop, add the `mcpServers.courtvision` block (Settings > Developer > Edit Config)
   with your absolute path -- the installer fills it in.
4. **Smoke test** three questions: *"Use system_health to show the snapshot date"*, *"Give me
   a scouting report for a well-known NBA player"*, and *"What is the claim survival rate?"*.
   Each answers with a `source_artifact` and `as_of`, or returns an honest `no_data`.

The pack is descriptive intelligence only. No betting data, no scraped odds, no live updates
-- questions that need what's absent degrade to `no_data` by design.

---

## Why this matters

Fail-closed answer engines are exactly what AI-engineering teams are trying to build right
now: an LLM that can only relay validated facts, cannot hallucinate a number, and admits when
it doesn't know. Retrieval-augmented chat usually means "the model paraphrases some documents
and hopes." This is the harder version -- every tool returns a typed envelope, the model is
contractually bound to honor the `status`, the numbers carry their own provenance and sample
size, and the honesty rails (`edge_claimed: false`, the caveat ladder, the market-sharper
disclosure) are enforced by the server, not the prompt. The demo isn't that the model gives
good answers. It's that the model *cannot* give a dishonest one -- and when the market beats
the model, the model is the first to tell you. That fail-closed contract, not any single
forecast, is the transferable engineering.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
