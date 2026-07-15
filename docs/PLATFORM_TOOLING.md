# Platform Tooling Reference

This tooling backs a converged 4-sport (NBA / MLB / Soccer / Tennis) CALIBRATED
prediction platform: one leak-free win-prob per sport anchors a coherent pregame
surface plus an in-game repricer. Measured leak-free / OOS on held-out data
(numbers live in `vault/_Edge_Maps/`; the single honesty truth-source is
`docs/JOB_EVIDENCE_PACKET.md`), the platform does two things well:

- **Pregame MATCHES the devigged closing line within noise** on team-strength
  markets (NBA moneyline, MLB moneyline, Soccer O/U-2.5), trailing only on totals
  and ATP match-win by freshness data (injuries, lineups, park / weather, starting
  pitchers) a public / box model cannot see.
- **In-game conditioning WINS in all 4 sports** - fusing the pregame intelligence
  prior with the realized score state beats the static pregame line (NBA, MLB,
  Soccer, Tennis each show a measured Brier reduction). This is the decisive,
  calibrated, delivered edge.

Both results reproduce from a fresh clone in under 60s on committed fixtures
(`scripts/platformkit/beat_the_close_scoreboard.py` and `ingame_scoreboard.py`,
`--corpus tests/fixtures/proof`). The tooling below enforces the discipline that
makes those claims trustworthy: leak-free walk-forward features, independently
reproducible results, FDR-correct evaluation, and calibrated (not inflated)
probability output.

**The honest disclaimer.** Pregame sports markets are efficient: we MATCH the
devigged close, we do not beat it, and we never claim a $ edge, ROI, or positive
expected value. Across all tested signal families, every candidate run through the
real honest gate (`src.loop.gate`) produced a REJECT verdict on out-of-sample
corpora - and those honest nulls are first-class, durable successes that prevent
repeated work and constrain future hypotheses. A SHIP verdict would require >= 2
independent corpora, FDR-corrected p < 0.05, and positive forward CLV vs real
closing lines; no such verdict exists. Good calibration (ECE) confirms the
probability scale is reliable; it does not imply beating the market close.

---

## Research Harness

`scripts/research_harness/`  -  the AUTONOMOUS_RESEARCHER surface for
systematic, null-result-first signal research. All six modules are importable
and expose CLIs; no module starts a live gate run autonomously.

| Module | Purpose | CLI | Honesty guarantee |
|--------|---------|-----|-------------------|
| `research_ledger.py` | Append-only JSONL lab notebook. Records REJECT / DEFER / SHIP / VARIANCE_ONLY verdicts per sport x signal family so null results compound and are never blindly re-tested. | `python scripts/research_harness/research_ledger.py [--dry-run] [--ingest-catalogs]` | Ledger is append-only; verdicts are immutable once written. Every entry requires `what_would_change_my_mind`. |
| `research_writeup.py` | Renders the ledger as a markdown note that explicitly states the all-REJECT / market-efficient thesis. REJECT findings are highlighted, not hidden. | Importable only: `from scripts.research_harness.research_writeup import render_writeup; md = render_writeup(Ledger())` | Hard-coded honest header: "NO EDGE IS CLAIMED." Forbidden to omit REJECT verdicts. |
| `hypothesis_enumerator.py` | Deterministic, finite enumeration of the candidate-signal space (single-col transforms + pairwise joints) for each sport's leak-free base columns. Cross-references tested vs untested families. | `python -m scripts.research_harness.hypothesis_enumerator` | UNTESTED != opportunity; documents search breadth only, not profit potential. |
| `belief_store.py` | Beta-Binomial ship-rate priors per signal family. Prior Beta(1,9)  -  mean ~ 10%, reflecting market efficiency. Sparse families pool to sport aggregate then global. | `python -m scripts.research_harness.belief_store [--ledger PATH] [--save]` | Posteriors are historical ship-rate estimates, not edge claims. REJECT families increase beta weight, not alpha. |
| `gap_observer.py` | Ranks research gaps by coverage / information-gain score. Score = coverage_gap_weight x prior_uncertainty x data_penalty x settled_discount. | `python -m scripts.research_harness.gap_observer [--top N] [--ledger PATH]` | Prints honest preamble: "UNTESTED != opportunity. Ranking = scientific thoroughness only." REJECT families remain listed but rank below unvisited candidates. |
| `research_loop.py` | End-to-end offline pipeline: enumerate -> ingest catalogs -> update ledger -> update BeliefStore -> render markdown writeup -> emit summary. Consumes existing catalog verdicts; never runs the live gate. | `python -m scripts.research_harness.research_loop [--vault PATH] [--dry-run]` | Wires the four upstream modules; exits with a summary that includes REJECT counts. No gate invocation; no edge claim possible. |
| `research_digest.py` | Concise honest health summary of a completed research loop run. Accepts the result dict from `run_research_loop()` and prints a one-screen status card (finding counts, verdict tally, belief posteriors, top gaps). | `research_loop.py --digest` (flag activates `format_digest(result)` after the run) | Output explicitly labels posteriors as historical ship-rate priors, not edge claims. Never omits REJECT counts. |

---

## Robustness + Calibration Tooling

`scripts/platformkit/`  -  static analysis, conformance checks, calibration
measurement, and the atlas build driver. All tools are read-only unless
explicitly noted.

| Module | Purpose | CLI | Honesty guarantee |
|--------|---------|-----|-------------------|
| `calibration_conformance.py` | Measures per-sport Brier score, ECE, and per-decile reliability bins. Verdicts: PASS (ECE < 0.05) / WARN (< 0.10) / FAIL (>= 0.10). | `python scripts/platformkit/calibration_conformance.py` | Hard-coded `HONESTY_NOTE`: "CALIBRATION != EDGE". Verdict refers only to reliability quality, not profitability. |
| `recalibration.py` | Walk-forward isotonic recalibration (strictly expanding window  -  event i uses only events 0 ... i-1). Compares raw vs recal ECE per sport. | `python scripts/platformkit/recalibration.py` | Reports honestly; near-zero or negative delta is noted as expected for already well-calibrated models. Embeds `CALIBRATION_NOTE` constant in output. |
| `hygiene_lint.py` | Scans every git-tracked file for (a) retracted numbers (+18.38%, 0.119/0.1191 endQ3 Brier, +54%/+54.57%) outside retraction-context lines, and (b) edge-claim phrases ("our edge", "profitable", "beats the market", "guaranteed", "+EV proven", "proven edge"). | `python scripts/platformkit/hygiene_lint.py` | Exit 0 = clean; exit 1 = violations found. Output format: `path:line:CATEGORY: matched_text`. Retraction-context exemption for retracted numbers; no exemption for edge-claim phrases. |
| `validate_adapter.py` | Adapter bootstrap scorecard. Runs the Sec 7/Sec 8 conformance checklist against a domain adapter's `SportContext` via `kernel.testing.conformance`. Items not yet contractable print `NOT_YET_CONTRACTED`; corpus-gated items print `SKIP` with reason. | `python scripts/platformkit/validate_adapter.py --sport <sport_id>` or `--toy` | Never fakes PASS for unimplemented items. Exits non-zero on any FAIL. |
| `check_no_public_push.py` | Pre-push tripwire. Blocks pushes to the public `origin` remote (`neeljshah/court-vision`) while any phase is open in `.planning/platform/build_state.json`. Read-only; never performs a push. | `python scripts/platformkit/check_no_public_push.py --check origin` (exit 1) / `--check private` (exit 0) | Wired as a git pre-push hook. Exit 0 = allowed; exit 1 = blocked; exit 2 = fatal. |
| `check_import_contract.py` | AST-only import-direction guard. Enforces: (1) kernel purity  -  `kernel/` may not import `src.*`, `domains.*`, `api.*`, `scripts.*`; (2) cross-adapter ban  -  `domains/<a>/` may not import `domains/<b>/`. | `python scripts/platformkit/check_import_contract.py` | AST-only; never executes inspected files. Output: `<path>:<line>:KERNEL_IMPORT_VIOLATION` or `CROSS_ADAPTER_VIOLATION`. |
| `gate_coverage_report.py` | Prediction-surface inventory vs ledger verdicts. Emits `.planning/platform/GATE_COVERAGE.md`. Descriptive only; no edge claims; no app boot; no torch; runtime < 5 s. | `python scripts/platformkit/gate_coverage_report.py` (run from `scripts/platformkit/`) | Output is labeled "descriptive only, no edge claims." |
| `atlas/build_all.py` | Multi-sport atlas build driver. Rebuilds the entire Obsidian graph (per-sport notes + META generators) in one command. `--full` adds style-matchups, style-trends, scouting, scheme-transitions, home-environment, NBA trends. `--with-catalogs` runs signal catalogs through the real gate (slow). | `python scripts/platformkit/atlas/build_all.py [--sport all\|<sport>] [--out DIR] [--full] [--with-catalogs]` | Graph-integrity + person-free pass required; all generators DRY onto `obsidian_emit.py`. META dims: `world_model`, `base_rates`, `calibration_segments`  -  each emits an honest, person-free cross-sport note. |

---

## The Always-On Stack: Supervisor + Boot

`boot.ps1` brings up the full local product; `supervisor/` owns the *inventory*
and DAG ordering of what it launches. The supervisor describes (it does NOT
spawn) the processes; each is a `ProcSpec` (`supervisor/manifest.py`) carrying a
launch shape, an optional listen port, `depends_on` edges, a readiness probe, a
restart policy, and env. `manifest(profile)` returns a topologically-sorted list
(Kahn's algorithm, stable on insertion order); a cyclic `depends_on` graph is a
config error and raises `CycleError`. Sport-blind: nothing in `supervisor/`
imports a sport adapter.

**Readiness probes** decide a process is READY (not merely alive): `tcp-port-open`,
`http-200` (on a path), `heartbeat-file-fresh` (mtime within `fresh_sec`), or
`none` (alive == ready). **Restart policy** is a capped exponential backoff
(`min(cap, base * 2**(attempt-1))`); long-lived loops retry forever.

| Process (ProcSpec) | Module | Port | depends_on | Readiness | Role |
|---|---|---|---|---|---|
| `m1_producer` | `predict_service.scheduler` | -- | -- | none (alive) | Produces every active sport's envelope; writes the predict heartbeat |
| `m1_api_paper` | `predict_service.app` | 8099 | m1_producer | http `/health` | Auto-API: serves the calibrated envelopes (read-only) |
| `m1_api_boards` | `scripts.platformkit.frontend.serve` | 8098 | m1_api_paper | tcp | Boards API for the UI |
| `m1_ui` | `npm run dev` (Next.js) | 3000 | m1_api_boards | tcp | Dashboard (skipped in `backend` profile / `-NoUI`) |
| `m1_paper` | `scripts.platformkit.pm_trading.auto_loop --forever` | -- | m1_api_paper | none | Paper-trading loop (paper only) |
| `m1_line_daemon` | `scripts.platformkit.odds_provider.line_snapshot_daemon` | -- | -- | none | Captures closing-line snapshots for CLV |
| `m6_ingame_loop` | `scripts.platformkit.ingame.live_loop` | -- | -- | heartbeat | In-game repricer loop |
| `m2_inplay` | `scripts.platformkit.odds_provider.inplay_runner` | -- | -- | heartbeat | Venue-native in-play capture (independent branch) |
| `m4_selfimprove` | `scripts.platformkit.improve.selfimprove_runner` | -- | -- | heartbeat | Self-improve ratchet (measurement-only by default) |

The capture / in-game / self-improve daemons are deliberately **independent
branches** (no `depends_on`): a dead feed is one red status entry, and the rest
of the stack keeps running. The `backend` profile drops the node UI and prunes
it from every `depends_on` edge so the DAG stays well-formed.

**Governance preflight (runs BEFORE the supervisor).** `boot.ps1` first runs a
fail-closed governance check (honesty linter, provenance, concurrency, pkl
integrity, leak audit, parity). It is **decision-only**: it never authorizes a
bet and never moves money. Real-money placement is **default-DENY** and requires
a separate explicit human flip plus a signed token regardless of the preflight
result; a clean preflight only sets boot eligibility. A failing preflight still
boots the paper stack (unless strict-governance is requested).

**The calibrated envelope (one win-prob anchors every market).** The producer
builds one `SnapshotEnvelope` per sport (`predict_service/contracts.py`):
schema-versioned, with a `status` sentinel (`ok` / `unavailable`), a list of
per-game `PredictionRecord`s (each carrying the model's calibrated `pregame_probs`
and a `leak_guard.in_sample == False` flag), market rows, and `EdgeRow`s. By
construction an `EdgeRow` carries one model probability and one market probability
and **no dollar field** -- `ev` is a probability-space quantity, not a stake, and
a `clv_is_proxy` flag marks when "close" is a pre-tip proxy rather than a settled
number. The store writes `latest.json` atomically (tmp + replace) and appends to
`history.jsonl`; a missing or torn read degrades to the `unavailable` sentinel and
never raises. The Auto-API (`:8099`) exposes read-only `GET /health`,
`/api/sports`, `/api/predict/{sport}`, `/api/predict/{sport}/{game_id}`, plus
guarded edge / bestbets / paper / report / SSE / ops routers that fail to 503
rather than fabricate a value.

---

## The build harness, the daemon fleet, and the paper-execution stack

Three deep docs cover the rest of the always-on system this reference only
summarizes above:

- **[docs/PLATFORM_HARNESS.md](PLATFORM_HARNESS.md)** -- the autonomous build
  orchestrator (`scripts/platform_harness/`) that turns the backlog into a
  running loop: probe state, plan a wave of disjoint-file tasks, spawn coding
  agents, run gate tiers, merge -- with no human required to click continue.
  Current honest status, pulled live from `build_status.py`: **53/83 backlog
  tasks done (63.9%)**, zero blocked, zero rejected.
- **[docs/DAEMONS.md](DAEMONS.md)** -- the always-on daemon fleet: 45
  long-lived `ProcSpec`s (`supervisor/stack_specs.py`) that capture lines,
  reprice live games, settle paper bets, and re-gate candidate signals with
  no chat session attached. Every daemon is PAPER (`executed=False`), UNITS
  not `$`.
- **[docs/PAPER_TRADING_STACK.md](PAPER_TRADING_STACK.md)** -- end to end,
  a model probability becomes a paper ledger row, gets a realistic simulated
  fill (`pm_trading/fill_sim.py` VWAP-walks the opposite side's captured
  Kalshi depth ladder; fail-closed `None`/`no_book` on a stale or missing
  book rather than dressing an unsimulated mid-fill as a book-fill), and is
  settled/graded behind a fail-closed greenlight gate. The same doc's Sec. 7
  covers the cross-venue arb lane (`pm_trading/cross_venue_arb.py` +
  `run_cross_venue_arb.py`) -- a fee-aware two-way lock scanner that fences
  soccer out by default (three-way moneyline risk) and stamps both legs of
  every lock idempotently.

### The id-aware G1 baseline

`scripts/platformkit/run_pytest_baseline.py` is the ONE sanctioned exception
to the per-file-only pytest rule (P0-H-005): a serial, budgeted (8h hard
stop), instrumented full-suite run that produces the frozen failing/error-id
baseline the harness's **G1 gate** (`scripts/platform_harness/gates.py`)
diffs future runs against. G1 is **id-aware**, not a raw pass/fail count: a
new failing or erroring test id fails the gate even if the total count is
unchanged, while a previously-frozen id is excluded so a known-broken test
doesn't block every future wave. Launched detached, never inline:

```bash
cd /c/Users/neelj/nba-ai-system && nohup python scripts/platformkit/run_pytest_baseline.py \
  > logs/pytest_baseline_capture.log 2>&1 &
```

`tests/platform/test_g1_id_aware.py` verifies the id-aware diff logic against
synthetic junit-xml fixtures only -- `run_pytest` is monkeypatched and the
real suite is never invoked from the test itself.

---

## Verification

The table below lists the CORE robustness invariants. The full test surface is
`tests/platform/` (306 files); run one file at a time to avoid pyarrow
contamination and machine freeze under high memory load.

Run each file **individually**  -  do not combine into a single `pytest tests/`
invocation. Combined runs can trigger pyarrow contamination and machine
freeze at high memory load. Command format:
`python -m pytest tests/platform/<file>.py -q`

| # | Test file | Invariant checked |
|---|-----------|-------------------|
| 1 | `test_adapter_leak_invariance.py` | **Truncation-invariance (leak-free):** `feature_bundle()` on seasons <= SPLIT produces base rows byte-identical to the full corpus for the same dates, across tennis / soccer / MLB. Proves no future event contaminates past walk-forward features. |
| 2 | `test_joint_signal_leak.py` | **Joint-signal leak-free + pure-transform:** joint signals on a truncated corpus equal the full corpus for shared pre-T rows; two calls on the same base matrix are bit-identical; output is independent of target / closing columns (no outcome leakage). |
| 3 | `test_adapter_determinism.py` | **Adapter determinism + order-invariance:** two independent adapter instantiations on identical data / seasons produce byte-identical base, signal, target, dates. Dates list is non-decreasing; shuffling input rows does not change output. |
| 4 | `test_gate_determinism.py` | **Gate-verdict determinism:** `evaluate()` on the same fixed `FeatureBundle` (synthetic, 300 rows) produces identical verdict and numeric metrics across two independent calls on CPU. Non-determinism here would silently invalidate catalog reproducibility. |
| 5 | `test_adapter_interface_parity.py` | **Cross-adapter interface parity:** all three market-only adapters (tennis / soccer / MLB) expose the same runtime interface  -  required methods, `feature_bundle()` parameter names and order, `FeatureBundle` attribute set. Enforces "adding a sport = only the adapter". |
| 6 | `test_recalibration_leak.py` | **Recalibration leak battery:** outcome-independence (permuting future outcomes leaves past calibrated values bit-identical), determinism, truncation-invariance, bounds [0, 1], and NaN / inf input guard. All synthetic data. |
| 7 | `test_calibration_conformance.py` | **Calibration (reliability) conformance:** synthetic units verify ECE ~ 0 -> PASS and severe miscalibration -> FAIL; real-corpus paths verify bins sum to n, verdict is valid, honesty note is present, and no edge-claim language appears in output. |
| 8 | `test_import_contract.py` | **Kernel purity + cross-adapter ban:** AST scan of the committed `kernel/` tree produces zero violations; negative fixtures confirm that `import nba_api` inside kernel and cross-domain imports are both detected. |
| 9 | `test_validate_adapter.py` | **Adapter scorecard (toy-based):** valid toyball `SportContext` -> no FAIL items; broken context (bad stats / clock / roster / game_state) -> relevant item FAILs and exit code is 1; `--toy` CLI path exits 0. |
| 10 | `test_hygiene_lint.py` | **Honesty / hygiene lint:** planted retracted numbers are flagged; retraction-context lines are not false-positived; edge-claim phrases are flagged (no exemption); a clean fixture directory produces zero hits; real repo scan completes without error. |
| 11 | `test_graph_invariants.py` | **Graph invariants  -  person-free + link-integrity:** no note may bear `[[Players/X]]`, `player_name:` / `display_name:` frontmatter, or `## Players / Roster / Squad` headers; every wikilink resolves or is an intentional cross-vault anchor. Hermetic (tmp_path only). |
| 12 | `test_generators_person_free.py` | **Generator-level person-free (batch 1):** each per-sport generator emits notes that are (a) person-free, (b) bare-stem wikilinks (no `../`, no `.md` suffix), (c) YAML-frontmatter-prefixed. Hermetic with synthetic DataFrames. |
| 13 | `test_generators_person_free_part2.py` | **Generator-level person-free (batch 2):** extends batch 1 to mlb.atlas, soccer.atlas, and sub-generators (h2h / seasons / playstyles / scheme-transitions / home-environment / scouting). Synthetic corpora via tmp_path. |
| 14 | `test_build_all_full_smoke.py` | **End-to-end graph-build smoke + health:** `build_all.main(["--sport","all","--full","--out",tmp])` exits 0, hub note written, all META generators ran; graph-health pass on a clean synthetic vault; person-free FAIL triggered correctly by a planted `[[Players/X]]` link. |

---

## See Also

The **graph layer**  -  Obsidian vault structure, per-sport playstyle / archetype /
style-matchup / scouting notes, cross-sport taxonomy, and graph dimensions
(`world_model`, `base_rates`, `calibration_segments`)  -  is documented in
[docs/MEMORY_GRAPH.md](MEMORY_GRAPH.md).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
