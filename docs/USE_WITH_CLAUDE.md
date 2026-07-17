# Use CourtVision with Claude

Run CourtVision's fail-closed sports-intelligence engine on your own machine and
ask Claude questions against it -- no server, no account, one command. What you
get is a **descriptive-intelligence snapshot**: validated claim families,
player/team profiles, and calibrated forecasts. It is a calibrated predictor,
**not** a betting product.

## 1. Clone

```
git clone https://github.com/neeljshah/court-vision.git
cd court-vision
```

A fresh clone ships with **no `data/`** -- the intelligence lives in a separate
data-pack you download in the next step.

## 2. Install the data-pack (one command)

```
python scripts/platformkit/publish_pack/install_pack.py
```

This downloads the latest published data-pack from GitHub Releases and unpacks it
into `data/`. It refuses to overwrite any file you already have (a first install
on a clean clone has nothing to clobber). To pull a newer snapshot later:

```
python scripts/platformkit/publish_pack/install_pack.py --update
```

The installer then prints your Python env setup and the exact Claude config
snippet. In short:

```
python -m venv .venv
# Windows:   .venv\Scripts\activate
# mac/linux: source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Connect Claude

**Claude Code** -- `.mcp.json` is gitignored (it's per-machine config), so a
fresh clone does **not** ship one. The installer prints the exact JSON to save
as `.mcp.json` at the repo root (step 2 output, section "2a"). Save it, reopen
the repo in Claude Code, and approve `courtvision` when prompted.

**Claude Desktop** -- Settings > Developer > Edit Config, then add (the installer
prints this with your absolute path filled in):

```json
{
  "mcpServers": {
    "courtvision": {
      "command": "python",
      "args": ["-m", "scripts.platformkit.mcp_server.server"],
      "cwd": "/absolute/path/to/court-vision"
    }
  }
}
```

Restart Claude Desktop; the CourtVision tools appear in the picker. Full server
docs: [MCP_SERVER.md](MCP_SERVER.md).

## 4. Smoke test (3 questions)

Ask Claude, once connected:

1. *"Use system_health to show the snapshot date."* -- confirms the pack loaded
   and tells you how fresh it is.
2. *"Give me a scouting report for a well-known NBA player."* -- a multi-axis
   descriptive vector with source and as-of.
3. *"What is the claim survival rate?"* -- an analytics receipt off the verified
   ledger views.

Each answer quotes real numbers with a `source_artifact` and `as_of`, or returns
an honest `no_data`.

## What it can answer

- **Scouting** -- per-concept ratings + percentiles, shooting facets, raw attributes.
- **Comparables** -- nearest players by shared attribute percentiles.
- **Matchup previews** -- win probability + both profiles + style + injuries + schedule.
- **Calibrated win probability** -- pre-game and in-game (a probability, not an edge).
- **Injury / schedule / historical context** off the descriptive fact stores.
- **Analytics receipts** -- attribution, claim survival, verification, system map.

## What returns `no_data` -- by design

The pack is descriptive intelligence only. These are **absent on purpose** and
the engine says `no_data` rather than inventing an answer:

- **No betting data** -- no ledgers, no CLV, no paper trades, no bankroll.
- **No scraped odds** -- no odds feeds, line history, or book depth.
- **No live updates** -- it is a snapshot. Check its date via `system_health`;
  today's games are not in it.
- **Some very large per-entity stores** are omitted to keep the pack
  laptop-friendly; questions that need them degrade honestly to `no_data`.

## Honesty rails

Every tool returns a fail-closed envelope with a `status` you should honor
verbatim: `ok`, `no_data`, `not_supported`, `refused`, `ambiguous`. This engine
produces **calibrated numbers and verified analytics, not a profit claim** -- no
dollar-edge, ROI, or beat-the-market language. See
[AI_CONSUMER_CONTRACT.md](AI_CONSUMER_CONTRACT.md) for the binding contract.
