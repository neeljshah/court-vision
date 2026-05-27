"""CryptoThresholdForecaster — GBM-based pricing of crypto threshold markets.

Handles question patterns like:
    - "Will Bitcoin be above $80,000 on May 27?"             (terminal threshold)
    - "Will Bitcoin reach $150,000 by June 30, 2026?"        (touch / path-dependent)
    - "Will ETH dip to $1,800 in June?"                      (touch from above)
    - "Will Bitcoin hit $150k by June 30, 2026?"             (touch / cumulative)

Method
------
1. Parse asset, strike, comparator (above/below/reach/dip), and resolution date.
2. Look up live spot via CoinGecko's free /simple/price endpoint (cached on disk
   per day to keep API hits to a handful per scan).
3. Estimate realized volatility from the last 30 days of daily closes (also via
   CoinGecko `/coins/{id}/market_chart?days=30`, cached daily).
4. Compute risk-neutral GBM probabilities:
       Terminal: P(S_T > K) = N( (ln(S/K) + (mu - 0.5 sigma^2) T) / (sigma sqrt T) )
                with mu = 0 by default (martingale assumption).
       Touch:    P(max S_t >= K) using reflection principle for log-GBM:
                = N(-d1) + (K/S)^(2 mu / sigma^2 - 1) * N(d2)
                For mu = 0 this collapses to: 2 * (1 - N(d1)) when K > S.
5. Return a Forecast with confidence scaled by time-to-expiry sanity and
   asset-recognition success.

This is *not* a money-printing oracle — it just gives an honest GBM baseline that
catches the most blatantly mispriced calendar threshold markets. Refinements like
implied vol from BVOL or sentiment-driven drift terms are out of scope here.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from predmarkets.edge_scanner import Forecast, Forecaster

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "cache", "crypto_forecaster",
)


_ASSET_MAP: Dict[str, Tuple[str, str]] = {
    # token -> (coingecko_id, canonical_symbol)
    "bitcoin": ("bitcoin", "BTC"),
    "btc": ("bitcoin", "BTC"),
    "ethereum": ("ethereum", "ETH"),
    "ether": ("ethereum", "ETH"),
    "eth": ("ethereum", "ETH"),
    "solana": ("solana", "SOL"),
    "sol": ("solana", "SOL"),
    "dogecoin": ("dogecoin", "DOGE"),
    "doge": ("dogecoin", "DOGE"),
    "xrp": ("ripple", "XRP"),
    "ripple": ("ripple", "XRP"),
    "cardano": ("cardano", "ADA"),
    "ada": ("cardano", "ADA"),
    "polygon": ("polygon-ecosystem-token", "POL"),
    "matic": ("polygon-ecosystem-token", "POL"),
    "litecoin": ("litecoin", "LTC"),
    "ltc": ("litecoin", "LTC"),
    "avalanche": ("avalanche-2", "AVAX"),
    "avax": ("avalanche-2", "AVAX"),
}

_BELOW_WORDS = ("below", "under", "dip", "drop")
_TOUCH_WORDS = ("reach", "hit", "touch", "exceed", "above ever", "fall to", "dip to", "drop to")
# Patterns indicating multi-strike markets the simple above/below parser can't score.
_RANGE_PATTERNS = (
    re.compile(r"between\s+\$", re.IGNORECASE),
    re.compile(r"\$[\d,kKmM\.]+\s*[-–to]+\s*\$[\d,kKmM\.]+", re.IGNORECASE),
    re.compile(r"\bin the range\b", re.IGNORECASE),
)
# $X[kKmM]? — suffix must be adjacent (no whitespace) and followed by a word
# boundary, otherwise '$72,000 May' parses '$72,000 M' as 72 billion.
_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)(?:([kKmM])(?![a-zA-Z]))?")

# Comparator-anchored fallback: 'above 75,400', 'reach 100k', 'dip to 70000'.
# The number must either have a thousands-comma OR a k/m suffix, to avoid
# matching dates like 'May 27' or 'in 2026'.
_PRICE_NEAR_COMP_RE = re.compile(
    r"(?:above|below|under|over|reach|reaches|reached|hit|hits|hits?\s+at|to|exceed|exceeds|dip\s+to|drop\s+to|fall\s+to)"
    r"\s+\$?\s*("
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"      # 75,400 or 1,000,000.50
    r"|\d+(?:\.\d+)?[kKmM](?![a-zA-Z])"  # 85k, 1.5m
    r"|\d{5,}"                            # plain 75400+
    r")\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:on|by|in)?\s*"
    r"(?:(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r"\s+(?P<day>\d{1,2})?(?:,?\s*(?P<year>\d{4}))?"
    r"|(?P<iso>\d{4}-\d{2}-\d{2}))",
    re.IGNORECASE,
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
)}


@dataclass
class _Parsed:
    asset_id: str
    asset_symbol: str
    strike: float
    direction: str        # "above" | "below"
    is_touch: bool
    resolution_ts: Optional[float]


@dataclass
class _ParsedRange:
    asset_id: str
    asset_symbol: str
    lower: float
    upper: float
    resolution_ts: Optional[float]


def _parse_price(text: str) -> Optional[float]:
    m = _PRICE_RE.search(text)
    if m is not None:
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            v = None
        if v is not None:
            suffix = (m.group(2) or "").lower()
            if suffix == "k":
                v *= 1_000.0
            elif suffix == "m":
                v *= 1_000_000.0
            return v
    # Fallback: comparator-anchored, allows missing $ (e.g. 'Bitcoin above 75,400').
    m2 = _PRICE_NEAR_COMP_RE.search(text)
    if m2 is None:
        return None
    raw = m2.group(1).replace(",", "")
    suffix = ""
    if raw and raw[-1].lower() in ("k", "m"):
        suffix = raw[-1].lower()
        raw = raw[:-1]
    try:
        v = float(raw)
    except ValueError:
        return None
    if suffix == "k":
        v *= 1_000.0
    elif suffix == "m":
        v *= 1_000_000.0
    return v


def _parse_date(text: str, now: Optional[datetime] = None) -> Optional[float]:
    now = now or datetime.now(timezone.utc)
    for m in _DATE_RE.finditer(text):
        if m.group("iso"):
            try:
                dt = datetime.fromisoformat(m.group("iso")).replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except ValueError:
                continue
        month_str = (m.group("month") or "").lower()[:3]
        if month_str not in _MONTHS:
            continue
        month = _MONTHS[month_str]
        day_raw = m.group("day")
        day = int(day_raw) if day_raw else 28  # default to month-end-ish
        year_raw = m.group("year")
        year = int(year_raw) if year_raw else now.year
        # If the month is in the past for the current year, assume next year.
        if not year_raw and month < now.month:
            year += 1
        try:
            dt = datetime(year, month, day, 23, 59, tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None


# Range market: 'between $A and $B', '$A-$B', 'in the range $A-$B'.
# Captures both strikes.
_RANGE_PARSE_RE = re.compile(
    r"(?:between|range\s+of?|from)\s+"
    r"\$?\s*([\d,]+(?:\.\d+)?(?:[kKmM])?)"
    r"\s+(?:and|to|-|–)\s+"
    r"\$?\s*([\d,]+(?:\.\d+)?(?:[kKmM])?)",
    re.IGNORECASE,
)
_RANGE_DASH_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?(?:[kKmM])?)\s*[-–]\s*\$\s*([\d,]+(?:\.\d+)?(?:[kKmM])?)"
)


def _parse_num_with_suffix(raw: str) -> Optional[float]:
    raw = raw.strip().replace(",", "")
    suffix = ""
    if raw and raw[-1].lower() in ("k", "m"):
        suffix = raw[-1].lower()
        raw = raw[:-1]
    try:
        v = float(raw)
    except ValueError:
        return None
    if suffix == "k":
        v *= 1_000.0
    elif suffix == "m":
        v *= 1_000_000.0
    return v


def _parse_range_question(question: str, end_date_iso: Optional[str] = None) -> Optional[_ParsedRange]:
    """Parse 'BTC between $A and $B by date Z' style markets."""
    if not question:
        return None
    q = question.lower()
    asset_id: Optional[str] = None
    asset_symbol: Optional[str] = None
    for token, (cg_id, sym) in _ASSET_MAP.items():
        if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", q):
            asset_id = cg_id
            asset_symbol = sym
            break
    if asset_id is None:
        return None
    m = _RANGE_PARSE_RE.search(question)
    if m is None:
        m = _RANGE_DASH_RE.search(question)
    if m is None:
        return None
    lower = _parse_num_with_suffix(m.group(1))
    upper = _parse_num_with_suffix(m.group(2))
    if lower is None or upper is None or lower <= 0 or upper <= 0:
        return None
    if lower > upper:
        lower, upper = upper, lower
    resolution_ts: Optional[float] = None
    if end_date_iso:
        try:
            dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            resolution_ts = dt.timestamp()
        except ValueError:
            pass
    if resolution_ts is None:
        resolution_ts = _parse_date(question)
    return _ParsedRange(
        asset_id=asset_id,
        asset_symbol=asset_symbol or "?",
        lower=lower,
        upper=upper,
        resolution_ts=resolution_ts,
    )


def _parse_question(question: str, end_date_iso: Optional[str] = None) -> Optional[_Parsed]:
    if not question:
        return None
    # Range / multi-strike markets need their own pricing path; this single-strike
    # parser would wrongly treat "between $A and $B" as "above $A".
    if any(p.search(question) for p in _RANGE_PATTERNS):
        return None
    q = question.lower()
    asset_id: Optional[str] = None
    asset_symbol: Optional[str] = None
    for token, (cg_id, sym) in _ASSET_MAP.items():
        # word-boundary match so 'eth' inside 'netherlands' doesn't trigger
        if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", q):
            asset_id = cg_id
            asset_symbol = sym
            break
    if asset_id is None:
        return None
    strike = _parse_price(question)
    if strike is None:
        return None
    direction = "below" if any(w in q for w in _BELOW_WORDS) else "above"
    is_touch = any(w in q for w in _TOUCH_WORDS) or " by " in q or " in " in q
    resolution_ts: Optional[float] = None
    if end_date_iso:
        try:
            dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            resolution_ts = dt.timestamp()
        except ValueError:
            pass
    if resolution_ts is None:
        resolution_ts = _parse_date(question)
    return _Parsed(
        asset_id=asset_id,
        asset_symbol=asset_symbol or "?",
        strike=strike,
        direction=direction,
        is_touch=is_touch,
        resolution_ts=resolution_ts,
    )


def _phi(x: float) -> float:
    """Standard-normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _gbm_prob_above(spot: float, strike: float, sigma_annual: float,
                    years: float, drift: float = 0.0) -> float:
    """P(S_T > K) under GBM with given annualized vol and drift (default 0)."""
    if spot <= 0 or strike <= 0 or sigma_annual <= 0 or years <= 0:
        return 1.0 if spot > strike else 0.0
    s = sigma_annual * math.sqrt(years)
    d = (math.log(spot / strike) + (drift - 0.5 * sigma_annual ** 2) * years) / s
    return _phi(d)


def _gbm_prob_touch(spot: float, strike: float, sigma_annual: float,
                    years: float, drift: float = 0.0, direction: str = "above") -> float:
    """P(max/min S_t hits K before T) under GBM (reflection principle).

    For direction='above' (K > S0): P(max >= K). Closed form:
        N(d1) + (K/S0)^(2mu/sigma^2 - 1) * N(d2)
        d1 = (ln(S0/K) - (mu - 0.5 sigma^2)T) / (sigma sqrt T)
        d2 = (ln(S0/K) + (mu - 0.5 sigma^2)T) / (sigma sqrt T)
    For drift=0 this simplifies to 2 * (1 - N(-d1)) = 2 * N(d1) when K > S0.
    Symmetric form for direction='below'.
    """
    if spot <= 0 or strike <= 0 or sigma_annual <= 0 or years <= 0:
        if direction == "above":
            return 1.0 if spot >= strike else 0.0
        return 1.0 if spot <= strike else 0.0
    if direction == "above" and spot >= strike:
        return 1.0
    if direction == "below" and spot <= strike:
        return 1.0
    if direction == "below":
        # Symmetric: P(min <= K) = P(max(1/S) >= 1/K). Same formula with swapped sign.
        return _gbm_prob_touch(strike, spot, sigma_annual, years, drift, direction="above")
    s = sigma_annual * math.sqrt(years)
    log_ratio = math.log(spot / strike)
    d1 = (log_ratio - (drift - 0.5 * sigma_annual ** 2) * years) / s
    d2 = (log_ratio + (drift - 0.5 * sigma_annual ** 2) * years) / s
    if drift == 0.0:
        # Symmetric simplification when drift is zero
        return min(1.0, 2.0 * _phi(d1))
    power = 2.0 * drift / (sigma_annual ** 2) - 1.0
    barrier_factor = math.pow(strike / spot, power)
    return min(1.0, _phi(d1) + barrier_factor * _phi(d2))


class _CoinGeckoClient:
    """Tiny rate-limited CoinGecko reader with per-day on-disk cache."""

    BASE = "https://api.coingecko.com/api/v3"

    def __init__(self, rps: float = 1.0, cache_dir: str = CACHE_DIR) -> None:
        self.rps = rps
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self._last_call = 0.0
        self._sess = requests.Session()
        self._sess.headers.update({"User-Agent": "nba-ai-system/predmarkets-crypto-1.0"})

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        wait = max(0.0, (1.0 / self.rps) - elapsed)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _cache_path(self, key: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        safe = re.sub(r"[^a-z0-9_\-]", "_", key.lower())
        return os.path.join(self.cache_dir, f"{day}__{safe}.json")

    def _get_cached(self, key: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        cache_file = self._cache_path(key)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        self._throttle()
        resp = self._sess.get(f"{self.BASE}{path}", params=params or {}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        try:
            with open(cache_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        except OSError:
            pass
        return data

    def spot(self, asset_ids: List[str]) -> Dict[str, float]:
        if not asset_ids:
            return {}
        key = "spot__" + ",".join(sorted(set(asset_ids)))
        data = self._get_cached(key, "/simple/price", {
            "ids": ",".join(sorted(set(asset_ids))),
            "vs_currencies": "usd",
        })
        return {k: float(v.get("usd")) for k, v in data.items() if v and v.get("usd") is not None}

    def historical_vol(self, asset_id: str, days: int = 30) -> Optional[float]:
        """Annualized realized vol from daily log returns over the last `days`."""
        data = self._get_cached(
            f"vol__{asset_id}__{days}",
            f"/coins/{asset_id}/market_chart",
            {"vs_currency": "usd", "days": str(days)},
        )
        prices = [float(p[1]) for p in data.get("prices", []) if p and len(p) == 2]
        if len(prices) < 5:
            return None
        rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
        if len(rets) < 2:
            return None
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        sd_daily = math.sqrt(var)
        # CoinGecko market_chart with days<=90 returns hourly-ish samples;
        # >90 returns daily. We requested 30 -> hourly buckets. Detect by len(rets):
        # if rets is much larger than `days`, it's hourly — annualize accordingly.
        samples_per_day = max(1.0, len(rets) / max(1, days))
        return sd_daily * math.sqrt(samples_per_day * 365.0)


class CryptoThresholdForecaster(Forecaster):
    """GBM-based forecaster for crypto threshold prediction markets."""

    name = "crypto_threshold_gbm"

    def __init__(self, coingecko: Optional[_CoinGeckoClient] = None,
                 default_drift: float = 0.0,
                 confidence_floor: float = 0.25,
                 confidence_cap: float = 0.55) -> None:
        self._cg = coingecko or _CoinGeckoClient()
        self.default_drift = default_drift
        self.confidence_floor = confidence_floor
        self.confidence_cap = confidence_cap
        self._spot_cache: Dict[str, float] = {}
        self._vol_cache: Dict[str, float] = {}

    def applies_to(self, market: Dict[str, Any]) -> bool:
        if (market.get("category") or "").lower() != "crypto":
            return False
        question = market.get("question_or_title") or market.get("question") or ""
        end_date = market.get("end_date")
        if _parse_question(question, end_date) is not None:
            return True
        if _parse_range_question(question, end_date) is not None:
            return True
        return False

    def _get_spot(self, asset_id: str) -> Optional[float]:
        if asset_id not in self._spot_cache:
            try:
                fetched = self._cg.spot([asset_id])
            except Exception:
                fetched = {}
            if asset_id in fetched:
                self._spot_cache[asset_id] = fetched[asset_id]
        return self._spot_cache.get(asset_id)

    def _get_vol(self, asset_id: str) -> Optional[float]:
        if asset_id not in self._vol_cache:
            try:
                v = self._cg.historical_vol(asset_id)
            except Exception:
                v = None
            if v is not None:
                self._vol_cache[asset_id] = v
        return self._vol_cache.get(asset_id)

    def _range_forecast(self, market: Dict[str, Any], question: str) -> Optional[Forecast]:
        """Price a 'between $A and $B' market as P(K1 <= S_T <= K2)."""
        parsed = _parse_range_question(question, market.get("end_date"))
        if parsed is None or parsed.resolution_ts is None:
            return None
        spot = self._get_spot(parsed.asset_id)
        sigma = self._get_vol(parsed.asset_id)
        if spot is None or sigma is None:
            return None
        now = time.time()
        years = max(0.0, (parsed.resolution_ts - now) / (365.0 * 86400.0))
        if years <= 0:
            prob = 1.0 if parsed.lower <= spot <= parsed.upper else 0.0
        else:
            # P(K1 <= S_T <= K2) = P(S_T > K1) - P(S_T > K2)
            p_above_lower = _gbm_prob_above(spot, parsed.lower, sigma, years, drift=self.default_drift)
            p_above_upper = _gbm_prob_above(spot, parsed.upper, sigma, years, drift=self.default_drift)
            prob = max(0.0, p_above_lower - p_above_upper)
        prob = max(0.0, min(1.0, prob))
        days = years * 365.0
        # Confidence: range markets are tighter than single-strike thresholds;
        # smaller relative width = better calibrated under GBM assumption.
        width_pct = (parsed.upper - parsed.lower) / max(1.0, spot)
        horizon_score = 1.0 if 1.0 <= days <= 180.0 else 0.5
        width_score = min(1.0, width_pct / 0.10)  # 10%-wide range = full credit
        confidence = self.confidence_floor + (self.confidence_cap - self.confidence_floor) * \
            0.5 * (horizon_score + width_score)
        confidence = min(self.confidence_cap, max(self.confidence_floor, confidence))
        reasoning = (
            f"GBM-range {parsed.asset_symbol} spot=${spot:,.0f} "
            f"[${parsed.lower:,.0f}, ${parsed.upper:,.0f}] "
            f"sigma_ann={sigma:.3f} T={days:.1f}d"
        )
        return Forecast(
            market_id=str(market.get("market_id") or market.get("id") or ""),
            prob_yes=prob,
            confidence=confidence,
            model_name=f"{self.name}_range",
            reasoning=reasoning,
        )

    def forecast(self, market: Dict[str, Any]) -> Optional[Forecast]:
        question = market.get("question_or_title") or market.get("question") or ""
        # Try range pricer first — only matches multi-strike questions.
        range_forecast = self._range_forecast(market, question)
        if range_forecast is not None:
            return range_forecast
        parsed = _parse_question(question, market.get("end_date"))
        if parsed is None or parsed.resolution_ts is None:
            return None
        spot = self._get_spot(parsed.asset_id)
        sigma = self._get_vol(parsed.asset_id)
        if spot is None or sigma is None:
            return None
        now = time.time()
        years = max(0.0, (parsed.resolution_ts - now) / (365.0 * 86400.0))
        if years <= 0:
            # Already past expiry — the market should be resolved already.
            prob = 1.0 if (parsed.direction == "above" and spot > parsed.strike) or \
                          (parsed.direction == "below" and spot < parsed.strike) else 0.0
        elif parsed.is_touch:
            prob = _gbm_prob_touch(spot, parsed.strike, sigma, years,
                                   drift=self.default_drift, direction=parsed.direction)
        elif parsed.direction == "above":
            prob = _gbm_prob_above(spot, parsed.strike, sigma, years, drift=self.default_drift)
        else:
            prob = 1.0 - _gbm_prob_above(spot, parsed.strike, sigma, years, drift=self.default_drift)
        prob = max(0.0, min(1.0, prob))
        # Confidence scales down for very short or very long horizons (vol regime
        # uncertainty) and for far-OTM strikes (tail risk underestimated by GBM).
        days = years * 365.0
        horizon_score = 1.0 if 1.0 <= days <= 180.0 else 0.5
        moneyness = abs(math.log(parsed.strike / spot)) if spot > 0 and parsed.strike > 0 else 0.0
        moneyness_score = max(0.0, 1.0 - moneyness / 1.0)  # 1.0 = ATM, 0 = e^1 away
        confidence = self.confidence_floor + (self.confidence_cap - self.confidence_floor) * \
            0.5 * (horizon_score + moneyness_score)
        confidence = min(self.confidence_cap, max(self.confidence_floor, confidence))
        reasoning = (
            f"GBM {parsed.asset_symbol} spot=${spot:,.0f} strike=${parsed.strike:,.0f} "
            f"sigma_ann={sigma:.3f} T={days:.1f}d "
            f"{'touch' if parsed.is_touch else 'terminal'} {parsed.direction}"
        )
        return Forecast(
            market_id=str(market.get("market_id") or market.get("id") or ""),
            prob_yes=prob,
            confidence=confidence,
            model_name=self.name,
            reasoning=reasoning,
        )


__all__ = ["CryptoThresholdForecaster"]
