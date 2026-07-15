# Proof Room snapshot spec (v1)

Goal: one scrubbed, static JSON bundle the public frontend reads. No live API
exposure, no data/ raw rows, aggregates + receipts only. Built entirely in
scripts/platformkit/showcase/ (non-gated). ASCII only. <=300 LOC/file.

## Output layout

data/frontend/showcase/            <- local staging (gitignored, like data/)
  manifest.json                    <- {generated_at_utc, bundle_version, files: {...}, counts}
  bridge.json
  slate.json
  calibration.json
  claims_index.json
  graveyard.json
  machine.json
  ledger.json
  replays/<game_id>.json

Exporter entrypoint: scripts/platformkit/showcase/export_snapshot.py
  - orchestrates per-room builders (one module per room, showcase/rooms/*.py)
  - each room builder: build() -> dict (pure), exporter writes atomically
  - a room that cannot build (missing source) writes {"status":"unavailable",
    "reason": "..."} -- NEVER fabricates. Fail-open per room, fail-closed on lint.

## Shared shapes

Receipt (attached to every headline number):
  {"claim": str,                # human sentence, no-edge-claims compliant
   "value": num|str,
   "label": str,                # e.g. "PROVISIONAL", "GATED", "MEASURED"
   "artifact": str,             # repo-relative path or ledger id
   "sha": str|null,             # content sha when available
   "reproduce": str|null,       # exact command
   "asof": str}                 # ISO date of the measurement

## Rooms (v1 fields; builders may add, never rename)

bridge.json: {heartbeat: {daemons_ready, daemons_total, last_tick_utc},
  funnel: [{stage, count, unit, receipt}], heroes: [Receipt x3]}

slate.json: {slates: [{sport, event_id, start_utc, home, away,
  our_prob_home, market_prob_home|null, market_source|null, asof_utc}],
  graded_yesterday: [{...same + outcome, brier_ours, brier_market|null}]}

calibration.json: {per_sport: [{sport, n, brier_ours, brier_close|null,
  crps|null, label, reliability_bins: [{p_lo, p_hi, n, p_mean, y_rate}],
  receipt}]}

claims_index.json: {total, families: [...], claims: [{id, statement, verdict,
  sport, family, sha, artifact, reproduce|null, asof}]}  # cap ~5000 rows,
  sampled across families if larger; manifest notes the cap.

graveyard.json: {rejects: [{hypothesis, sport, why_killed, gate, asof,
  receipt}], retractions: [{number, story, where_documented}]}

machine.json: {daemons: [{name, purpose, status, last_beat_utc}],
  build: {commits, span, model_roles: str}, loop: {recent_verdicts: [...]}}

ledger.json: {paper: {n_positions, settled, coverage_pct, clv_bps_mean|null,
  clv_measurable_pct, framing: "CLV is the yardstick; measurement infra,
  not an edge claim."}, per_sport: [...]}

replays/<id>.json: {game: {sport, home, away, date, final}, ticks: [{t,
  period, clock, score_home, score_away, prob_static, prob_conditional,
  prob_market|null}], receipt}

## Hard rails (enforced by showcase/lint_bundle.py, run at end of export)

- Banned tokens anywhere in bundle: roi, bankroll, pnl, profit, edge_pct,
  and ALL retracted numbers (18.38, 0.119 as headline, 54%, 78.11, 8.94, 54.57).
- Every headline number MUST carry a receipt with a label; PROVISIONAL data
  keeps its PROVISIONAL label verbatim.
- Secrets scrub: no api keys, account ids, bet-account balances, emails.
- Bundle must round-trip json.load and stay < 15 MB total.

## v1.1 addendum (post-scout decisions, binding)

- PREFER data/frontend/* sources (already shaped): best_bets.json (slate),
  ops/calibration_scoreboard_latest.json, ops/clv_scoreboard.json,
  clv_ledger.jsonl (aggregate only), reject_ledger.jsonl, ingame/ladder_*.json
  + ingame/*_gate_*.json (graveyard/gates), ops/autonomy_status.json +
  ops/autoloop_report.json + **/_heartbeat.json (machine).
- Receipt.sha = sha256 of the SOURCE ARTIFACT FILE computed at export time
  (no claim-level sha exists; do not invent one).
- Claims = TWO corpora, kept separate in claims_index.json:
  {preregistered: {total, graded, sample:[...]}} from data/cache/claims/
  cards.jsonl + card_ledger.jsonl; {verified_facts: {total, families:
  [{family, n_claims, n_verified, n_mismatch}], sample:[...]}} from
  data/cache/intel_claims/*_claims_validation.json. Sample caps: 2000 each.
- RENAME on export: any 'edge_vs_market' field -> 'delta_vs_market';
  'edge' wording never appears in public copy.
- Replay v1: market prob series from data/cache/inplay_odds/
  <sport>_price_series.parquet for 2-3 finished games + our pregame prob +
  final outcome. Tick-level OUR-prob join (paper_predictions.jsonl by
  event_id) is attempted; if the join fails, ship market-series-only with
  note 'model tick overlay: v2'. Never fabricate model ticks.
- Funnel counts: parquet row counts via pyarrow metadata only (never full
  read); knowledge.jsonl line counts; model_registry.json at data/models/
  (NEVER the .claude/worktrees copies).
- Do not export: .bot_state/spend_*.json, bet_id/account-ish fields,
  taken_book is OK (venue name only).

## Tests

One test file per room builder under tests/platformkit/showcase/, run
per-file only. Each test: build() returns required keys, lint passes on a
tiny synthetic bundle, unavailable-source path returns status:unavailable.
