# Structured-Extraction Freshness Pipeline (injury/lineup/news -> vacated-load)

_Design doc, 2026-06-16. For: roadmap item X1 (the #2 lever, capturable freshness). Build location: `scripts/platformkit/freshness/` (new dir) + `domains/basketball_nba/freshness/` (the as-of read adapter). Treat the vacated-load model (`scripts/team_system/effects_vacated_load.py`) and the existing as-of reader (`scripts/team_system/availability.py`) as EXISTING; this pipeline FEEDS them, it does not modify them._

---

## Goal + done-criteria

**Goal.** Stand up a nightly + ~2h-pre-game LLM structured-extraction pipeline that converts unstructured injury/lineup/news text into typed, timestamped rows in SQLite, where each `status=OUT` row drives the EXISTING vacated-load usage redistribution. The LLM extracts and structures ONLY; it never emits a probability, a usage multiplier, or any number that enters the prediction chain. The vacated-load model (already validated) computes every redistribution; the pipeline's only job is to deliver a clean, vintage-aligned `who-is-OUT-and-when-did-we-know` table.

**Why this is the lever (from the roadmap).** Freshness is the binding constraint on pregame calibration and the pregame model's one known structural gap: the close moves on injury/lineup news the model cannot see. This pipeline is the capturable slice of that edge -- and it is honest by construction ONLY if every fact is stamped with the wall-clock time we actually knew it (`extracted_at`) and the backtest uses the as-of value alone.

**Done = shipped + validated means ALL of:**

1. **Pipeline runs unattended.** `python scripts/platformkit/freshness/run_extraction.py --window pregame` produces validated rows in `data/freshness/freshness.sqlite` from >=2 source types, with every row carrying `extracted_at` (UTC ISO-8601) and a downstream Pydantic schema-validation pass (no row enters the DB unvalidated).
2. **Vintage alignment is enforced, not hoped.** A test asserts `extracted_at < tip_off_utc` for every row used in any backtest read, and the as-of reader (`as_of_out_ids(team, asof_ts)`) NEVER returns a row whose `extracted_at >= asof_ts`. A deliberately-late row (extracted after tip) is filtered out by the reader -- proven by a unit test.
3. **It drives vacated-load.** `as_of_out_ids(...)` returns the OUT player_ids; piped into the existing `TeamModel.from_cache(out_ids=...)` path (the same interface `availability.out_ids_for` already feeds), the sim reroutes usage via the existing `usage_reroute_mult`. No change to the vacated-load math.
4. **Leak-free OOS calibration win, two corpora.** On walk-forward (purge + embargo), the pregame sim WITH the as-of freshness feed has Brier/log-loss vs the Shin-devigged close that is **no worse** and **better on the subset of games with a confirmed pre-tip OUT delta**, on **NBA 2023-24 AND 2024-25** (the two corpora). Reported with 95% CI clustered by game_id and a Diebold-Mariano test (p<0.05, N>=200) on the affected subset. An honest null (no improvement) is a recorded success, not a failure.
5. **Extraction quality measured.** On a hand-labeled golden set of ~150 source snippets, field-level precision/recall for `status` and `player_id` mapping is reported; the downstream schema-validation reject rate is logged (the brief's ~12% hard-case semantic-fail is the thing we catch here, not the thing we trust away).

---

## Design

### Data flow (one line)

```
sources (text)  ->  fetch (honest, polite)  ->  raw_documents table (verbatim + fetched_at)
   ->  LLM structured extraction (Claude tool-use, strict schema, instructor max_retries=3)
   ->  Pydantic downstream re-validation + player_id resolution  ->  injury_status rows (typed, extracted_at)
   ->  as-of reader (domains/...)  ->  out_ids_for_asof  ->  EXISTING TeamModel.from_cache(out_ids=...)  ->  EXISTING vacated-load reroute  ->  sim
```

The LLM sits in exactly one box (extraction). Everything downstream of it is deterministic Python + SQL. No probability, no multiplier, no number crosses out of the LLM box.

### Dir / file layout (all under ALLOWED paths, each <=300 LOC, per-file tests)

```
scripts/platformkit/freshness/
  schema.py              # Pydantic models: RawDocument, InjuryExtraction, InjuryRow (the typed contract)
  db.py                  # SQLite open/migrate/insert/query helpers; the 3 tables below
  sources.py             # honest fetchers: ESPN injury JSON, NBA.com injury report PDF/CSV, team beat RSS
  extract.py             # the LLM extraction agent (Claude tool-use + instructor, max_retries=3)
  resolve.py             # name -> player_id resolution against the existing roster map (fuzzy + alias table)
  run_extraction.py      # CLI orchestrator: fetch -> extract -> validate -> resolve -> insert (idempotent)
  golden/                # hand-labeled extraction fixtures (committed) for the quality eval
    injury_snippets.jsonl
  test_schema.py
  test_db.py
  test_extract.py        # uses recorded API fixtures (vcr-style cassette), no live call in CI
  test_resolve.py
  test_run_extraction.py

domains/basketball_nba/freshness/
  as_of_reader.py        # as_of_out_ids(team, asof_ts) -- the ONLY thing the sim/backtest calls
  test_as_of_reader.py   # the vintage-alignment guard tests (the load-bearing tests)

data/freshness/          # gitignored (data/ is gitignored); local SQLite lives here
  freshness.sqlite
```

`data/registry/` is NEVER written. The SQLite file lives under `data/freshness/` (a normal gitignored data dir), not the registry.

### SQLite schema (3 tables -- raw, extracted, resolved)

The separation matters: `raw_documents` is the audit trail (verbatim text we saw, when we fetched it), `injury_extractions` is the LLM's typed output (auditably linked to its source doc), `injury_status` is the resolved, query-ready table the sim reads. `extracted_at` propagates from doc fetch time, never from game time.

```sql
-- 1. Verbatim source capture (audit trail; lets us re-extract if the schema changes)
CREATE TABLE raw_documents (
    doc_id        TEXT PRIMARY KEY,         -- sha256(source_url + fetched_at)
    source        TEXT NOT NULL,            -- 'espn' | 'nba_official' | 'beatwriter_<team>'
    source_url    TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,            -- UTC ISO-8601, the moment WE pulled it
    raw_text      TEXT NOT NULL,            -- verbatim, untouched
    content_hash  TEXT NOT NULL             -- sha256(raw_text); dedup unchanged re-pulls
);

-- 2. LLM extraction output (one row per extracted player-status from a doc)
CREATE TABLE injury_extractions (
    extraction_id TEXT PRIMARY KEY,         -- uuid4
    doc_id        TEXT NOT NULL REFERENCES raw_documents(doc_id),
    player_name   TEXT NOT NULL,            -- as the LLM read it (pre-resolution)
    team_raw      TEXT,                     -- as the LLM read it
    status        TEXT NOT NULL,            -- OUT|DOUBTFUL|QUESTIONABLE|PROBABLE|AVAILABLE|GTD
    severity      TEXT,                     -- minor|moderate|severe|season_ending|unknown
    body_part     TEXT,
    game_date     TEXT,                     -- the date the status applies to (model's claim)
    confidence    REAL NOT NULL,            -- LLM self-reported [0,1]  (NOT a probability that enters preds)
    extracted_at  TEXT NOT NULL,            -- == raw_documents.fetched_at (propagated; the vintage stamp)
    model_id      TEXT NOT NULL,            -- e.g. 'claude-...-YYYYMMDD' for reproducibility
    schema_ok     INTEGER NOT NULL DEFAULT 0  -- 1 only after downstream Pydantic re-validation passed
);

-- 3. Resolved, query-ready status the sim/backtest reads
CREATE TABLE injury_status (
    row_id        TEXT PRIMARY KEY,         -- uuid4
    extraction_id TEXT NOT NULL REFERENCES injury_extractions(extraction_id),
    player_id     INTEGER NOT NULL,         -- resolved against the canonical roster map
    team_id       INTEGER NOT NULL,
    team_tri      TEXT NOT NULL,            -- 'SAS' etc; matches availability.py's tri interface
    status        TEXT NOT NULL,
    severity      TEXT,
    game_date     TEXT NOT NULL,
    source        TEXT NOT NULL,
    extracted_at  TEXT NOT NULL,            -- the vintage stamp; the WHOLE GAME
    confidence    REAL NOT NULL,
    superseded_by TEXT                      -- row_id of a later extraction for same (player_id, game_date), or NULL
);
CREATE INDEX idx_status_asof ON injury_status (player_id, game_date, extracted_at);
CREATE INDEX idx_status_team ON injury_status (team_tri, game_date, extracted_at);
```

**Why three tables and `superseded_by`:** a player's status changes through the day (QUESTIONABLE at noon -> OUT 90 min before tip). We NEVER overwrite; we append a new row with a later `extracted_at` and point the old row's `superseded_by` at it. The as-of reader picks the latest row with `extracted_at < asof_ts`. This is what makes vintage alignment a query, not a hope.

### How OUT rows map to vacated-load (no math change)

`effects_vacated_load.py` already produced a validated `usage_reroute_mult` (and pts/ast variants, with per-role absorption tiers). The runtime path is the EXISTING one that `availability.out_ids_for(tri, asof=...)` feeds: `TeamModel.from_cache(out_ids=...)`. This pipeline simply provides a richer, timestamp-correct `out_ids` set:

```
as_of_out_ids("SAS", asof_ts="2024-03-11T23:30:00Z")
   -> {player_id, ...}   # every player with latest status in {OUT} and extracted_at < asof_ts
   -> TeamModel.from_cache(out_ids=...)   # EXISTING; reroutes usage by the EXISTING usage_reroute_mult
```

`severity`/`confidence` are stored but do NOT feed the multiplier in v1 (the vacated-load model is binary IN/OUT). They are display + future-research fields. QUESTIONABLE/DOUBTFUL are stored but NOT treated as OUT by default (matching `availability.py`'s `include_questionable=False` default); a separate gated experiment can test a probabilistic-availability variant later -- out of scope here, and it would be a NEW gated flag, never flipped ON in this work.

---

## Implementation sketch

### `schema.py` -- the typed contract (Pydantic v2)

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class Status(str, Enum):
    OUT = "OUT"; DOUBTFUL = "DOUBTFUL"; QUESTIONABLE = "QUESTIONABLE"
    PROBABLE = "PROBABLE"; AVAILABLE = "AVAILABLE"; GTD = "GTD"

class Severity(str, Enum):
    MINOR = "minor"; MODERATE = "moderate"; SEVERE = "severe"
    SEASON_ENDING = "season_ending"; UNKNOWN = "unknown"

class InjuryExtraction(BaseModel):
    """One player-status the LLM pulled from ONE document. The LLM fills this; nothing here is a probability that enters predictions."""
    player_name: str
    team_raw: Optional[str] = None
    status: Status
    severity: Severity = Severity.UNKNOWN
    body_part: Optional[str] = None
    game_date: Optional[str] = Field(None, description="ISO date YYYY-MM-DD the status applies to")
    confidence: float = Field(..., ge=0.0, le=1.0,
        description="LLM's self-reported extraction confidence. NOT an outcome probability.")

    @field_validator("player_name")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("player_name empty")
        return v.strip()

class ExtractionBatch(BaseModel):
    """Top-level tool-call return: a doc yields zero or more extractions."""
    extractions: list[InjuryExtraction]
```

### `extract.py` -- the LLM extraction agent (extracts ONLY)

```python
import instructor
from anthropic import Anthropic
from .schema import ExtractionBatch

# instructor wraps the Anthropic client and re-prompts on schema-validation failure.
_client = instructor.from_anthropic(Anthropic())   # key from env; NEVER hard-coded

SYSTEM = (
    "You are a sports-data EXTRACTION tool. You read injury/lineup text and return "
    "structured player-status records. You do NOT predict games, estimate win "
    "probability, or output any number except the schema's confidence field "
    "(which is your confidence in the EXTRACTION, not in any game outcome). "
    "If a field is not stated in the text, leave it null/unknown -- never guess. "
    "Map vague phrasing conservatively: 'game-time decision' -> GTD, not AVAILABLE "
    "(LLMs are biased toward optimistic availability; resist it)."
)

def extract_doc(raw_text: str, model: str = "claude-...", max_retries: int = 3) -> ExtractionBatch:
    """Return validated ExtractionBatch. instructor retries on Pydantic failure up to max_retries.
    Constrained decoding is ~12% semantic-fail on hard cases -> the caller STILL re-validates downstream."""
    return _client.messages.create(
        model=model,
        max_tokens=2048,
        max_retries=max_retries,                 # instructor: re-prompt with the validation error
        system=SYSTEM,
        messages=[{"role": "user",
                   "content": f"Extract every player injury/availability status from:\n\n{raw_text}"}],
        response_model=ExtractionBatch,          # strict tool-use schema
    )
```

**Belt-and-suspenders (the brief's 12% rule).** `instructor`'s `max_retries` handles *syntactic/Pydantic* failures. It does NOT catch *semantically wrong* output (right shape, wrong fact). So `run_extraction.py` re-validates downstream before `schema_ok=1`:
- status string is in the `Status` enum (already enforced) AND consistent with severity (e.g. `season_ending` => status cannot be `AVAILABLE`);
- `game_date` (if present) is within +/- 3 days of the source doc's `fetched_at` date (rejects hallucinated dates);
- the player name resolves to exactly one `player_id` (see `resolve.py`); ambiguous/no-match rows are quarantined (`schema_ok=0`) and logged, never silently dropped.

### `resolve.py` -- name -> player_id (deterministic, not LLM)

```python
def resolve(player_name: str, team_raw: str | None, roster_map: dict) -> tuple[int, int, str] | None:
    """Return (player_id, team_id, team_tri) or None. Exact -> alias-table -> rapidfuzz>=92 within team.
    NO LLM here: resolution is a lookup, and an LLM 'guess' would reintroduce the fabrication risk."""
    ...
```

### `run_extraction.py` -- orchestrator (idempotent, two windows)

```python
# python run_extraction.py --window nightly      (full slate, ~once/day)
# python run_extraction.py --window pregame      (~2h before each tip; only today's games)
def main(window: str):
    now = utcnow_iso()                              # the vintage stamp source
    for src in active_sources(window):
        for doc in src.fetch():                     # sources.py, polite (see below)
            if db.seen_content_hash(doc.content_hash):
                continue                            # unchanged re-pull -> skip, but record fetched_at
            db.insert_raw(doc, fetched_at=now)
            batch = extract_doc(doc.raw_text)        # LLM, the only LLM step
            for ext in batch.extractions:
                if not downstream_valid(ext, doc):   # the 12%-catch re-validation
                    db.quarantine(ext, doc); continue
                resolved = resolve(ext.player_name, ext.team_raw, ROSTER_MAP)
                if resolved is None:
                    db.quarantine(ext, doc); continue
                db.insert_status(ext, resolved, extracted_at=now, mark_supersede=True)
```

`extracted_at` is set to the fetch wall-clock `now`, identical across a run, and propagated unchanged into `injury_status`. This is the single most important line in the pipeline: it is the difference between a freshness edge and a leak.

### `as_of_reader.py` -- the ONLY thing the sim/backtest calls (the leak guard)

```python
def as_of_out_ids(team_tri: str, asof_ts: str, statuses=("OUT",)) -> set[int]:
    """Player_ids whose LATEST status as-of asof_ts is in `statuses`.
    Vintage alignment: NEVER returns a row with extracted_at >= asof_ts.
    asof_ts at backtest time = tip_off_utc (or the prediction timestamp); in production = utcnow()."""
    rows = db.query(
        "SELECT player_id, status, extracted_at FROM injury_status "
        "WHERE team_tri=? AND game_date=? AND extracted_at < ? "
        "ORDER BY player_id, extracted_at DESC",
        (team_tri, _date_of(asof_ts), asof_ts))
    latest = {}                                       # first row per player = latest before asof
    for r in rows:
        latest.setdefault(r["player_id"], r["status"])
    return {pid for pid, st in latest.items() if st in statuses}
```

This signature mirrors the existing `availability.out_ids_for(tri, asof=...)` so it is a drop-in for the same `TeamModel.from_cache(out_ids=...)` consumer -- but it keys on a full `extracted_at` *timestamp*, not a filename date, which is the upgrade that makes intraday pre-tip freshness honest.

### `sources.py` -- honest fetching (politeness is part of the design)

- **NBA official injury report** (the league publishes a scheduled injury report; CSV/PDF). Authoritative, has explicit timestamps -> best `extracted_at` ground truth. Parse the timestamp the league prints, but store OUR `fetched_at` as the binding vintage stamp.
- **ESPN injury JSON** (`site.api.espn.com/.../injuries`) -- supplemental; undocumented, treat as "works until it doesn't" (brief gotcha).
- **Team beat-writer RSS / public posts** -- only public feeds, respect robots.txt, `User-Agent` identifying the project, >=2s between requests, cache verbatim so we never re-hit. No scraping behind logins, no paywalled content. (The roadmap explicitly de-prioritizes computer-use odds scraping; same spirit here -- use clean feeds, fetch politely.)

Two source TYPES minimum (NBA-official + one of ESPN/beat) so a single source's outage or bias does not silently zero the feed.

### Build-loop config note (human-confirm before applying)

The pre-game window wants a scheduled run. Propose a NEW headless cron entry (per the roadmap's "headless `-p` nightly cron" pattern) -- but DO NOT edit `.claude/settings.json` in this work; the active session is on `fullsend-ingame-pregame-execution` and shares that file. Flag for the human: "add a cron/scheduled task calling `run_extraction.py --window pregame`; confirm before touching shared `.claude/` config." The Python CLI must run standalone without any settings change.

---

## Validation plan (leak-free, two corpora)

**Corpora:** NBA 2023-24 (corpus A) and NBA 2024-25 (corpus B). Each must pass independently -- a pass-on-A / honest-reject-on-B is a finding, not a hidden failure.

**The hard part is that historical `extracted_at` is hard to reconstruct.** We cannot LLM-extract today and pretend we knew it last season. Two honest options, in order of preference:

1. **Preferred (true vintage):** use sources that publish a historical timestamp we did NOT generate -- chiefly the NBA official injury report archive (each report is timestamped at publication). Set `extracted_at` to the *published report time*, not today. This is genuine vintage data: the league knew it then, so we can claim we could have.
2. **Fallback (outcome-conditioned proxy -- OPTIMISTIC UPPER BOUND only):** where only a final pre-game status exists, set `extracted_at = tip_off_utc - 90 minutes` ONLY for `status=OUT` rows that the historical box score confirms as a DNP-injury (cross-checked against `data/dnp_rows.parquet`, which `effects_vacated_load.py` already uses). **WARNING: this selection is OUTCOME-CONDITIONED -- we know these players were OUT only because the game already happened. Any metric computed on this fallback-proxy subset must be labeled "OPTIMISTIC UPPER BOUND (selection conditioned on realized DNP -- NOT a leak-free calibration result)". The headline "shipped + validated" verdict MUST come ONLY from true forward-captured `extracted_at` vintage (the nightly / ~2h-pre-game live extraction); the fallback-proxy subset CANNOT be used to claim the pipeline is validated or that a calibration gain is real.** Use the proxy subset solely to bound how large the effect could be if timing were perfect, not to claim it is captured.

Never backfill `extracted_at` from anything that postdates tip. A test asserts no `extracted_at >= tip_off` row is ever read.

**Walk-forward protocol (matches the project standard):**
- Expanding window: train/calibrate on `game_date < t`, evaluate on `game_date >= t`.
- **Purge:** drop any test game involving a team that played within 48h of a training game (the project's existing rule).
- **Embargo:** 3-day gap between train and test boundary.
- Vintage assertion INSIDE the window: for every test game, the freshness rows read satisfy `extracted_at < tip_off_utc`.
- The freshness feed is the ONLY thing that differs between the two arms (control = sim without the as-of OUT set; treatment = sim WITH it). Same seed, same sim, same calibrator.

**Metric + test + thresholds:**
- Primary: **Brier** and **log-loss** of the game win-probability vs the **Shin-devigged** close (`mberk/shin`; multiplicative devig only at near -110/-110). Report Brier Skill Score vs the close as the headline.
- **Diebold-Mariano test** on per-game Brier differences (treatment vs control), on the **subset of games with >=1 confirmed pre-tip OUT delta** (the only games where the feed can possibly move the number). Threshold: DM p<0.05, N>=200; report the point delta with a 95% CI **clustered by game_id** (naive SEs run ~3x too narrow).
- Secondary diagnostic: per-game reliability on the affected subset (Murphy decomposition -- did Resolution rise without Reliability degrading?).
- **Extraction-quality eval (separate, on the golden set):** field-level precision/recall for `status` and exact-match rate for `player_id` resolution on ~150 hand-labeled snippets; report the downstream schema-validation reject rate (expect ~10-15% on hard cases per the brief -- this number being non-zero is the system working, not failing).

**Honest-reject branch (a success).** If, on the affected subset, the treatment does NOT beat control on either corpus (DM p>=0.05 or CI straddles 0), the recorded finding is: "structured freshness OUT-deltas are absorbed by recency / already in the close on these games -- no measured pregame calibration gain." That is a legitimate, publishable outcome and consistent with the project's prior that recency absorbs much of vacated-load. It does NOT get tuned until it passes.

---

## Effort + sequencing (rough days; dependencies; do-first)

Total ~1.5-2 weeks, matching the roadmap's X1 estimate.

1. **(0.5d) `schema.py` + `db.py` + migrations + their per-file tests.** No external deps; unblocks everything. DO FIRST.
2. **(0.5d) `as_of_reader.py` + `test_as_of_reader.py` FIRST among the readers.** Write the vintage-alignment guard tests BEFORE the fetchers -- the late-row-filtered-out test is the load-bearing correctness check; build it early so everything downstream is validated against it.
3. **(1.5d) `sources.py`** -- start with the NBA official injury report (gives true historical timestamps, which the validation depends on); add ESPN second. Polite fetch + verbatim cache.
4. **(1.5d) `extract.py` + `resolve.py`** -- instructor/Pydantic wiring, downstream re-validation, name resolution against the existing roster map. Record API cassettes for `test_extract.py` so CI never makes a live call.
5. **(1d) `run_extraction.py`** -- orchestration, idempotency, supersede logic, quarantine.
6. **(0.5d) Golden set** -- hand-label ~150 snippets; wire the extraction-quality eval.
7. **(3-4d) Validation harness** -- build the historical `extracted_at` reconstruction (NBA report archive + the conservative 90-min proxy cross-checked vs `dnp_rows.parquet`), run the two-arm walk-forward on both corpora, DM test, reliability. This is the longest and most important block.

**Dependencies:** the vacated-load model and `TeamModel.from_cache(out_ids=...)` already exist (do not modify). The roster name->id map already exists (used by `effects_vacated_load.py`); `resolve.py` reuses it. The Shin devig (`src/prediction/betting_edge.py`) and the walk-forward harness exist; the validation calls them read-only. None of this work edits `src/`, `kernel/`, `api/`, `scripts/team_system`, or `intel` -- it adds new files under `scripts/platformkit/freshness/` and `domains/basketball_nba/freshness/` only.

---

## Gotchas + how the honest discipline applies

- **`extracted_at` is the whole game.** Every leak risk in this pipeline reduces to "did we stamp a fact with a time earlier than we truly knew it?" The guard is mechanical: the as-of reader filters `extracted_at < asof_ts`, a unit test plants a post-tip row and asserts it is excluded, and historical `extracted_at` is only ever set from a source-published timestamp or a clearly-labeled conservative pre-tip proxy. Never from today.
- **The LLM never emits a number that enters predictions.** Its only numeric output is `confidence` in its own extraction, which is stored for display/triage and does NOT feed the multiplier. The vacated-load model (deterministic, already validated) computes all redistribution. This is the binding invariant; the system prompt states it and the schema enforces it (no probability field exists on `InjuryRow`).
- **Constrained decoding is ~12% semantic-fail on hard cases.** `instructor max_retries=3` fixes shape, not truth. The downstream re-validation (severity/status consistency, date sanity, single-player resolution) is non-negotiable; rows that fail are quarantined (`schema_ok=0`) and logged, never silently dropped or silently trusted.
- **LLM optimism bias** (the brief: LLMs understate injury severity and assume starters play). The system prompt explicitly resists it ("game-time decision -> GTD not AVAILABLE"); the golden-set precision/recall on `status` is the measurement that catches drift. Conservatism is the safe direction here -- a false QUESTIONABLE is harmless (not treated as OUT); a false AVAILABLE for an actually-OUT star is the costly error, so the prompt and eval are tuned to minimize THAT.
- **Recency may absorb the signal (the prior).** The project already found vacated-load is largely immaterial for marginal accuracy because recency absorbs it; the value is freshness/timing. So the eval is scoped to the affected subset (games with a pre-tip OUT delta) and an honest null is an expected, acceptable outcome -- recorded, not tuned away.
- **Two corpora, clustered SEs, DM test.** No "it helped" claim ships on one season or a bare point delta. NBA 2023-24 AND 2024-25; 95% CI clustered by game_id; DM p<0.05, N>=200.
- **Source fragility / politeness.** ESPN and beat feeds break without notice and must be fetched politely (UA, robots.txt, >=2s spacing, verbatim cache). Two source types minimum so one outage does not silently zero the OUT set (which would look like "everyone available" -- a dangerous failure mode). The NBA official report is the authoritative anchor.
- **No flag flipped ON, no shared config touched.** Severity/QUESTIONABLE-as-probabilistic-availability is a FUTURE gated experiment, not part of this work. The pre-game cron is proposed for human confirmation; this work does not edit `.claude/settings.json` (shared with the active `fullsend-ingame-pregame-execution` branch). Local-only; never pushed; `data/freshness/` is gitignored; `data/registry/` is never written.
- **Secrets.** The Anthropic key comes from the environment, never hard-coded (the repo already has a history of a hard-coded Odds API key flagged for rotation -- do not repeat it).
