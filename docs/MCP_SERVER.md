# CourtVision MCP Server

An [MCP](https://modelcontextprotocol.io) stdio server that exposes CourtVision's
fail-closed sports-intelligence engine to any MCP client -- Claude Code, Claude
Desktop, or any other AI. One process, nine tools, the same honest envelope every
CLI and human path already gets.

**Entry point:** `scripts/platformkit/mcp_server/server.py`
**Run:** `python -m scripts.platformkit.mcp_server.server`

The MCP wire protocol is JSON-RPC 2.0 over stdio, so this ships without the `mcp`
SDK: a minimal newline-delimited JSON-RPC loop implementing `initialize`,
`tools/list`, and `tools/call`. The server module imports light (no pandas); every
backing engine is lazy-imported inside its handler, so a resident process stays
under ~100MB until a tool is called.

## Honesty rails (mirror docs/AI_CONSUMER_CONTRACT.md)

Every tool returns the standard **fail-closed envelope** as JSON text:

```
{status: ok | no_data | not_supported | refused | ambiguous,
 category, sport, source_artifact, as_of, ...category-specific fields}
```

The caller MUST honor `status` verbatim -- never soften a refusal into a hedge:

| status          | meaning                                              | what the caller does                          |
|-----------------|------------------------------------------------------|-----------------------------------------------|
| `ok`            | resolver answered                                    | quote numbers verbatim; cite `source_artifact` + `as_of` |
| `no_data`       | backing artifact absent/empty                        | say NO_DATA; do NOT fill from model memory    |
| `not_supported` | no resolver registered for this question type        | stop; never improvise                         |
| `refused`       | edge/ROI/retracted-number language, or a stale receipt | refuse; cite `.claude/rules/no-edge-claims.md` |
| `ambiguous`     | multiple candidates                                  | disambiguate before answering                 |

This engine produces **calibrated numbers and verified analytics, not a profit
claim.** No dollar-edge / ROI / beat-the-market language, ever. See
[AI_CONSUMER_CONTRACT.md](AI_CONSUMER_CONTRACT.md) for the full contract and
[.claude/rules/no-edge-claims.md](../.claude/rules/no-edge-claims.md) for the
retracted-number list.

## Tools

| Tool | What you get |
|------|--------------|
| `ask` | **Universal front door.** Any natural-language sports question, routed through the resolver (20 registered categories: player_stat, rating_attribute, concept_rating, prediction_winprob, calibration_number, historical_result, mechanism_effect, ranking, injury/news/schedule context, scouting, comparables, matchup_preview, analytics receipts). |
| `scouting_report(sport, player)` | Multi-axis descriptive scouting vector: per-concept rating+percentile, shooting facet, raw attributes. Never collapsed to one number. |
| `comparables(sport, player, k)` | K nearest players by RMS-normalized Euclidean distance over shared attribute percentiles. |
| `matchup_preview(sport, home, away)` | Fan-out preview: win prob + both profiles + style matchup + injuries + schedule context. Blocks that are absent are named in `blocks_absent`. |
| `win_probability(sport, home, away, ingame_state?)` | Calibrated pre-game or in-game win probability, quoted verbatim off `predict_matchup`. A calibrated probability, not an edge. `ingame_state` must be COMPLETE for the sport or it is silently dropped (pregame is returned instead, same `p_home_win`): `nba`/`wnba`/`soccer` need `elapsed, home_score, away_score`; `mlb` needs `inning, half, home_score, away_score`; `tennis` needs `sets_home, sets_away` (optionally `games_home, games_away, surface`). |
| `injury_report(sport, team_or_player)` | Newest-first injury rows off the fact store, 7-day staleness gate. |
| `analytics_receipts(kind)` | Verified-analytics ledger views: `attribution`, `claim_survival`, `verification`, `contradictions` (can be a large full conflict dump), `system_map`. |
| `run_burst(steps?, skip_slow?)` | **Executes a maintenance burst -- takes minutes, hits the network, writes to disk.** Not a query. `line_snapshot`/`settle_sweep`/`feed_health` are network-slow; `pnl_bestbets`/`analytics_verify`/`freshness_sla` are cheap/local-only (`skip_slow=true` runs just those three). Returns `{status: ok\|aborted, steps: [...], ...}`. |
| `system_health` | Cheap read-only status: last burst report, freshness-SLA summary, fleet on/off. No network, no compute. |

## Example: request / response

Request (two newline-delimited JSON-RPC messages on stdin):

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ask","arguments":{"query":"what is the claim survival rate?"}}}
```

Response for id 2 (the `content[0].text` is the envelope):

```json
{
  "status": "ok",
  "category": "analytics_claim_survival",
  "sport": "nba",
  "source_artifact": "data/cache/analytics_verify/claim_survival.json",
  "as_of": "2026-07-17T04:09:08Z",
  "n_cards_total": 138,
  "n_eligible": 0,
  "survival": {"7d": null, "30d": null, "60d": null},
  "honest_note": "Calibration/CLV re-grading of already-validated claims. No dollars, no ROI, no edge."
}
```

## Add to Claude Code

The repo `.mcp.json` already declares it (project-scoped):

```json
{
  "mcpServers": {
    "courtvision": {
      "command": "python",
      "args": ["-m", "scripts.platformkit.mcp_server.server"],
      "env": {"PYTHONPATH": "."}
    }
  }
}
```

Open the repo in Claude Code and approve the `courtvision` server when prompted.
The tools appear as `mcp__courtvision__ask`, etc.

## Add to Claude Desktop

Add to `claude_desktop_config.json` (Settings -> Developer -> Edit Config),
using an absolute path so it runs from the repo root:

```json
{
  "mcpServers": {
    "courtvision": {
      "command": "python",
      "args": ["-m", "scripts.platformkit.mcp_server.server"],
      "cwd": "C:/path/to/nba-ai-system"
    }
  }
}
```

Restart Claude Desktop; the CourtVision tools appear in the tool picker.

## Tests

`tests/platformkit/mcp_server/test_server.py` drives the real subprocess over
stdio (initialize -> tools/list -> tools/call), asserts all nine tools and their
descriptions, checks that an absent artifact yields a `no_data` envelope rather
than a protocol error, and asserts the server module imports without pandas.

```
python -m pytest tests/platformkit/mcp_server/test_server.py -q
```

---
**See also:** [AI_CONSUMER_CONTRACT.md](AI_CONSUMER_CONTRACT.md) - the binding
contract every AI consumer follows.
