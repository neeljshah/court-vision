# sports_predictor MCP Server + Track-Record Ledger / Drift Monitor

_Design doc, 2026-06-16. For: roadmap 01-claude-mastery item "custom sports_predictor stdio MCP server" (Layer 1, step 9) + roadmap X3 "calibration drift monitor + public track-record ledger". Build location: PART A -> `scripts/platformkit/mcp_server/`; PART B -> `scripts/platformkit/ledger/` (code, git-tracked) writing to `vault/_TrackRecord/` (data, gitignored). Design doc only -- no code edited._

This blueprint has two tightly-coupled halves. PART A exposes the EXISTING predictor as MCP tools so any MCP host (Claude Code, CI agent, IDE) calls it with zero re-integration. PART B is the append-only ledger that every prediction (including the MCP server's) writes to, plus the weekly drift check. The ledger is the validation artifact; the LLM never emits the probability -- the quant pipeline (`predict_matchup.build_result`) does, and the ledger records it verbatim.

---

## Goal + done-criteria (measurable)

### PART A -- sports_predictor MCP server
"Shipped + validated" means:
1. `python -m scripts.platformkit.mcp_server.sports_predictor` starts a stdio MCP server that responds to `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read` per MCP protocol (JSON-RPC 2.0).
2. `tools/list` returns exactly four tools: `predict_pregame`, `predict_ingame`, `calibration_report`, plus `list_sports` (trivial discovery helper). `resources/list` returns the `edge_map://` resource.
3. `tools/call predict_pregame {"sport":"nba","home":"BOS","away":"LAL"}` returns the SAME JSON dict that `predict_matchup.build_result(...)["pregame"]` produces today -- byte-identical fields, `edge_claimed:false`, `honest_note` present. The server shells into the existing predictor; it does NOT recompute any probability.
4. On a fresh clone with no corpus, every tool returns `{"available": false, "note": <the _UNAVAILABLE string>}` and exit code stays 0 (never raises, never fabricates a number).
5. The server is registered in a project `.mcp.json` (project-scoped, NOT user `~/.claude.json`), so a teammate / future session inherits it by opening the repo.
6. A per-file test `scripts/platformkit/mcp_server/test_sports_predictor.py` drives the server in-process (no subprocess) and asserts 1-4. Runs in < 5s.

Done-criteria explicitly NOT in scope for A: remote HTTP transport, OAuth, the Sampling primitive. Stdio + local only (see invariants).

### PART B -- track-record ledger + drift monitor
"Shipped + validated" means:
1. Every call to the predictor (CLI or MCP) appends ONE row per prediction to `vault/_TrackRecord/predictions.parquet` (mirrored to `predictions.csv` for human/skeptic diff) with the schema below. Append is atomic (write temp + os.replace) and idempotent on `pred_id`.
2. A grading step `grade_outcomes.py` joins open predictions to realized outcomes (from the existing per-sport corpus) and fills `outcome`, `graded_at`, leaving market `devig_close_prob` where capturable.
3. A headless weekly drift check `drift_check.py` computes recent-window Brier + ECE per (sport, market, layer) and compares to a 30-day rolling baseline; emits an ALERT row when recent Brier rises > 1 sigma of the rolling-window Brier distribution. Exit code 2 on alert (so a cron / `-p` run is detectable), 0 otherwise. Writes `vault/_TrackRecord/drift_report.md`.
4. Reproducibility: a skeptic running `python -m scripts.platformkit.ledger.replay_proof` on the committed fixture ledger (`tests/fixtures/ledger_demo.csv`) recomputes the same Brier/ECE/DM numbers in < 30s. The fixture ledger is git-tracked; the live ledger is gitignored.
5. The drift check NEVER writes a probability and NEVER edits a prediction row -- it only reads + appends to a separate `drift_log.parquet`. Predictions are append-only and immutable once written.

The trust moat: an append-only, timestamped, hash-pinned, multi-month calibration record that a skeptic reproduces from committed scripts. This is worth more than any single model upgrade (Good Judgment Project pattern) and is the thing that makes "best predictions" a verifiable claim rather than a slogan.

---

## Design

### Data flow (both parts)

```
                         scripts/platformkit/predict_matchup.build_result()   <-- the ONE number source
                                          |  (returns dict; edge_claimed:false)
              +---------------------------+---------------------------+
              |                                                       |
   PART A: MCP server (stdio)                              PART B: ledger.append_prediction()
   tools/call -> build_result() -> JSON back to host       row -> vault/_TrackRecord/predictions.parquet
              |                                                       |
        (server ALSO calls ledger.append on every                    | (later)
         tools/call so MCP predictions are logged too)        grade_outcomes.py  (joins realized outcome)
                                                                      |
                                                              drift_check.py (weekly, headless)
                                                               -> drift_log.parquet + drift_report.md
                                                               -> exit 2 on >1-sigma Brier rise
```

Key seam: BOTH the MCP server and the ledger call into `predict_matchup`/`predictor_jd`. Neither reimplements prediction. The LLM (the MCP host) only sees the returned numbers; it cannot author them.

### PART A directory layout (all NEW files, no collision with shared config)

```
scripts/platformkit/mcp_server/
  __init__.py
  sports_predictor.py        # the stdio server (<=300 LOC) -- tool/resource registration + shell into predict_matchup
  schemas.py                 # JSON Schemas for the 4 tool inputs (pure dicts, no corpus) (<=120 LOC)
  test_sports_predictor.py   # per-file test: in-process drive of the server
.mcp.json                    # project-scoped MCP registration  (HUMAN-CONFIRM before applying -- see Gotchas)
```

The server uses the official Anthropic `mcp` Python SDK (`pip install mcp`) with `FastMCP` for terse tool registration. It imports `scripts.platformkit.predict_matchup` (build_result / build_parser / _norm_sport / live_kwargs) and `predictor_jd._build_predictor` -- all already public and corpus-guarded. NO edit to predict_matchup is required; the server is a pure consumer.

Tool surface (mirrors roadmap text):
- `predict_pregame(sport, home, away, surface="Hard")` -> `build_result(...)["pregame"]` + provenance.
- `predict_ingame(sport, home, away, <live-state kwargs>)` -> `build_result(...)["ingame"]` (or `ingame_note` when state incomplete).
- `calibration_report(sport, market="ml", window_days=30)` -> reads the LEDGER (PART B) `compute_calibration(...)` and returns Brier/ECE/Resolution + market baseline + DM p-value. Read-only; no recompute of predictions.
- `list_sports()` -> `["nba","mlb","soccer","tennis"]` + availability flag per sport.

Resource surface:
- `edge_map://current` -> returns the text of `docs/research/edge-taxonomy.md` + `vault/_Edge_Maps/` (the per-sport edge map). Read as context BEFORE the host reasons. Read-only by MCP design.

Off-the-shelf MCP servers to add ALONGSIDE the custom one (registered in the same `.mcp.json`):

| Server | Scope | Why | R/W |
|---|---|---|---|
| Filesystem (official) | `data/` and `vault/` -- READ ONLY | Agents read parquet/JSON signal catalogs + intel notes as resources with zero file-I/O glue; honors the gitignore-data invariant by being RO | R only |
| SQLite (community fork, pinned) | a NEW `vault/_TrackRecord/results.sqlite` mirror of the ledger + calibration tables | Interactive `SELECT sport, brier FROM calib WHERE layer='pregame' ORDER BY brier` during research; faster than reading parquet by hand | R (point the fork at a read-only DB copy) |
| Memory (official, knowledge graph) | `vault/_TrackRecord/signal_memory.json` | Durable agent memory of which signals were tested/REJECTed and current Brier baselines -- stops agents re-running documented experiments | R/W (agent-owned, not prediction data) |

machina-sports/sports-skills note: per roadmap Layer-1 step, install `machina-sports/sports-skills` for its READ-ONLY sports data tools and its compute-only `betting` skill. It is a SKILL pack (Claude Skills), not an MCP server, so it composes with -- does not replace -- the `sports_predictor` MCP server: skills give the host scouting/data-fetch verbs; the MCP server gives it the calibrated number. Keep the `betting` skill compute-only and `disable-model-invocation:true` so the LLM never auto-bets.

### PART B directory layout

```
scripts/platformkit/ledger/
  __init__.py
  schema.py            # the LedgerRow dataclass + pyarrow schema + pred_id hashing (<=120 LOC)
  ledger.py            # append_prediction() / read_ledger() / atomic write (<=200 LOC)
  grade_outcomes.py    # join open preds -> realized outcomes from corpus (<=200 LOC)
  metrics.py           # brier/ece/resolution/dm_test (pure functions, no I/O) (<=180 LOC)
  drift_check.py       # weekly headless drift monitor -> exit code (<=200 LOC)
  replay_proof.py      # skeptic reproduction on committed fixture (<=120 LOC)
  test_ledger.py       # per-file test of append idempotency + schema
  test_metrics.py      # per-file test of brier/ece/dm on synthetic data with known answers
tests/fixtures/
  ledger_demo.csv      # ~120 graded rows (git-tracked) -> replay_proof reproduces the numbers
vault/_TrackRecord/    # GITIGNORED -- the live data lives here
  predictions.parquet  # append-only, immutable rows
  predictions.csv      # human/skeptic-readable mirror
  drift_log.parquet    # one row per drift_check run (append-only)
  drift_report.md      # latest human-readable drift summary
```

### Ledger row schema (the validation artifact)

| column | type | notes |
|---|---|---|
| pred_id | str | sha1(sport+home+away+market+layer+inputs_hash+pred_ts)[:16] -- idempotency key |
| pred_ts | iso8601 str | when the prediction was MADE (UTC); the vintage clock |
| sport | str | nba/mlb/soccer/tennis |
| layer | str | "pregame" or "ingame" |
| market | str | "ml" / "total" / "spread" / "over_2.5" / "p1_match_win" etc. |
| home | str | home team / p1 |
| away | str | away team / p2 |
| inputs_hash | str | sha1 of the FULL kwargs dict (incl live-state) -> reproducibility + dedup |
| model_version | str | git short-sha of HEAD at prediction time (provenance) |
| calibrated_prob | float | THE number, copied verbatim from build_result(); LLM never writes this |
| point_proj | float\|null | e.g. total_mean / proj_margin (for non-binary markets, scored separately) |
| game_date | str\|null | scheduled game date (for vintage check: pred_ts < game_date) |
| devig_close_prob | float\|null | Shin-devigged market close, filled at grading if capturable |
| outcome | int\|null | realized binary outcome (1/0); null until graded |
| graded_at | iso8601 str\|null | when outcome was filled |
| game_id | str\|null | cluster key for clustered SEs + DM blocking |

Append-only + immutable: a row is written once at prediction time with `outcome=null`; grading only fills `outcome/graded_at/devig_close_prob` via a separate pass that matches on `pred_id` and refuses to overwrite a non-null `outcome`. No other column is ever mutated.

---

## Implementation sketch (real, copyable)

### PART A -- sports_predictor.py (FastMCP)

```python
"""scripts.platformkit.mcp_server.sports_predictor -- stdio MCP server wrapping the predictor.
The quant pipeline computes every probability; this server only marshals it to MCP. No edge.
INVARIANTS: never edit src/kernel; reuse predict_matchup; <=300 LOC; stdio only (no auth/HTTP)."""
from __future__ import annotations
import argparse, pathlib
from mcp.server.fastmcp import FastMCP
from scripts.platformkit import predict_matchup as pm
from scripts.platformkit.ledger import ledger  # PART B
from scripts.platformkit.ledger import metrics

mcp = FastMCP("sports_predictor")
_REPO = pathlib.Path(__file__).resolve().parents[3]

def _run(argv: list[str]) -> dict:
    """Build the predictor + result EXACTLY as the CLI does, then log to the ledger."""
    a = pm.build_parser().parse_args(argv)
    sport = pm._norm_sport(a.sport)
    pred = pm._build_predictor(sport)
    if pred is None:
        return {"available": False, "note": pm._UNAVAILABLE}
    result = pm.build_result(sport, pred, a)        # <-- the ONE number source
    ledger.append_from_result(result, layer_filter=None)  # logs pregame + ingame rows
    result["available"] = True
    return result

@mcp.tool()
def predict_pregame(sport: str, home: str, away: str, surface: str = "Hard") -> dict:
    """Calibrated pre-game probabilities for a matchup. Matches the devigged close; NOT an edge."""
    out = _run(["--sport", sport, "--home", home, "--away", away, "--surface", surface])
    return out if not out.get("available") else {**out["pregame"], "framing": out["framing"]}

@mcp.tool()
def predict_ingame(sport: str, home: str, away: str, elapsed: float | None = None,
                   home_score: int | None = None, away_score: int | None = None,
                   inning: int | None = None, half: str | None = None,
                   sets_home: int | None = None, sets_away: int | None = None,
                   surface: str = "Hard") -> dict:
    """In-game probabilities conditioned on realized state -- the one honest departure from the close."""
    argv = ["--sport", sport, "--home", home, "--away", away, "--surface", surface]
    for flag, val in (("--elapsed", elapsed), ("--home-score", home_score),
                      ("--away-score", away_score), ("--inning", inning), ("--half", half),
                      ("--sets-home", sets_home), ("--sets-away", sets_away)):
        if val is not None:
            argv += [flag, str(val)]
    out = _run(argv)
    if not out.get("available"):
        return out
    return out.get("ingame", {"ingame_note": out.get("ingame_note")})

@mcp.tool()
def calibration_report(sport: str, market: str = "ml", window_days: int = 30) -> dict:
    """Brier/ECE/Resolution + devigged-close baseline + DM p-value from the LEDGER (read-only)."""
    df = ledger.read_ledger(graded_only=True)
    return metrics.compute_calibration(df, sport=sport, market=market, window_days=window_days)

@mcp.tool()
def list_sports() -> dict:
    return {s: (pm._build_predictor(s) is not None) for s in pm._SPORTS}

@mcp.resource("edge_map://current")
def edge_map() -> str:
    p = _REPO / "docs" / "research" / "edge-taxonomy.md"
    return p.read_text(encoding="utf-8") if p.exists() else "edge map unavailable on this clone"

if __name__ == "__main__":
    argparse.ArgumentParser(prog="sports_predictor").parse_args()  # no flags; stdio only
    mcp.run()  # stdio transport (default)
```

### PART A -- .mcp.json (project-scoped; HUMAN-CONFIRM before writing -- shared config)

```json
{
  "mcpServers": {
    "sports_predictor": {
      "command": "python", "args": ["-m", "scripts.platformkit.mcp_server.sports_predictor"],
      "env": {"PYTHONPATH": "."}
    },
    "fs_data_ro": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./data", "./vault"]
    },
    "results_sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "./vault/_TrackRecord/results.sqlite"]
    },
    "signal_memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {"MEMORY_FILE_PATH": "./vault/_TrackRecord/signal_memory.json"}
    }
  }
}
```
Filesystem server is pointed at `./data` and `./vault` ONLY (least privilege; never `/` or repo root) and is treated as read-only by convention -- the SQLite DB it would write through is a separate disposable mirror, and prediction parquets are written ONLY by `ledger.py`, never by an MCP host. SQLite `--db-path` is a read mirror; do not give an agent write access to prediction tables.

### PART B -- ledger.py (atomic append)

```python
def append_from_result(result: dict, layer_filter=None) -> list[str]:
    """Turn a predict_matchup.build_result() dict into ledger rows and append. Returns pred_ids."""
    rows = []
    for layer in ("pregame", "ingame"):
        block = result.get(layer)
        if not block or (layer_filter and layer != layer_filter):
            continue
        for market, prob in _iter_binary_markets(result["sport"], block):  # ml, total-over, etc.
            rows.append(_build_row(result, layer, market, prob))
    _atomic_append(rows)   # write temp parquet of (existing + new), os.replace; dedup on pred_id
    _mirror_csv()
    return [r["pred_id"] for r in rows]

def _atomic_append(rows):
    path = _LEDGER_PARQUET
    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=SCHEMA_COLS)
    new = pd.DataFrame(rows)
    merged = pd.concat([existing, new]).drop_duplicates("pred_id", keep="first")  # idempotent
    tmp = path.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False); os.replace(tmp, path)
```

### PART B -- metrics.py (pure; the proper-scoring core)

```python
def brier(p, y):  return float(np.mean((p - y) ** 2))

def ece(p, y, n_bins=10):                       # equal-WIDTH bins, 10 default (state it!)
    edges = np.linspace(0, 1, n_bins + 1); idx = np.digitize(p, edges[1:-1])
    e = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            e += (m.mean()) * abs(y[m].mean() - p[m].mean())
    return float(e)

def murphy(p, y, n_bins=10):                     # Reliability - Resolution + Uncertainty
    ...  # returns dict(reliability=, resolution=, uncertainty=)

def dm_test(loss_a, loss_b):                     # Diebold-Mariano on per-game Brier loss
    d = loss_a - loss_b                          # a=model, b=devigged close
    n = len(d); hac = _newey_west_var(d)         # HAC variance for temporal autocorr
    stat = d.mean() / np.sqrt(hac / n)
    return {"dm_stat": float(stat), "p_value": float(2 * (1 - norm.cdf(abs(stat)))), "n": n}

def compute_calibration(df, sport, market, window_days):
    sub = df[(df.sport == sport) & (df.market == market) & df.outcome.notna()]
    recent = sub[sub.pred_ts >= (now() - timedelta(days=window_days))]
    p, y = recent.calibrated_prob.values, recent.outcome.values
    out = {"sport": sport, "market": market, "n": len(recent), "brier": brier(p, y),
           "ece": ece(p, y), **murphy(p, y), "edge_claimed": False}
    mkt = recent.devig_close_prob.dropna()
    if len(mkt) >= 50:                            # only claim a "beat" with power
        la = (recent.loc[mkt.index].calibrated_prob - recent.loc[mkt.index].outcome) ** 2
        lb = (mkt - recent.loc[mkt.index].outcome) ** 2
        out["vs_close"] = dm_test(la.values, lb.values)   # p<0.05 AND lower Brier => beat
        out["market_brier"] = brier(mkt.values, recent.loc[mkt.index].outcome.values)
    return out
```

### PART B -- drift_check.py (headless, exit-code-bearing)

```python
def main() -> int:
    df = ledger.read_ledger(graded_only=True)
    alerts = []
    for (sport, market, layer), g in df.groupby(["sport", "market", "layer"]):
        daily = g.set_index("graded_at").calibrated_prob  # bucket per day
        rolling = _rolling_daily_brier(g, window=30)       # 30-day rolling baseline series
        recent = _window_brier(g, days=7)                  # recent 7-day Brier
        sigma = rolling.std()
        if sigma > 0 and (recent - rolling.mean()) > sigma:   # >1-sigma RISE in Brier = worse
            alerts.append({"sport": sport, "market": market, "layer": layer,
                           "recent_brier": recent, "baseline": rolling.mean(), "sigma": sigma})
    _append_drift_log(alerts)                  # vault/_TrackRecord/drift_log.parquet (append-only)
    _write_report(alerts)                      # drift_report.md
    return 2 if alerts else 0                   # exit 2 -> cron/-p run + PushNotification fires
```

Scheduling (headless, NO new shared-config edit required): run via the deferred `schedule`/`CronCreate` cloud-agent tool OR a local Task Scheduler entry calling
`python -m scripts.platformkit.ledger.drift_check`. On exit 2, fire `PushNotification`. Document both; do NOT auto-install a cron without human confirm.

---

## Validation plan (leak-free)

PART A (MCP server) -- correctness, not statistics:
- `test_sports_predictor.py`: drive the FastMCP server in-process; assert `tools/list` == the 4 names; assert `predict_pregame` output dict EQUALS `predict_matchup.build_result(...)["pregame"]` for a stubbed predictor (monkeypatch `_build_predictor` to a deterministic fake); assert the no-corpus path returns `available:false` and never raises. Per-file pytest only (full suite freezes the box).
- Manual: `claude mcp list` shows `sports_predictor`; a tools/call from the host returns the same JSON the CLI prints.

PART B (ledger / drift) -- the real statistical bar:
- Leak-free by construction: every row stores `pred_ts` and `game_date`; `grade_outcomes.py` asserts `pred_ts < game_date` (vintage alignment) and DROPS + flags any row that violates it (a logged leak, not a silent pass). Calibration is computed only on `outcome.notna()` rows.
- Metric + test + threshold: per (sport, market, layer) report Brier with 95% CI clustered by `game_id` (cluster-robust SE), Murphy decomposition (Reliability must fall AND Resolution stay >= market), ECE (10 equal-width bins, stated), and the DM test vs the Shin-devigged close. "Beats the close" claim requires DM p < 0.05 AND lower Brier AND N >= 200 -- otherwise it is logged as an honest REJECT (a success, not a failure).
- >= 2 corpora: run the whole calibration on TWO independent corpora per sport (e.g. NBA two disjoint seasons; MLB current + Retrosheet). A win on one season only is an artifact and is rejected.
- Drift threshold: recent 7-day Brier rise > 1 sigma of the 30-day rolling daily-Brier distribution -> ALERT (exit 2). Tune sigma multiplier only with a backtest on the fixture ledger to target a sane false-alarm rate (~1/month); do not hand-set it to suppress alerts.
- replay_proof.py validates reproducibility: a skeptic recomputes Brier/ECE/DM on the committed `tests/fixtures/ledger_demo.csv` and gets the identical numbers in < 30s. The fixture is the public proof; the live ledger is the private compounding asset.

---

## Effort + sequencing (rough days; dependencies)

1. PART B `schema.py` + `ledger.py` + `metrics.py` + their two per-file tests -- FIRST (1.5 days). Everything else logs into it; metrics are reused by the MCP `calibration_report` tool. No external deps beyond pandas/pyarrow/numpy/scipy (already present).
2. PART B `grade_outcomes.py` + the fixture ledger + `replay_proof.py` (1 day). Now the validation artifact reproduces.
3. PART A server `schemas.py` + `sports_predictor.py` + test (1 day). Depends on PART B ledger (the server logs every call). Requires `pip install mcp`.
4. PART B `drift_check.py` + report + scheduling doc (0.5 day). Depends on graded rows existing.
5. `.mcp.json` + off-the-shelf servers wiring -- LAST, HUMAN-CONFIRM (0.5 day). Total ~4.5 days, matching the X3 "3-5 days" estimate plus the MCP wrapper.

Do PART B before PART A: the ledger is the substrate; the MCP server is a client of it. Build the number-recorder before the number-server.

---

## Gotchas + how the honest discipline applies

- THE NUMBER NEVER COMES FROM THE LLM. The MCP host (Claude) calls `predict_pregame`; the tool body shells into `build_result()` (the quant pipeline) and returns its dict verbatim. The ledger copies `calibrated_prob` straight from that dict. There is no path where an LLM token becomes a logged probability. This is the load-bearing invariant -- preserve it even when adding tools.
- edge_claimed stays false everywhere. The MCP tool docstrings, the `framing` field, and the `honest_note` all carry the "matches the devigged close; in-game adds realized state; no $ edge" framing. A `calibration_report` that finds DM p >= 0.05 returns an honest REJECT, surfaced as such -- not buried.
- Append-only / immutable predictions. Grading fills `outcome` once and refuses to overwrite. Never "correct" a logged prediction; a wrong-looking past prediction IS the track record. Mutating it destroys the trust moat.
- Vintage / leak guard. `pred_ts < game_date` is asserted at grading; violators are flagged + dropped, logged as leaks. The ledger's value is that it is leak-free BY TIMESTAMP, not by re-derivation.
- Local-only, no shared-config collision. All new code is under `scripts/platformkit/` (allowed; <=300 LOC/file; per-file tests). The live ledger writes to `vault/_TrackRecord/` (gitignored). The ONLY shared-config touch is the project `.mcp.json` -- flag it HUMAN-CONFIRM and do not write it from an autonomous wave (the active branch `fullsend-ingame-pregame-execution` may be editing in-game code; a new top-level `.mcp.json` is additive and shouldn't collide, but a human should confirm before it lands). Do NOT edit `.claude/settings.json`.
- MCP security: stdio server inherits full OS privileges -> point Filesystem at `./data`+`./vault` ONLY (never repo root), treat it RO, never give an MCP host write to prediction parquets. No remote/HTTP/OAuth in this design; no Sampling primitive (recursive LLM loops are unauditable). Log every `tools/call`.
- No native parquet MCP server exists -> the custom server returns JSON from `build_result()` directly, and the optional SQLite mirror (a disposable copy) gives ad-hoc query access. Do not expose the live parquet through a writable server.
- Box constraints: never run bare `pytest tests/` (freezes the box) -- per-file tests only. Pin the community SQLite/Memory server versions (official churn). bash cwd is flaky -> prefix commands with `cd /c/Users/neelj/nba-ai-system &&`.
- ECE binning is a footgun: state "10 equal-width bins" everywhere and never optimize ECE directly (not a proper score) -- it is a diagnostic alongside the reliability diagram; the bar is Brier/log-loss + DM.
