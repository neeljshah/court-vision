"""scripts.platformkit.odds_provider.team_resolver -- code<->name canonical keys.

Our NBA/MLB slates carry SHORT CODES ("BOS", "CIN") while the odds feed
(ESPN/Kalshi/Polymarket) carries FULL names ("Boston Celtics", "Cincinnati
Reds"). `canonical(sport, name)` collapses EITHER form to one stable key per
team (e.g. canonical("nba","BOS") == canonical("nba","Boston Celtics")), so the
strict aggregate.teams_match can compare resolved keys and finally link codes to
full names -- WITHOUT loosening the false-match guard.

Honesty contract: an UNKNOWN team degrades to a normalized fallback (its own
nickname token), never a crash and never a collision with a different team.
Sports without codes (soccer/tennis/world-cup) pass through unchanged via the
same normalize path, so their existing full-name matching is untouched.

Maps are static 30-team reference literals copied from the repo's authoritative
sources (NBA: src/data/odds_scraper.py; MLB: domains/mlb/ingest_current.py).
Re-defined here (not imported) to avoid importing the gated src/ tree.
"""
from __future__ import annotations

import re
from typing import Dict

# --------------------------------------------------------------------------- #
# NBA: code -> canonical nickname token; full-name nickname is the same token.
# (Authoritative 30-team set; mirrors src/data/odds_scraper.py.)
# --------------------------------------------------------------------------- #
_NBA_CODE_TO_NICK: Dict[str, str] = {
    "ATL": "hawks", "BOS": "celtics", "BKN": "nets", "CHA": "hornets",
    "CHI": "bulls", "CLE": "cavaliers", "DAL": "mavericks", "DEN": "nuggets",
    "DET": "pistons", "GSW": "warriors", "HOU": "rockets", "IND": "pacers",
    "LAC": "clippers", "LAL": "lakers", "MEM": "grizzlies", "MIA": "heat",
    "MIL": "bucks", "MIN": "timberwolves", "NOP": "pelicans", "NYK": "knicks",
    "OKC": "thunder", "ORL": "magic", "PHI": "76ers", "PHX": "suns",
    "POR": "trailblazers", "SAC": "kings", "SAS": "spurs", "TOR": "raptors",
    "UTA": "jazz", "WAS": "wizards",
}
# ESPN/alt code spellings -> our canonical NBA code (mirrors ingest_espn_odds._ALIAS).
_NBA_CODE_ALIASES: Dict[str, str] = {
    "GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS", "UTAH": "UTA",
    "WSH": "WAS", "BRK": "BKN", "PHO": "PHX", "CHO": "CHA", "NOR": "NOP",
}

# --------------------------------------------------------------------------- #
# MLB: code -> canonical nickname token (mirrors domains/mlb NAME_TO_CODE,
# inverted). Same-city pairs (CWS White Sox vs CUB Cubs) get DISTINCT tokens.
# --------------------------------------------------------------------------- #
_MLB_CODE_TO_NICK: Dict[str, str] = {
    "ARI": "diamondbacks", "ATL": "braves", "BAL": "orioles", "BOS": "redsox",
    "CUB": "cubs", "CWS": "whitesox", "CIN": "reds", "CLE": "guardians",
    "COL": "rockies", "DET": "tigers", "HOU": "astros", "KAN": "royals",
    "LAA": "angels", "LAD": "dodgers", "MIA": "marlins", "MIL": "brewers",
    "MIN": "twins", "NYM": "mets", "NYY": "yankees", "OAK": "athletics",
    "PHI": "phillies", "PIT": "pirates", "SDG": "padres", "SFO": "giants",
    "SEA": "mariners", "STL": "cardinals", "TAM": "rays", "TEX": "rangers",
    "TOR": "bluejays", "WAS": "nationals",
}
# Common alternate MLB codes -> our canonical code.
_MLB_CODE_ALIASES: Dict[str, str] = {
    "CHC": "CUB", "CHW": "CWS", "SD": "SDG", "SF": "SFO", "KC": "KAN",
    "TB": "TAM", "WSH": "WAS", "WSN": "WAS", "ARZ": "ARI", "LA": "LAD",
}

# --------------------------------------------------------------------------- #
# KBO (LANE 4): code -> canonical nickname token = the parquet's OWN ASCII EN
# spelling (domains/baseball_kbo/kbo_results.parquet), lowercased. Kalshi's
# ODDS FEED (kalshi.py._team_label reads yes_sub_title, falling back to the
# market title) carries the club's FULL English name ("NC Dinos", "Kia
# Tigers", ...), NOT the ticker's 3-letter tail code -- verified live
# 2026-07-06 direct against /trade-api/v2/markets?series_ticker=KXKBOGAME
# (yes_sub_title == 'NC Dinos' for the NCD leg). _KBO_NAME_TO_CODE below is
# the single explicit map from each of the 10 real clubs' Kalshi full name to
# its exact parquet spelling; _NAME_NICK_FIXUPS folds each into the SAME
# multi-word-collapse mechanism NBA/MLB already use (e.g. "red sox"->
# "redsox") so "NC Dinos" and "NC" converge on one canonical key. NPB is NOT
# addable this way: the parquet's team names are Japanese kanji/katakana,
# which _norm's [^a-z0-9 ] regex strips to "" -- there is no ASCII nickname
# token to converge on, so NPB odds-matching stays a named, honest gap (see
# kalshi_listing.py module docstring / this lane's report) rather than a
# silently-broken code map.
# --------------------------------------------------------------------------- #
_KBO_NAME_TO_CODE: Dict[str, str] = {
    "nc dinos": "nc", "kia tigers": "kia", "lotte giants": "lotte",
    "kt wiz": "kt", "samsung lions": "samsung", "ssg landers": "ssg",
    "lg twins": "lg", "hanwha eagles": "hanwha", "kiwoom heroes": "kiwoom",
    "doosan bears": "doosan",
}
# NPB update (LANE 2, this fix): the ASCII-nickname-token mechanism above still
# cannot apply to NPB (the parquet's kanji/katakana strips to "" under _norm),
# but this is NO LONGER an unaddressed gap -- see _NPB_NAME_TO_KANJI +
# canonical()'s dedicated npb branch just below, which matches Kalshi's full
# English name to the parquet's RAW kanji spelling via an explicit 12-club map
# instead of the ASCII-nickname-convergence trick.

# --------------------------------------------------------------------------- #
# NPB (LANE 2): Kalshi's ODDS FEED (kalshi.py._team_label, same yes_sub_title/
# title fields KBO uses) carries each club's FULL English name ("Hanshin
# Tigers"), verified live 2026-07-06 direct against
# /trade-api/v2/markets?series_ticker=KXNPBGAME (both open + settled markets,
# all 12 real clubs). But NPB's parquet (data/domains/npb/npb_results.parquet)
# stores the npb.jp scrape's NATIVE Japanese kanji/katakana club name for each
# team, NOT an ASCII code -- so the KBO mechanism (normalize the full name ->
# ASCII nickname token -> match the parquet's OWN ASCII spelling) cannot
# apply: `_norm`'s [^a-z0-9 ] regex strips ALL kanji/katakana to "",
# meaning a kanji "code" has no ASCII nickname token to converge on (see the
# module-level note above and npb_outcome_resolver's module docstring).
#
# _NPB_NAME_TO_KANJI is the single explicit map from each of the 12 real NPB
# clubs' Kalshi full English name (lowercased, normalized the SAME way as
# every other name in this module) to the EXACT RAW (un-normalized) parquet
# kanji/katakana spelling -- mirrors npb_outcome_resolver._CODE_TO_NAME
# (ticker-code -> parquet name) one level up (full-name -> parquet name
# instead of ticker-code -> parquet name), cross-checked against the SAME
# live 2026-07-06 Kalshi probe.
# --------------------------------------------------------------------------- #
_NPB_NAME_TO_KANJI: Dict[str, str] = {
    # Keys are the ALREADY-_norm()-NORMALIZED Kalshi full name (lowercase,
    # punctuation incl. hyphens collapsed to spaces -- e.g. "Nippon-Ham" ->
    # "nippon ham") so a dict lookup on `norm` (canonical()'s already-normalized
    # string) hits directly; canonical() must NOT re-normalize these keys.
    "yokohama dena baystars": "DeNA",
    "tokyo yakult swallows": "ヤクルト",
    "hiroshima toyo carp": "広島",
    "hanshin tigers": "阪神",
    "hokkaido nippon ham fighters": "日本ハム",
    "tohoku rakuten golden eagles": "楽天",
    "saitama seibu lions": "西武",
    "orix buffaloes": "オリックス",
    "fukuoka hawks": "ソフトバンク",
    "fukuoka softbank hawks": "ソフトバンク",
    "chiba lotte marines": "ロッテ",
    "yomiuri giants": "巨人",
    "chunichi dragons": "中日",
}


def _kbo_code_to_nick() -> Dict[str, str]:
    """{ASCII EN code (lowercased) -> itself} for every real KBO club, derived
    from domains.baseball_kbo.team_map.ALL_EN_CODES (never hand-duplicated).
    Import-guarded: an import failure degrades to {} (kbo falls back to the
    prior strict-name-only matching, never a crash)."""
    try:
        from domains.baseball_kbo.team_map import ALL_EN_CODES
        return {code: code.lower() for code in ALL_EN_CODES}
    except Exception:  # noqa: BLE001 -- degrade, never bubble
        return {}


# Multi-word full-name nicknames that must collapse to a single token so a
# full name resolves to the SAME key as its code (e.g. "Red Sox" -> "redsox").
_NAME_NICK_FIXUPS = {
    ("nba", "trail blazers"): "trailblazers",
    ("mlb", "red sox"): "redsox",
    ("mlb", "white sox"): "whitesox",
    ("mlb", "blue jays"): "bluejays",
    **{("kbo", full): code for full, code in _KBO_NAME_TO_CODE.items()},
}

_CODE_TO_NICK = {"nba": _NBA_CODE_TO_NICK, "mlb": _MLB_CODE_TO_NICK,
                 "kbo": _kbo_code_to_nick()}
_CODE_ALIASES = {"nba": _NBA_CODE_ALIASES, "mlb": _MLB_CODE_ALIASES}
_STOP = {"the", "fc", "afc", "cf", "sc"}

# NPB (LANE 2): raw (un-normalized) parquet kanji/katakana spelling -> itself,
# used as the "code" key for npb (mirrors _kbo_code_to_nick's {code: code}
# shape, but keyed on the RAW string since kanji/katakana normalizes to ""
# under _norm -- see _NPB_NAME_TO_KANJI's module note above).
_NPB_KANJI_TO_SELF: Dict[str, str] = {k: k for k in set(_NPB_NAME_TO_KANJI.values())}
_CODE_TO_NICK["npb"] = _NPB_KANJI_TO_SELF


def _norm(name: str) -> str:
    """Lowercase, strip punctuation/stopwords -> space-joined tokens."""
    s = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    return " ".join(t for t in s.split() if t and t not in _STOP)


def canonical(sport: str, name: str) -> str:
    """Map a short code OR a full name to one canonical key per team.

    canonical("nba", "BOS") == canonical("nba", "Boston Celtics") == "nba:celtics".
    For sports without codes (soccer/tennis/world-cup) this is just the
    normalized full-name nickname token -- a pass-through that does not change
    their existing matching. Unknown input degrades to its normalized nickname
    token (never crashes, never collides with a known different team).

    NPB (LANE 2) special case: the parquet's own team spelling is Japanese
    kanji/katakana, which normalizes to "" (no ASCII survives _norm's regex),
    so it MUST be matched on the RAW string before normalization discards it.
    A Kalshi full English name ("Hanshin Tigers") still goes through the
    normal normalize-then-lookup path via _NPB_NAME_TO_KANJI.
    """
    sp = str(sport).lower()
    raw = str(name).strip()
    if sp == "npb" and raw in _NPB_KANJI_TO_SELF:
        return f"npb:{raw}"
    norm = _norm(raw)
    if not norm:
        return f"{sp}:"
    if sp == "npb":
        kanji = _NPB_NAME_TO_KANJI.get(norm)
        if kanji is not None:
            return f"npb:{kanji}"
        return f"npb:{norm.split()[-1]}"

    code_map = _CODE_TO_NICK.get(sp)
    if code_map is not None:
        # 1) Pure short code (a single all-letters token like "BOS"/"CIN").
        if " " not in norm:
            up = raw.upper().strip()
            up = _CODE_ALIASES.get(sp, {}).get(up, up)
            if up in code_map:
                return f"{sp}:{code_map[up]}"
        # 2) Full name -> nickname token via explicit multi-word fixups...
        for (fsp, phrase), tok in _NAME_NICK_FIXUPS.items():
            if fsp == sp and phrase in norm:
                return f"{sp}:{tok}"
        # 3) ...else nickname = last significant token; keep only if it is a
        #    real nickname for this sport (so it converges with the code key).
        last = norm.split()[-1]
        if last in set(code_map.values()):
            return f"{sp}:{last}"

    # Fallback (sports without codes, or unknown team): normalized last token.
    return f"{sp}:{norm.split()[-1]}"


__all__ = ["canonical"]
