"""scripts.platformkit.autonomy.label_finals_refresh -- bounded, sport-blind
periodic refresh for the outcome-LABEL artifacts the in-game resolvers depend
on (LANE 3: soccer finals staleness guard).

THE GAP THIS CLOSES
-------------------
26 of 32 unresolved soccer_intl in-game bets traced back to
data/domains/soccer_intl/espn_finals.parquet silently going stale: 2026-06-22
..06-28 was never ingested (nobody re-ran ingest_espn_finals by hand for six
days). ingame_paper_settle._refresh_soccer_finals ALREADY self-heals a SHORT
gap (hardcoded 3-day UTC lookback) every m27 tick, but (a) a 3-day window
cannot heal a 6-day hole and (b) the exact same "someone has to run the
ingest script by hand" shape exists for MLB (espn_boxscores.parquet, observed
stale 2.5 days as of this lane) and WNBA (espn_scoreboard.parquet) -- no
periodic caller exists for either today (grep-verified: neither
domains.mlb.ingest_espn_box.ingest_range nor
domains.basketball_wnba.ingest_espn.ingest_season/ingest_seasons has any
caller outside a test or a CLI __main__).

WHAT THIS MODULE DOES
----------------------
refresh_one(spec, ...): reads the target parquet's own max date (if any),
computes the missing UTC dates since (bounded to spec.max_dates_per_tick so a
single tick can never fetch an unbounded backlog), and calls the sport's own
ingest_range-shaped fetcher for just those dates. A brand-new/missing parquet
falls back to a small bootstrap window (spec.bootstrap_days), never an
unbounded full-history pull. Every fetch is wrapped: a raised exception (network
hiccup, bad HTML, etc.) is caught, logged, and returned as an isolated per-spec
error -- it can NEVER sink a caller's tick or block a sibling spec.

refresh_all(specs, ...): runs refresh_one for each spec in SPECS (or an
injected list), isolated per-spec, returns one summary dict for observability.

NPB/KBO: wired (wave-42 lane label-finals-wiring) via
domains.baseball_npb.results_catchup.catchup_npb /
domains.baseball_kbo.results_catchup_kbo.catchup_kbo. These are SEASON-level,
idempotent catch-ups (not per-UTC-date ESPN JSON fetches like the three specs
above) -- the `dates` arg passed by refresh_one is ignored by their fetch_fn
wrappers below; catchup_npb/catchup_kbo re-derive their own staleness check
and current-season target internally. Bounded the same way: never touches a
prior season, never an unbounded pull, safe to call on every tick (a fresh
parquet is a no-op).

HONESTY: descriptive/realized-score ingestion only; no $/edge field; never
writes data/registry/; never flips a flag; never raises out of refresh_one/
refresh_all.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_label_finals_refresh.py -q
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

DEFAULT_MAX_DATES_PER_TICK = 10
DEFAULT_BOOTSTRAP_DAYS = 3
DEFAULT_REFETCH_DAYS = 3

# fetch_fn contract: fetch_fn(dates: List[str] (YYYYMMDD), out_path: Path) -> Any.
# Isolated per-spec -- an exception here is caught by refresh_one, never propagated.
FetchFn = Callable[..., Any]


@dataclass(frozen=True)
class RefreshSpec:
    """One label artifact's bounded-refresh wiring.

    name: short id for logging/summary keys (e.g. "soccer_intl_finals").
    out_path: the parquet this spec keeps fresh.
    date_col: column read to find the corpus's current max date ("date" for
        every ingest module wired here).
    fetch_fn: sport ingest_range-shaped callable: fetch_fn(dates, out_path=...).
    max_dates_per_tick / bootstrap_days: bounds (never an unbounded pull).
    refetch_days: trailing window ALWAYS re-fetched even if already present
        (a present date may be incomplete -- ingests persist FINAL games only);
        0 disables (pure watermark, the pre-2026-07-07 behavior).
    """
    name: str
    out_path: Path
    fetch_fn: FetchFn
    date_col: str = "date"
    max_dates_per_tick: int = DEFAULT_MAX_DATES_PER_TICK
    bootstrap_days: int = DEFAULT_BOOTSTRAP_DAYS
    refetch_days: int = DEFAULT_REFETCH_DAYS


def _utc_today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def _max_existing_date(out_path: Path, date_col: str) -> Optional[dt.date]:
    """Best-effort max date already in *out_path*, or None if missing/empty/
    unreadable (never raises -- an unreadable parquet just falls back to the
    bootstrap window, same as a brand-new one)."""
    try:
        if not Path(out_path).exists():
            return None
        import pandas as pd
        df = pd.read_parquet(out_path, columns=None)
        if date_col not in df.columns or df.empty:
            return None
        d = pd.to_datetime(df[date_col], errors="coerce").dropna()
        if d.empty:
            return None
        return d.max().date()
    except Exception as exc:  # noqa: BLE001
        logger.debug("label_finals_refresh: max-date read failed for %s: %s",
                     out_path, exc)
        return None


def missing_dates(spec: RefreshSpec, *, today: Optional[dt.date] = None) -> List[str]:
    """YYYYMMDD dates from (max existing date + 1) through *today* inclusive,
    capped at spec.max_dates_per_tick (most-recent-first is NOT assumed by
    callers -- returned oldest-first so a capped tick makes forward progress
    through a backlog rather than re-fetching today forever). A brand-new/
    unreadable parquet uses a bootstrap_days window ending today instead of an
    unbounded full-history pull. Never raises."""
    now = today if today is not None else _utc_today()
    max_dt = _max_existing_date(spec.out_path, spec.date_col)
    if max_dt is None:
        start = now - dt.timedelta(days=max(0, spec.bootstrap_days - 1))
    else:
        start = max_dt + dt.timedelta(days=1)
        if spec.refetch_days > 0:
            # ROOT-CAUSE GUARD (2026-07-07): a date PRESENT in the parquet is
            # not necessarily COMPLETE. The ingests persist only games already
            # FINAL at fetch time, so the first final of day D advances the
            # watermark to D and locks out the rest of D's games forever
            # (observed: exactly 1 of ~14 MLB games/day landed 07-03..07-06 ->
            # 129 in-game paper bets unsettleable). Always re-fetch the
            # trailing refetch_days window; every wired ingest dedupes on its
            # event/game id, so re-fetching is idempotent.
            start = min(start, now - dt.timedelta(days=spec.refetch_days - 1))
    if start > now:
        return []
    n_days = (now - start).days + 1
    n_days = min(n_days, max(0, spec.max_dates_per_tick))
    return [(start + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(n_days)]


def refresh_one(spec: RefreshSpec, *, today: Optional[dt.date] = None) -> Dict[str, Any]:
    """Bounded refresh for one RefreshSpec. NEVER raises -- any failure
    (missing-dates computation OR the fetch itself) degrades to an isolated
    error entry with fetched=[] so a caller's tick or a sibling spec is
    unaffected."""
    try:
        dates = missing_dates(spec, today=today)
    except Exception as exc:  # noqa: BLE001
        logger.warning("label_finals_refresh[%s] missing_dates failed: %s", spec.name, exc)
        return {"name": spec.name, "fetched": [], "n_fetched": 0, "error": str(exc)[:200]}
    if not dates:
        return {"name": spec.name, "fetched": [], "n_fetched": 0, "error": None}
    try:
        spec.fetch_fn(dates, out_path=spec.out_path)
        return {"name": spec.name, "fetched": dates, "n_fetched": len(dates), "error": None}
    except Exception as exc:  # noqa: BLE001 -- a bad fetch must never sink the host tick
        logger.warning("label_finals_refresh[%s] fetch failed dates=%s err=%s",
                       spec.name, dates, exc)
        return {"name": spec.name, "fetched": [], "n_fetched": 0, "error": str(exc)[:200]}


def refresh_all(specs: Optional[Sequence[RefreshSpec]] = None,
                 *, today: Optional[dt.date] = None) -> Dict[str, Dict[str, Any]]:
    """refresh_one for every spec (defaults to the real SPECS list), isolated
    per-spec. Never raises. Returns {spec.name: result_dict}."""
    out: Dict[str, Dict[str, Any]] = {}
    for spec in (specs if specs is not None else SPECS):
        try:
            out[spec.name] = refresh_one(spec, today=today)
        except Exception as exc:  # noqa: BLE001 -- belt+suspenders; refresh_one already isolates
            logger.warning("label_finals_refresh[%s] unexpected top-level error: %s",
                           spec.name, exc)
            out[spec.name] = {"name": spec.name, "fetched": [], "n_fetched": 0,
                              "error": str(exc)[:200]}
    return out


def _soccer_finals_fetch(dates: List[str], out_path: Path) -> Any:
    from domains.soccer_intl.ingest_espn_finals import ingest_range
    return ingest_range(dates, out_path=out_path)


def _mlb_boxscores_fetch(dates: List[str], out_path: Path) -> Any:
    from domains.mlb.ingest_espn_box import ingest_range
    return ingest_range(dates, out_path=out_path)


def _wnba_scoreboard_fetch(dates: List[str], out_path: Path) -> Any:
    from domains.basketball_wnba.ingest_espn import ingest_season
    # WNBA's fetcher is season-keyed; dates_override lets us pass the exact
    # bounded date list instead of walking the full season calendar. The
    # season year is the UTC year of the LATEST date in this bounded batch
    # (dates is oldest-first; a same-tick season rollover is a same-day edge
    # case that self-heals on the very next tick, never a crash).
    year = dates[-1][:4] if dates else str(_utc_today().year)
    return ingest_season(year, out_path=out_path, dates_override=dates)


def _npb_results_fetch(dates: List[str], out_path: Path) -> Any:
    # dates ignored: catchup_npb is season-level + self-derives its own
    # staleness check (see module docstring PROPOSED_WIRING).
    from domains.baseball_npb.results_catchup import catchup_npb
    return catchup_npb(out_path=out_path)


def _kbo_results_fetch(dates: List[str], out_path: Path) -> Any:
    # dates ignored: catchup_kbo is season-level + self-derives its own
    # staleness check (see domains.baseball_npb.results_catchup docstring).
    from domains.baseball_kbo.results_catchup_kbo import catchup_kbo
    return catchup_kbo(out_path=out_path)


def _default_specs() -> List[RefreshSpec]:
    """Built lazily (module-level import-time safety: no repo-path resolution
    at import unless a caller actually asks for SPECS)."""
    repo_root = Path(__file__).resolve().parents[3]
    return [
        RefreshSpec(
            name="soccer_intl_finals",
            out_path=repo_root / "data" / "domains" / "soccer_intl" / "espn_finals.parquet",
            fetch_fn=_soccer_finals_fetch,
        ),
        RefreshSpec(
            name="mlb_espn_boxscores",
            out_path=repo_root / "data" / "domains" / "mlb" / "espn_boxscores.parquet",
            fetch_fn=_mlb_boxscores_fetch,
        ),
        RefreshSpec(
            name="wnba_espn_scoreboard",
            out_path=repo_root / "data" / "domains" / "wnba" / "espn_scoreboard.parquet",
            fetch_fn=_wnba_scoreboard_fetch,
        ),
        RefreshSpec(
            name="npb_results",
            out_path=repo_root / "data" / "domains" / "npb" / "npb_results.parquet",
            fetch_fn=_npb_results_fetch,
            max_dates_per_tick=1,
            bootstrap_days=1,
        ),
        RefreshSpec(
            name="kbo_results",
            out_path=repo_root / "data" / "domains" / "kbo" / "kbo_results.parquet",
            fetch_fn=_kbo_results_fetch,
            max_dates_per_tick=1,
            bootstrap_days=1,
        ),
    ]


SPECS: List[RefreshSpec] = _default_specs()


__all__ = [
    "RefreshSpec", "SPECS", "DEFAULT_MAX_DATES_PER_TICK", "DEFAULT_BOOTSTRAP_DAYS",
    "DEFAULT_REFETCH_DAYS", "missing_dates", "refresh_one", "refresh_all",
]
