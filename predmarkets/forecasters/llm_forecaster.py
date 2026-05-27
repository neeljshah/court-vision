"""LLMForecaster — Claude-backed forecaster for non-crypto prediction markets.

Wraps a Claude API call that produces a calibrated probability + reasoning for
a market question. Designed for markets without a structured pricing model:
politics, world events, entertainment, science.

Cost / rate-limit control:
    - Daily on-disk cache per (market_id, date) so re-runs cost nothing.
    - Defaults to Haiku 4.5 for affordability (~$0.001 / market).
    - Prompt caching on the system prompt (5-min ephemeral) so a batch of N
      questions only pays the system-prompt input tokens once.
    - Gracefully no-ops with applies_to() = False if ANTHROPIC_API_KEY is not
      set or the anthropic SDK is missing.

Note: probabilities from LLM forecasters are noisy. The forecaster reports
confidence around 0.30 so the EdgeScanner Kelly sizing stays conservative.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from predmarkets.edge_scanner import Forecast, Forecaster


_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "cache", "llm_forecaster",
)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_SYSTEM_PROMPT = """You are a calibrated forecaster scoring prediction-market questions.

For each question I send, you will reply with a single JSON object on one line:
{"prob_yes": float in [0,1], "reasoning": "<= 200 chars", "confidence": "low" | "med" | "high"}

Rules:
- Use base rates first. If a specific person winning a future election, default to <= 0.05 unless they are a leading candidate per the most recent polling you know about.
- If the event is improbable on its face (e.g. obscure candidate, narrow timing, sci-fi outcome), prob_yes <= 0.02.
- If the question is about something already-decided (event already happened/didn't happen by the question's date), set confidence=high and prob_yes near 0 or 1.
- If you don't have enough information to be calibrated (e.g. very niche, requires very fresh news), reply with prob_yes equal to the market-implied price the user gives you, confidence="low", reasoning="insufficient information".
- Be honest: do not claim certainty you do not have.
- Output JUST the JSON object. No prose, no markdown fence, no leading text.
"""

_CATEGORY_DENYLIST = {"Crypto"}  # has its own GBM forecaster
_CATEGORY_ALLOWLIST: Optional[set] = None  # if None, allow everything not in denylist


_JSON_RE = re.compile(r"\{[^{}]*\"prob_yes\"[^{}]*\}", re.DOTALL)


def _cache_key(market_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", market_id)[:80]
    return f"{today}__{safe_id}.json"


def _read_cache(market_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(_CACHE_DIR, _cache_key(market_id))
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(market_id: str, payload: Dict[str, Any]) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, _cache_key(market_id))
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except OSError:
        pass


def _parse_response(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    # Strip a code fence if Claude wrapped despite instructions.
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"```$", "", text).strip()
    candidates = [text]
    m = _JSON_RE.search(text)
    if m:
        candidates.append(m.group(0))
    for c in candidates:
        try:
            data = json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        prob = data.get("prob_yes")
        if prob is None:
            continue
        try:
            prob_f = float(prob)
        except (TypeError, ValueError):
            continue
        if not 0.0 <= prob_f <= 1.0:
            continue
        return {
            "prob_yes": prob_f,
            "reasoning": str(data.get("reasoning", ""))[:240],
            "confidence_label": str(data.get("confidence", "med")).lower(),
        }
    return None


def _confidence_score(label: str) -> float:
    return {"low": 0.15, "med": 0.30, "high": 0.45}.get(label, 0.25)


def _has_anthropic() -> bool:
    try:
        import anthropic  # noqa: F401
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    except ImportError:
        return False


class LLMForecaster(Forecaster):
    """Claude-backed probability forecaster for non-crypto markets."""

    name = "llm_claude"

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 300,
        rps: float = 4.0,
        min_volume_24h: float = 5_000.0,
        category_denylist: Optional[set] = None,
        client: Any = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._min_rps_interval = 1.0 / max(0.1, rps)
        self._last_call = 0.0
        self._client = client
        self._client_ok: Optional[bool] = None
        self._min_volume_24h = min_volume_24h
        self._denylist = set(category_denylist or _CATEGORY_DENYLIST)

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_ok is False:
            return None
        try:
            import anthropic
            if not os.environ.get("ANTHROPIC_API_KEY"):
                self._client_ok = False
                return None
            self._client = anthropic.Anthropic()
            self._client_ok = True
            return self._client
        except ImportError:
            self._client_ok = False
            return None

    def applies_to(self, market: Dict[str, Any]) -> bool:
        if self._client_ok is False:
            return False
        if self._ensure_client() is None:
            return False
        if (market.get("category") or "") in self._denylist:
            return False
        question = market.get("question_or_title") or market.get("question") or ""
        if not question:
            return False
        if market.get("status") and market["status"] != "open":
            return False
        try:
            vol24 = float(market.get("volume_24h") or 0.0)
        except (TypeError, ValueError):
            vol24 = 0.0
        if vol24 < self._min_volume_24h:
            return False
        return True

    def _ask_claude(self, question: str, market_price: float, end_date: str) -> Optional[Dict[str, Any]]:
        client = self._ensure_client()
        if client is None:
            return None
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_rps_interval:
            time.sleep(self._min_rps_interval - elapsed)
        user_msg = (
            f"Question: {question}\n"
            f"Market-implied YES probability: {market_price:.4f}\n"
            f"Resolves by: {end_date or 'unknown'}\n"
            f"Today is: {date.today().isoformat()}\n"
            f"Respond with ONLY the JSON object."
        )
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[{
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_msg}],
            )
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            self._last_call = time.monotonic()
        try:
            text = resp.content[0].text if resp.content else ""
        except (AttributeError, IndexError):
            text = ""
        parsed = _parse_response(text)
        if parsed is None:
            return {"error": f"unparseable response: {text[:200]}"}
        parsed["raw_text"] = text[:400]
        return parsed

    def _market_implied_yes(self, market: Dict[str, Any]) -> float:
        yb = market.get("yes_bid")
        ya = market.get("yes_ask")
        if yb is not None and ya is not None:
            try:
                return (float(yb) + float(ya)) / 2.0
            except (TypeError, ValueError):
                pass
        for k in ("last_price", "yes_bid", "yes_ask"):
            v = market.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return 0.5

    def forecast(self, market: Dict[str, Any]) -> Optional[Forecast]:
        if not self.applies_to(market):
            return None
        market_id = str(market.get("market_id") or market.get("id") or "")
        if not market_id:
            return None
        cached = _read_cache(market_id)
        if cached is None:
            question = market.get("question_or_title") or market.get("question") or ""
            price = self._market_implied_yes(market)
            end_iso = market.get("end_date") or market.get("endDate") or ""
            result = self._ask_claude(question, price, str(end_iso))
            if result is None or "error" in result:
                # Cache the error so we don't retry the same broken response all day
                _write_cache(market_id, result or {"error": "no_client"})
                return None
            _write_cache(market_id, result)
            cached = result
        if "error" in cached or "prob_yes" not in cached:
            return None
        return Forecast(
            market_id=market_id,
            prob_yes=float(cached["prob_yes"]),
            confidence=_confidence_score(cached.get("confidence_label", "med")),
            model_name=f"{self.name}/{self.model}",
            reasoning=str(cached.get("reasoning", ""))[:240],
        )


__all__ = ["LLMForecaster"]
