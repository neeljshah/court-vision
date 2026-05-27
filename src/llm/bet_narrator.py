"""bet_narrator.py — Claude-generated 2-3-sentence narratives per graded bet.

Replaces the template `"X projects to Y vs Z; model edges line W by V"` on /tonight
and /share with real analytical narratives. Uses claude-haiku-4-5 with prompt
caching on the system prompt for cheap batch generation.

Behavior:
  - If ANTHROPIC_API_KEY env var is unset, narrate_slate() is a no-op (template
    narratives remain).
  - Per-bet narratives are cached on disk at data/cache/narratives/<date>/<bet_id>.txt
    so the same slate replayed within or across days hits zero API cost.
  - Up to N_WORKERS concurrent API calls. Failures fall back to the original
    template narrative and are logged but do not crash the request.

Public API:
  narrate_slate(bets: list[dict], date: str, max_bets: int | None = None) -> None
      Mutates `bets` in place, replacing `narrative_text` for each bet (up to
      `max_bets`, defaulting to len(bets)). Returns None.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5"
_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "narratives"
_N_WORKERS = 6
_TIMEOUT_SEC = 12.0
_MAX_TOKENS = 220

_SYSTEM = (
    "You are CourtVision, an NBA prop-bet analyst. For each bet you receive, "
    "produce a 2-3 sentence narrative that explains *why* the model likes the "
    "OVER or UNDER side. Reference at least one of: opponent matchup tendency, "
    "recent form, pace, injury context, or role/usage. Stay under 60 words. "
    "Be direct and specific — no hedging like 'might' or 'could'. End with a "
    "plain-English risk note when there is genuine uncertainty (DNP, blowout "
    "risk, line shopping). Never recommend a stake size or use the word 'lock'."
)


_client_lock = threading.Lock()
_client = None  # lazy
_batch_disabled = False  # tripped on auth error to silence per-bet spam


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                import anthropic  # lazy import
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    return None
                _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _cache_path(date: str, bet_id: str) -> Path:
    return _CACHE_DIR / date / f"{bet_id}.txt"


def _read_cache(date: str, bet_id: str) -> Optional[str]:
    p = _cache_path(date, bet_id)
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


def _write_cache(date: str, bet_id: str, text: str) -> None:
    p = _cache_path(date, bet_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(text.strip() + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("bet_narrator: failed to cache %s: %s", p, exc)


def _bet_to_prompt(bet: dict) -> str:
    """Compact JSON-ish user message — Claude reads it well, cheap on tokens."""
    side_word = "OVER" if bet["side"] == "OVER" else "UNDER"
    fields = {
        "player": bet.get("player_name"),
        "team": bet.get("team"),
        "opponent": bet.get("opp"),
        "venue": bet.get("venue"),
        "stat": bet.get("prop_stat"),
        "side": side_word,
        "line": bet.get("line"),
        "model_q50": bet.get("q50"),
        "edge_units": bet.get("edge_units"),
        "model_prob_pct": (bet.get("model_prob") or 0) * 100,
        "market_prob_pct": (bet.get("market_prob") or 0) * 100,
        "ev_pct": bet.get("ev_pct"),
        "last_5_median": bet.get("last_5_median"),
        "last_10_median": bet.get("last_10_median"),
        "season_median": bet.get("season_median"),
        "best_book": bet.get("best_book"),
        "best_price": bet.get("best_price"),
        "stars_available": bet.get("stars_available_flag"),
        "injury_status": bet.get("injury_status"),
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    return (
        "Bet to analyze (write a 2-3 sentence narrative). Reference at least "
        "one of: recent form (L5/L10 vs season), matchup, or role context. "
        "If L5 median is far above season median note the streak; if the line "
        "sits between L5 and L10 medians point it out.\n"
        + json.dumps(fields, separators=(",", ":"))
    )


def _call_claude(bet: dict) -> Optional[str]:
    global _batch_disabled
    if _batch_disabled:
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            timeout=_TIMEOUT_SEC,
            system=[{
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _bet_to_prompt(bet)}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        text = " ".join(parts).strip()
        return text or None
    except Exception as exc:
        msg = str(exc)
        if "401" in msg or "authentication" in msg.lower():
            if not _batch_disabled:
                log.warning("bet_narrator: ANTHROPIC_API_KEY invalid; "
                            "disabling narration for the rest of this batch.")
                _batch_disabled = True
        else:
            log.warning("bet_narrator: Claude call failed for %s: %s",
                        bet.get("bet_id"), exc)
        return None


def _narrate_one(bet: dict, date: str) -> Optional[str]:
    bet_id = bet.get("bet_id") or ""
    if not bet_id:
        return None
    cached = _read_cache(date, bet_id)
    if cached:
        return cached
    text = _call_claude(bet)
    if text:
        _write_cache(date, bet_id, text)
    return text


def narrate_slate(bets: list[dict], date: str,
                  max_bets: Optional[int] = None) -> None:
    """Mutate `bets` in place, replacing `narrative_text` with LLM output.

    No-op when ANTHROPIC_API_KEY is unset. Template narrative remains.
    Up to max_bets (default: all). Failures keep the original narrative.
    """
    if not bets:
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return
    global _batch_disabled
    _batch_disabled = False  # reset per slate build
    limit = max_bets if max_bets is not None else len(bets)
    target = bets[:limit]

    with ThreadPoolExecutor(max_workers=_N_WORKERS) as pool:
        futures = {pool.submit(_narrate_one, b, date): i
                   for i, b in enumerate(target)}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                text = fut.result()
            except Exception as exc:
                log.warning("bet_narrator: worker crashed: %s", exc)
                continue
            if text:
                target[i]["narrative_text"] = text
