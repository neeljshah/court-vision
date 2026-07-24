# CourtVision MCP -- Quickstart (zero to connected)

Connect the CourtVision **fail-closed sports-intelligence** MCP server to Claude in
under five minutes. You need a Claude subscription (Claude Code CLI or Claude
Desktop) and Python 3.10+.

The server is a **read-only oracle**: every answer is a typed envelope with
`status` (`ok` / `no_data` / `not_supported` / `refused`), a `source_artifact`,
and an `as_of` timestamp. It never answers from model memory and never claims a
dollar edge -- an honest `NO_DATA` is a correct answer, not a failure. See
[docs/AI_CONSUMER_CONTRACT.md](AI_CONSUMER_CONTRACT.md).

> Replace `<REPO_ROOT>` below with the absolute path to your clone
> (e.g. `C:\Users\you\nba-ai-system` or `/home/you/nba-ai-system`).

---

## 1. Clone + Python env

```bash
git clone <this-repo-url> nba-ai-system
cd nba-ai-system
python --version            # must be 3.10 or newer

# minimal deps the server actually uses (the repo already pins these):
python -m pip install pandas numpy
# optional: pyarrow -- only for the parquet-backed tools, which are NO_DATA
# on a fresh clone anyway (see section 6). Skip it for the demo.
```

The server process itself imports **only the Python standard library** -- it
starts with zero third-party deps. `pandas`/`numpy` are pulled lazily the first
time you call a data tool. No compiler, no GPU, no network needed to launch it.

Sanity-check it runs (Ctrl-C to exit -- it waits on stdin):

```bash
python -m scripts.platformkit.mcp_server.server
```

If that prints nothing and blocks, it is working (it is a stdio JSON-RPC loop).

---

## 2. Claude Code (CLI)

One command from inside the repo root:

```bash
claude mcp add courtvision --env PYTHONPATH=. -- python -m scripts.platformkit.mcp_server.server
```

Or drop this `.mcp.json` at `<REPO_ROOT>/.mcp.json` (already checked in -- Claude
Code auto-loads it when you launch `claude` from the repo root):

```json
{
  "mcpServers": {
    "courtvision": {
      "command": "python",
      "args": ["-m", "scripts.platformkit.mcp_server.server"],
      "env": { "PYTHONPATH": "." }
    }
  }
}
```

`PYTHONPATH=.` lets `python -m scripts...` resolve the package; **launch `claude`
from `<REPO_ROOT>`** so the relative path anchors correctly (see the cwd
troubleshooting row). Verify with `/mcp` inside Claude Code -- `courtvision`
should list 9 tools.

---

## 3. Claude Desktop

Edit `claude_desktop_config.json` (create it if absent):

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Desktop does **not** inherit a working directory, so pin `cwd` to the repo root:

```json
{
  "mcpServers": {
    "courtvision": {
      "command": "python",
      "args": ["-m", "scripts.platformkit.mcp_server.server"],
      "cwd": "<REPO_ROOT>",
      "env": { "PYTHONPATH": "." }
    }
  }
}
```

On Windows, if `python` is not on PATH, set `"command"` to your full interpreter
path (e.g. `C:\\Users\\you\\miniconda3\\python.exe`, doubled backslashes).
Restart Claude Desktop; the tools appear under the plug/tools icon.

---

## 4. First 5 questions (with expected envelope shapes)

Ask these in plain English. The model routes each through a CourtVision tool and
must quote the envelope verbatim. Shapes below are real outputs.

**1. Atlas card (works on a bare clone -- reads a committed manifest):**
> "Show the CourtVision atlas card for LeBron James."
```json
{ "status": "ok", "category": "atlas_card", "sport": "nba",
  "source_artifact": "scripts/platformkit/analytics_showcase/out/atlas_nba_manifest.json",
  "as_of": "..." }
```

**2. Refusal (edge/ROI language is refused by contract) -- shows the guardrail:**
> "What's the ROI of your best bets?"
```json
{ "status": "refused", "category": "edge_language",
  "source_artifact": ".claude/rules/no-edge-claims.md" }
```
The model must refuse and cite the rule -- it will NOT invent a profit number.

**3. Deliberate NO_DATA (fail-closed honesty) -- an unbuilt store on a clone:**
> "What's the latest injury report for the Lakers?"
```json
{ "status": "no_data", "category": "edge_facts_injury_report", "sport": "nba",
  "source_artifact": "data/cache/edge_engine/injury_facts_nba.jsonl",
  "note": "fact store not built in this clone" }
```
This is the point of the system: no fresh artifact -> it says **NO_DATA** and
names the missing file, instead of hallucinating an injury list.

**4. Win probability (calibrated number, not a market claim):**
> "Calibrated win probability, Lakers home vs Celtics."
```json
{ "status": "ok"|"no_data", "category": "prediction_winprob", "sport": "nba",
  "p_home_win": 0.xx, "source_artifact": "...", "as_of": "..." }
```
Returns `no_data` on a bare clone (Elo corpora live under gitignored `data/`).

**5. Analytics receipts (verified-claims ledger):**
> "Show the CourtVision claim-survival receipts."
```json
{ "status": "ok"|"no_data", "category": "analytics_receipts",
  "source_artifact": "data/cache/analytics_verify/claim_survival.json", "as_of": "..." }
```

Every answer names a `source_artifact` and `as_of`. If one doesn't, it's
non-compliant -- re-ask.

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `python: command not found` / server won't start | Python not on PATH | Install Python 3.10+; on Desktop set `"command"` to the full interpreter path (Windows: doubled backslashes). |
| Every tool returns a uniform `no_data` | Launched with the wrong cwd, so relative data roots miss | Launch `claude` from `<REPO_ROOT>` (CLI), or set `"cwd": "<REPO_ROOT>"` (Desktop). `PYTHONPATH=.` alone does not set cwd. |
| `ModuleNotFoundError: scripts...` | `PYTHONPATH` not set, or not run as a module | Keep `"env": {"PYTHONPATH": "."}` and the `-m scripts.platformkit.mcp_server.server` form; run from repo root. |
| `ModuleNotFoundError: pandas` / `numpy` on a data question | Deps not installed | `python -m pip install pandas numpy` (the server launches without them; data tools need them). |
| `courtvision` absent from `/mcp` or the tools icon | Config not picked up | CLI: confirm `.mcp.json` is at repo root and you launched from there. Desktop: fully restart the app after editing the config. |
| A tool takes minutes / hits the network | You invoked `run_burst` | That's the one write/network tool. For a read-only status use `system_health`, or pass `skip_slow=true` to `run_burst`. |

---

## 6. What ships in the clone vs. what stays NO_DATA (honest)

The public repo commits **code + a few JSON manifests**, not the private data
lake. So a fresh clone is a working *server* with mostly *empty shelves* -- and
it tells you so, per tool, instead of faking it.

**Works on a bare clone (committed artifacts):**
- `atlas_card` questions via `ask` -- reads committed `analytics_showcase/out/*_manifest.json`.
- `mechanism_effect` questions -- reads committed `domains/*/knowledge` ledgers.
- Any `refused` path (edge/ROI/retracted-number language) -- reads committed `.claude/rules/`.
- `system_health` -- returns `status: ok` with each block honestly `no_data`.

**Returns NO_DATA on a bare clone (data lives under gitignored `data/` + `vault/`):**
- `scouting_report`, `comparables` -- need `data/cache/profiles/*.parquet`.
- `injury_report` -- needs `data/cache/edge_engine/injury_facts_*.jsonl`.
- `analytics_receipts` -- needs `data/cache/analytics_verify/*.json`.
- `win_probability`, most `ask` stat/ranking/prediction categories -- need
  `data/domains/*.parquet` and Elo corpora.
- `matchup_preview` -- overall `status: ok`, but its sub-blocks report
  `blocks_absent` for the missing data pieces.

This is by design: the demo proves the **fail-closed contract** (honest
`NO_DATA` beats a confident guess). To light up the data tools you must build or
sync the local `data/` lake -- which is intentionally not part of the public
clone.

---
**See also:** [docs/AI_CONSUMER_CONTRACT.md](AI_CONSUMER_CONTRACT.md) (envelope
rules) - [.claude/rules/no-edge-claims.md](../.claude/rules/no-edge-claims.md)
(why nothing here claims a dollar edge).
