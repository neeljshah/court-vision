# 12 - Data Inventory, Infrastructure, Ops, and the Planning Corpus

Deep-dive into what data actually exists on disk, how it is refreshed, the GPU/local
compute setup, the planning/docs corpus, and what real 24/7 always-on operation would
require. READ-ONLY survey; ASCII only.

Honesty rails honored throughout: markets are efficient; the honest win is CALIBRATION,
not a dollar edge; everything betting-side is PAPER-only. Numbers below are data shapes
and file sizes (verified live), never profit claims.

---

## 1. INVENTORY -- what exists and is used

### 1.1 Per-sport prediction corpora (the live, USED data)

These are the parquets the domain predictors actually read. Path config example:
`domains/mlb/config.py:212` `DATA_DIR_REL = "data/domains/mlb"`. Verified rowcounts
(read live 2026-06-18):

| Sport / file | Rows x cols | Date span | Notes |
|---|---|---|---|
| `data/domains/basketball_nba/games.parquet` | 4,846 x 12 | 2022-10-18 .. 2026-04-12 | team-game results |
| `data/domains/basketball_nba/player_boxscores.parquet` | 27,816 x 26 | 2024-10-22 .. 2026-01-19 | player props base |
| `data/domains/basketball_nba/asof_features.parquet` | (126KB) | thru 2026-06-13 | leak-free as-of features |
| `data/domains/mlb/games.parquet` (FROZEN SBR) | 27,983 x 10 | 2010-04-04 .. 2021-11-02 | historical Elo corpus |
| `data/domains/mlb/games_current.parquet` | 10,826 x 10 | 2022-04-07 .. 2026-06-16 | extends frozen corpus via free MLB StatsAPI |
| `data/domains/mlb/pitchers.parquet` | 27,983 x 11 | 2010 .. 2021 | pitcher-blind era only |
| `data/domains/mlb/player_gamelogs.parquet` | (99KB, refreshed 2026-06-18 08:46) | current | prop base |
| `data/domains/soccer/matches.parquet` | 25,834 x 11 | 2015-08-07 .. 2026-05-24 | club football (football-data.co.uk) |
| `data/domains/soccer/asof_features.parquet` | (3.3MB) | thru 2026-06-13 | largest as-of feature table |
| `data/domains/soccer_intl/results.parquet` | 49,477 x 9 | 1872-11-30 .. 2026-06-27 | full intl history (World Cup vertical) |
| `data/domains/tennis/matches.parquet` (ATP) | 30,616 x 20 | 2015-01-04 .. 2025-12-17 | Sackmann + tennis-data |
| `data/domains/tennis/wta_matches.parquet` | 11,270 x 20 | 2015-01-19 .. 2025-11-01 | WTA corpus |
| `data/domains/tennis/asof_features.parquet` | (4.8MB) | thru 2026-06-13 | largest single domain parquet |

Total `data/domains/` footprint: ~93MB. This is the genuinely-used, multi-sport
prediction surface and it is SMALL and tidy -- exactly the kind of compact corpus the
sport-blind kernel was built to validate.

Supporting per-domain artifacts that exist and are used:
- `odds.parquet` per domain (NBA/MLB/soccer/tennis) -- historical/captured lines.
- `postmortem.parquet` per domain -- settled prediction-vs-outcome rows for calibration.
- `paper_book/*.json` -- the PAPER bet ledgers: `data/domains/mlb/paper_book/paper_book_AL.json`
  (252KB) + `paper_book_NL.json` (323KB), `soccer/paper_book/paper_book.json` (20KB),
  `tennis/paper_book/paper_book.json` (12KB). These are the live paper-trade record.
- `odds_snapshots/snapshots.jsonl` under `basketball_nba`, `mlb_sbro`, `soccer_fd`,
  `tennis_atp` -- append-only line-capture logs for CLV.
- `data/frontend/snapshots/soccer_intl.json` -- the board snapshot the UI serves (written
  by `snapshot_writer`, refreshed by `refresh_daemon`).

### 1.2 NBA CV / tracking data (the heavy, legacy tier)

| Dir | Size | Content |
|---|---|---|
| `data/tracking/` | 6.5 GB | per-game `tracking_data.csv` + `features.csv` from the CV pipeline |
| `data/games/` | 759 MB | older per-game feature CSVs (e.g. `0022400625/features.csv` = 415MB) |
| `data/shadow/` | 1.6 GB | shadow/replay captures (single file `0042500316_2026-05-28.csv` = 1.58GB) |
| `data/models/` | 1.3 GB | trained model artifacts + ~25 timestamped `_backup_iterNN_*` dirs |

Largest single files on disk are CV feature CSVs (one game = 100-430MB). This tier is
the expensive, hard-to-refresh data; the per-sport parquets above are cheap by contrast.

### 1.3 Databases + state files

- `data/nba_ai.db` (8.7MB SQLite) -- legacy NBA store.
- `data/bets.db` (53KB SQLite) -- legacy bet ledger.
- `data/registry/` -- governance registry (NEVER write per rules): `SIGNAL_REGISTRY.md`,
  `calibration_registry/`, `domain_registry/`, `engine_registry/`, `foundry_scoreboard/`,
  `build_checks/`, `ensemble_weights_proposal.json`.
- Process pid/state files at repo root: `.pod_start_epoch`, `.budget_watchdog.pid`,
  `.sync_watchdog.pid`, `.video_upload.pid`, `.pending_uploads.txt`, `phase_g_processed.txt`,
  `phase_g_metrics.csv` (ingest done-tracking).

### 1.4 Legacy intelligence layer (mostly stranded -- see Limitations)

`data/intelligence/` holds ~99 parquets + ~50 JSON artifacts (atlases, archetypes,
correlation matrices, residual heads). `data/cache/` holds ~44 feature parquets.
`data/cache/profiles/DATA_INVENTORY.md` (auto-generated 2026-05-30) is the census doc.

### 1.5 Ops / docs / planning corpus

- `docs/operations/`: `runpod-runbook.md` (GPU ops), `data-pipeline.md`, `deployment.md`,
  `full-game-production.md`, `fresh-pod-bootstrap.md`, `new-pod-checklist.md`,
  `backfill-100-games.md`, `runpod_video_sync_notes.md`.
- `docs/CLAUDE-state.md` -- working-copy state mirror (local-only/gitignored).
- `.planning/` -- ~40 planning docs + subdirs (`platform/`, `intelligence/`, `brain/`,
  `ingame/`, `loop/`, `queue/`, etc.). `NOW.md` is the declared SINGLE SOURCE OF TRUTH;
  `ROADMAP.md` (~167KB) and `DATA_VISION.md` are the big plans.
- `docs/research/` -- proposals + this deep-dive (the human-gated "build here" area).

---

## 2. HOW IT WORKS -- data flow + key components

### 2.1 The refresh path (per-sport, keyless)

Each domain has 5-6 `ingest_*.py` modules (NBA 6, MLB 5, soccer 5, tennis 6) that pull
from FREE, keyless public sources and write only into `data/domains/<sport>/`:

- MLB: `domains/mlb/ingest_current.py` pulls FINAL results from `statsapi.mlb.com`
  (`sportId=1, gameType=R`, no key; browser UA required to avoid 406). It maps full team
  names onto the same non-standard SBR 3-letter codes the frozen 2010-2021 corpus uses so
  the two concatenate and the SAME `walk_forward_elo` replays across both. Leak-free:
  final games only, no in-progress scores.
- Tennis: `domains/tennis/ingest_sackmann.py` downloads Jeff Sackmann ATP/WTA CSVs from
  `raw.githubusercontent.com/JeffSackmann/tennis_atp|tennis_wta` (CC BY-NC-SA),
  idempotently (skip if present, size>0).
- Soccer: `ingest_footballdata*.py` (football-data.co.uk) + `ingest_espn_*` for player
  stats / WC rosters; `soccer_intl` results from a long-history results CSV.
- NBA: `ingest_boxscores/espn_box/espn_odds/linescores/quarter_box/schedule.py`.

Flow: `ingest_*` -> raw -> domain `asof_*` builders produce LEAK-FREE as-of feature
parquets (`asof_features.parquet`, `asof_box_extra`, `asof_runvar`, `asof_park`,
`asof_sp_form`, `asof_hold`) -> `predictor.py` / `ratings.py` consume them.

### 2.2 The board snapshot + refresh daemon

`scripts/platformkit/frontend/snapshot_writer.py:write_all(sports)` computes each sport's
board ONCE and writes it atomically to `data/frontend/snapshots/<sport>.json`. The server
(`serve.py`) does cheap reads of those snapshots.

`scripts/platformkit/frontend/refresh_daemon.py` keeps them fresh:
- `run_once(sports, writer)` (line 46) -- one tick; on ANY writer error it LOGS and
  returns `{}`, leaving last-good snapshots untouched (contract: "DEGRADE, NEVER DIE").
- `run_forever(interval_s=60.0, ...)` (line 65) -- loop; never raises.
Run: `python -m scripts.platformkit.frontend.refresh_daemon --interval 30 --sports ...`.

### 2.3 The always-on self-improving paper loop

`scripts/platformkit/pm_trading/auto_loop.py` -- one cycle = three guarded steps
(`run_once`, line 36):
1. `run_paper_cycle()` (run_paper_today) -- paper-trade today's real games into a CLV
   ledger, `executed=False`.
2. `grade_open_bets()` (grade_paper) -- grade finished games win/loss + CLV vs close.
3. `improve_all()` (self_improve) -- recalibrate on accumulated REAL outcomes, GATED by
   the eval-gate (only ever improve or hold).
Each step is wrapped so one failure never sinks the loop. Run forever:
`python -m scripts.platformkit.pm_trading.auto_loop --forever --interval 1200`.
This is the closest thing to a 24/7 brain today; it is PAPER-only and gets smarter
strictly as real games settle.

### 2.4 The GPU CV ingest pipeline (RunPod)

`docs/operations/runpod-runbook.md` is the distilled GPU runbook:
- Local dev: RTX 4060 (8GB). Production ingest: RunPod community RTX 3090/4090 (24GB),
  ~$0.34-0.50/hr.
- Verified spec: full game (194K frames) end-to-end in ~68 min, stability 1.000, ball
  ~79%, zero OOM; ~$0.10-0.13/game (one pod / 6 workers).
- Parallelism rule: `N ~= floor(VRAM_GB / 3.5)` -> 6 workers on a 24GB card (~3.3GB
  VRAM/worker). RAM becomes the limit on 40GB+ cards.
- Critical configs: `OMP/MKL/OPENBLAS/NUMEXPR_NUM_THREADS=6` (CFS quota ~17.85 cores --
  oversubscription caused ~3x throttling); `_VRAM_FLUSH_INTERVAL=3000` in
  `unified_pipeline.py` (100 forces GPU sync barriers -> 10x slowdown; launcher refuses
  to start if wrong); install `decord` (NVDEC) or PyAV CPU decode becomes bottleneck;
  stage videos to LOCAL SSD not NFS (NFS ~38x slower -> turns a 7h run into 60h);
  quarantine AV1 (no HW decode).
- Pod is NOT a git repo: code synced via `rsync --exclude data --exclude .git`. Pod
  disk is EPHEMERAL -- data must be pulled (`rsync data/tracking`, `scp queue.db`,
  `phase_g_processed.txt`) BEFORE pod stop, or auto-synced to B2 via
  `scripts/sync_remote.py --push`.

### 2.5 The planning corpus

`.planning/NOW.md` (declared SSOT, header `updated: 2026-06-17`): active milestone, a
`NEXT` list (max 5, action|where|done-when), `RECENT DONE`, and `Active blockers` (which
honestly record the negative paper ROI and cold-start improve verdict). `ROADMAP.md`
(~167KB, grep-only) is the long phase list; `DATA_VISION.md` the north-star data plan.

---

## 3. HOW IT IS USED -- callers / consumers

- Domain `predictor.py` / `ratings.py` / `prop_engine.py` read the `data/domains/<sport>/`
  parquets at predict time (config-driven paths).
- The FastAPI/serve frontend (`serve.py`, board at `http://127.0.0.1:8098/`) reads
  `data/frontend/snapshots/<sport>.json`; `refresh_daemon` writes them.
- `auto_loop.py` consumes the per-sport corpora + `odds_snapshots` and appends to
  `paper_book/*.json`, then feeds settled `postmortem.parquet` rows back into
  `self_improve` -> eval-gate.
- The eval-gate (`scripts/platformkit/eval_gate/`) consumes postmortem + golden sets to
  decide ship/hold on any recalibration.
- The CV pipeline (`src/pipeline/unified_pipeline.py`, RunPod) produces `data/tracking/`
  + `data/events/`, scored by `scripts/ingest_backfill_quality.py`, consumed by
  `scripts/build_residuals.py` / `train_cv_models.py`.
- Skills as user-facing entry points: `predict-matchup`, `calibration-report`,
  `cross-sport-benchmark`, `eval-gate`, `signal-audit`, `state-roadmap` -- all operate on
  the per-sport corpora + gate.
- `data/registry/` is read by governance/build-check tooling and is WRITE-FORBIDDEN to
  agents.

---

## 4. STRENGTHS

1. The genuinely-used data is small, clean, and multi-sport: ~93MB of `data/domains/`
   covering 4-5 sports, ~150K total result rows spanning back to 1872 (intl soccer). Easy
   to validate, cheap to refresh, trivially fits the 15GB box.
2. Keyless, free, idempotent refresh: MLB StatsAPI, Sackmann GitHub, football-data,
   ESPN. No paid API dependency; ingest modules skip-if-present and are leak-free
   (finals-only).
3. Frozen-corpus + current-extension pattern (MLB): the 2010-2021 SBR corpus stays
   frozen while `games_current.parquet` extends to 2026-06-16 under the SAME team codes so
   one walk-forward replays across both -- clean separation, no historical rewrite.
4. As-of leak-free feature design is pervasive (`asof_*` everywhere) -- the data layer
   was built with the leak-free discipline baked in, not bolted on.
5. Daemons degrade, never die: `refresh_daemon` and `auto_loop` both wrap every tick so
   a flaky feed yields slightly-stale data, never a dark screen or a dead loop.
6. RunPod runbook is battle-tested and specific: exact thread caps, VRAM flush value,
   NFS gotcha, ephemeral-disk pull discipline -- this is real operational knowledge, not
   aspirational.
7. Planning hygiene: a single declared SSOT (`NOW.md`) with honest blockers, plus
   human-gated-path rules that keep `src/`, `kernel/`, `api/`, `data/registry/` safe from
   autonomous edits.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS (brutally honest)

1. The `DATA_INVENTORY.md` census is STALE and MISLEADING. It is dated 2026-05-30 and
   reports nearly every parquet in `data/`, `data/cache/`, `data/intelligence/` as "0
   rows" (only `player_fingerprints*` show 221/230). Either the census ran against
   stripped local copies or these tables are genuinely empty -- either way the headline
   doc oversells a ~190-parquet "inventory" that is mostly empty shells.
2. Massive stranded NBA intelligence/CV tier. ~99 intelligence parquets + ~50 JSON +
   ~44 cache parquets + 6.5GB tracking + 1.6GB shadow + 1.3GB models. Most of this is the
   legacy NBA-only research surface; memory notes repeatedly flag the intelligence
   atlases as descriptive/scouting, not edge, and the CV signals as a noise wall (jersey
   OCR ~2.3% read). This is built-but-largely-unread relative to the current 4-sport
   product. Big disk, low current leverage.
3. Data depth is THIN for the active vertical. The World Cup prop vertical runs on 24
   matches; `NOW.md` itself records isotonic recalibration OVERFITS on that slice and was
   correctly held back, and opponent-adjustment measured NULL. soccer_intl has 49K rows
   of history but the modern prop layer is data-starved.
4. MLB pitcher data is era-limited: `pitchers.parquet` only covers 2010-2021 (frozen
   corpus). The 2022-26 extension is games-only (10,826 rows) with no matching pitcher
   table -> current MLB runs effectively pitcher-blind on recent seasons.
5. odds_snapshots are single-line / single-venue. `NOW.md` blocker: "Live odds limited
   to ESPN's single republished line until a 2nd venue matches -> no real arb yet." TRUE
   prop CLV is not yet computable (closing prop lines not captured).
6. No real always-on host. There is NO systemd/cron/VPS/cloud deployment for the
   self-improving loop. `auto_loop --forever` runs only while a terminal on the 15GB
   Windows box is open. ROADMAP Phase 21 ("Hetzner VPS cron") and Phase 34 ("MLOps,
   auto-retrain, drift alerts") are both unchecked (TODO).
7. Local box is fragile: 15GB RAM, full `pytest` freezes it (per-file tests only), GPU
   is an 8GB RTX 4060 -- can't run the CV pipeline locally at production scale. RunPod
   pods are ephemeral and must be manually pulled before stop or data is lost.
8. ~25 timestamped `data/models/_backup_iterNN_*` dirs (1.3GB) -- no clear retention/
   pruning policy; model artifact sprawl.
9. Two parallel data worlds with weak linkage: the legacy `data/` flat files +
   `nba_ai.db` + `bets.db` vs the new `data/domains/<sport>/` parquets + `paper_book`.
   The census doc only covers the legacy world; there is no single up-to-date manifest of
   the per-domain corpora (this report had to derive rowcounts live).
10. Refresh is manual / loop-driven, not scheduled. Nothing guarantees ingest ran today;
    freshness is whatever the last manual run or daemon tick produced (e.g. soccer
    espn_player_stats refreshed 2026-06-18 09:08, but only because a process was running).

---

## 6. PLAN TO GET BETTER (prioritized)

Quick wins:
1. Regenerate / fix `DATA_INVENTORY.md` and split it. Rerun the census against the REAL
   local data and add a separate `data/domains/INVENTORY.md` (per-sport rows, span,
   last-refresh, source). Remove or clearly mark the 0-row legacy shells so the doc stops
   overselling. (Approach: a small script that walks `data/domains/*` + reads parquet
   metadata; write atomically.)
2. Stamp freshness into every snapshot + a heartbeat file. Have `refresh_daemon` and
   each ingest write `last_refresh_utc` + rowcount into a `data/health/<sport>.json`; the
   board surfaces a "stale" badge when older than a threshold. Cheap, makes #10 visible.
3. Prune model backups. Keep last N + any promoted; archive the rest off-box. Reclaims
   ~1GB and removes ambiguity about which artifact is live.
4. Archive the stranded CV/intelligence tier off the working box. 6.5GB tracking +
   1.6GB shadow can go to B2 / cold storage; keep only what the current 4-sport product
   reads. Frees the 15GB box and clarifies what is actually used.

Bigger bets:
5. Stand up a genuine always-on host (ROADMAP Phase 21). A small always-on VPS (Hetzner/
   Fly) running `auto_loop --forever` + `refresh_daemon` under systemd/supervisor, with
   the per-domain parquets synced (they are only ~93MB). This is the single biggest gap:
   the self-improving paper loop only compounds if it runs 24/7 across a full season, and
   right now it dies when the laptop sleeps.
6. Close the MLB pitcher gap. Extend `ingest_pitchers` to 2022-26 via MLB StatsAPI so
   current predictions stop running pitcher-blind.
7. Multi-venue + closing-prop capture for true CLV. Add a second keyless odds venue and
   log closing prop lines so CLV-vs-close (the honest yardstick) becomes computable;
   today only realized-ROII-at-taken-price exists.
8. Scheduled ingest with retries + alerting (toward Phase 34). Cron/timer per sport with
   exponential backoff + a Discord/email alert on N consecutive failures; drift alerts on
   calibration metrics from the eval-gate.
9. One canonical data manifest as code. A `data_manifest.py` that is the single source
   for every used table's path/schema/source/refresh-cadence, consumed by predictors and
   health checks alike -- kills the two-parallel-worlds drift (#9 above).

---

## 7. HOW GOOD CAN IT GET -- honest ceiling

Realistic best for THIS area (data + ops, not the model's edge):

- The per-sport data layer can become a clean, fully-fresh, fully-manifested,
  always-refreshed 4-5 sport corpus on free keyless feeds, with freshness badges and
  drift alerts. That is very achievable and would make the product feel production-grade.
- With a small always-on VPS, the self-improving paper loop can run unattended across
  full seasons (thousands of settled games), which is exactly the regime where the honest
  calibration story (Brier/ECE matching the devigged close) can actually be PROVEN at N
  large enough to escape small-sample variance. That is the highest-value ceiling here.

What permanently limits it:
- Markets are efficient. Better data plumbing improves CALIBRATION and sharpness; it does
  NOT manufacture a dollar edge. The honest ceiling is "match the devigged close within
  noise, with a measured in-game conditioning improvement labelled as calibration." No
  amount of ops work changes that.
- Data DEPTH on free feeds caps freshness: same-day lineups, late scratches, weather, and
  true closing lines are the levers we mostly cannot see keylessly -- repeatedly flagged
  in memory as the real gap on totals/props. The current vertical (World Cup, 24 matches)
  is data-starved and will stay so until the schedule provides more matches.
- The legacy NBA CV/intelligence tier is at a documented noise wall (jersey OCR ~2.3%,
  ghost slots, scoreboard-OCR keystone) -- more ops won't lift it; it should be treated as
  cold-storage scouting data, not a growth surface.
- The local box (15GB RAM, 8GB GPU, freeze-on-full-pytest) is a hard ceiling for any
  heavy compute done locally; production CV must stay on ephemeral RunPod, and the
  always-on loop must move off the laptop to compound at all.

Net: the data/ops layer can realistically reach "clean, fresh, manifested, 24/7,
drift-alerted, honestly-calibrated multi-sport decision support" -- a genuinely strong
engineering artifact -- but its predictive ceiling is bounded by market efficiency and
keyless-feed depth, and its honest deliverable is calibration, never profit.
