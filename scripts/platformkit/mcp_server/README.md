# sports_predictor MCP server (SKELETON)

A stdio [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the
system's **read-only, calibrated** predictor to an MCP client. The model chooses the matchup
or in-game state; the **deterministic predictor computes every number**. The LLM never
authors a figure.

Honest framing only (the same line the predictor itself holds): pregame **matches** the
devigged close (calibration / sharpness, not a fabricated edge); in-game **adds** the realized
state through the validated repricer + in-game recalibrator. **No `$` edge is ever claimed.**

## Status: skeleton, not wired

- The `mcp` SDK is an **optional** import. Without it the module still parses and its pure
  helpers (`predict_pregame`, `predict_ingame`, `calibration_report`, `read_edge_map`) work
  and are unit-testable; only `serve()` requires the SDK.
- This file is **additive and inert**. It is **not** registered in `.mcp.json`. Enabling is a
  human step (see the proposed snippet below).

## Tools (each SHELLS the existing CLI -- never re-implements a model)

| Tool | Shells | Returns |
|------|--------|---------|
| `predict_pregame(sport, home, away)` | `python -m scripts.platformkit.predict_matchup --sport <s> --home <h> --away <a> --json` | the CLI's verbatim JSON surface |
| `predict_ingame(sport, state)` | the same CLI with in-game flags derived from `state` (`elapsed`, `inning`, `half`, `home_score`, `away_score`, `sets_home`, `games_home`, `surface`, ...) | the CLI's verbatim in-game JSON |
| `calibration_report(sport)` | `python -m scripts.platformkit.recal_report` | the report sliced to one sport |

`sport` is one of `nba`, `mlb`, `soccer`, `tennis` (alias `basketball_nba` -> `nba`).
On a fresh clone with no local/gitignored corpora, the underlying CLI exits 0 with an
"unavailable" note; the tools surface that note rather than an error.

## Resource

- `edge_map://<sport>` (or `edge_map://all`) -- read-only text from `vault/_Edge_Maps/` **if
  present**. The vault is local/gitignored; on a clone without it the resource returns a benign
  "unavailable" note. (A legacy copy lives under `_vault_legacy_archive/_Edge_Maps/`.)

## Run (after `pip install mcp`)

```
python -m scripts.platformkit.mcp_server.sports_predictor_server
```

It speaks MCP over stdio; point an MCP client at the command above. Without the SDK it prints
a guidance note to stderr and exits 1.

## Enabling (HUMAN-CONFIRM)

No proposed registration snippet exists yet. A human writes the entry (command +
args pointing at `sports_predictor_server`) and merges it into the real `.mcp.json`
(this skeleton does **not** create or edit the live `.mcp.json`).

## Invariants

Read-only; never authors numbers; never edits `src/` or `kernel/`; `<=300` LOC; ASCII only;
no secrets; degrades cleanly when corpora/vault are absent.
