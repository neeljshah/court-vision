"""Generic title and probe gate for footage-queue items.

Every queue item, including legacy entries, is admitted through this module.
The 90-second probe is disposable only after it has passed; rejected probes are
moved to quarantine with a sidecar, never deleted.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from scripts.platformkit import footage_content_gate
from scripts.platformkit.tracking import footage_census

# CREATE_NO_WINDOW: every console child of the console-less agent Bash tool
# (ssh, scp, yt-dlp, ffprobe) allocates its OWN console on Windows and pops a
# terminal window. Seven lanes plus a five-minute watchdog made that a stream of
# windows across the desktop; the user asked three times for it to stop.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


PROBE_SECONDS = 90
GATE_VERSION = 3
REVIEW_DIR = Path("data/footage_review")
QUARANTINE_DIR = Path("data/footage_quarantine")
_REJECT = ("presser", "press conference", "podcast", "reaction", "esports",
           "gameplay", "pes", "ea sports", "ceremony", "q&a", "interview",
           "coaching clinic", "studio", "talk show")
_DESCRIPTION_REJECT = ("press conference", "podcast", "reaction", "gameplay", "esports")
_SPORT_TERMS = {
    "tennis": ("tennis",),
    "wnba": ("wnba", "basketball", "women's basketball", "womens basketball",
             "women-s basketball", "ncaa"),
    "npb": ("npb", "japanese baseball", "baseball"),
    "kbo": ("kbo", "korean baseball", "baseball"),
    "soccer": ("soccer", "football"),
    "football": ("football", "nfl", "american football"),
    "mlb": ("mlb", "major league baseball", "baseball"),
    "nhl": ("nhl", "hockey", "ice hockey"),
    "ncaa_basketball": ("ncaa", "basketball", "march madness"),
    "cricket": ("cricket",),
    "handball": ("handball",),
    "volleyball": ("volleyball",),
}
_WORD_OR_HYPHENATED = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class GateResult:
    decision: str
    reason: str
    title: str
    description: str
    review_dir: str = ""


def _tokens(text: str) -> tuple[str, ...]:
    """Lowercase tokens, retaining hyphenated forms and their component words."""
    tokens: list[str] = []
    for word in _WORD_OR_HYPHENATED.findall(text.lower()):
        tokens.append(word)
        if "-" in word:
            tokens.extend(word.split("-"))
    return tuple(tokens)


def _contains_phrase(tokens: tuple[str, ...], phrase: str) -> bool:
    phrase_tokens = _tokens(phrase)
    width = len(phrase_tokens)
    return bool(phrase_tokens) and any(
        tokens[index:index + width] == phrase_tokens
        for index in range(len(tokens) - width + 1)
    )


def _first_matching_phrase(tokens: tuple[str, ...], phrases: tuple[str, ...]) -> str | None:
    return next((phrase for phrase in phrases if _contains_phrase(tokens, phrase)), None)


def title_rejection(sport: str, title: str, description: str) -> str | None:
    """Return a title rejection or ambiguity; description is empty-title-only."""
    if sport not in _SPORT_TERMS:
        raise ValueError("Unsupported sport: %s" % sport)
    title_tokens = _tokens(title or "")
    if not title_tokens:
        description_tokens = _tokens(description or "")
        phrase = _first_matching_phrase(description_tokens, _DESCRIPTION_REJECT)
        return "title_reject:%s" % phrase.replace(" ", "_") if phrase else None
    phrase = _first_matching_phrase(title_tokens, _REJECT)
    if phrase:
        return "title_reject:%s" % phrase.replace(" ", "_")
    target_terms = _SPORT_TERMS[sport]
    target_match = _first_matching_phrase(title_tokens, target_terms)
    own_terms = set(target_terms)
    other_match: str | None = None
    for other_sport, terms in _SPORT_TERMS.items():
        if other_sport == sport:
            continue
        candidates = tuple(term for term in terms if term not in own_terms)
        if _first_matching_phrase(title_tokens, candidates):
            other_match = other_sport
            break
    if not other_match:
        return None
    if target_match:
        return "title_ambiguous"
    return "title_reject:other_sport_%s" % other_match


def fetch_metadata(url: str) -> tuple[str, str]:
    """Fetch title and description only; never download media for this step."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--no-playlist", "--dump-single-json", url],
            check=True, capture_output=True, text=True, timeout=90,
            creationflags=_NO_WINDOW,
        )
        payload = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return "", ""
    return str(payload.get("title") or ""), str(payload.get("description") or "")


def _metadata(item: dict[str, str]) -> tuple[str, str]:
    title = str(item.get("title") or "")
    description = str(item.get("description") or "")
    if title and description:
        return title, description
    fetched_title, fetched_description = fetch_metadata(item.get("url", ""))
    return title or fetched_title, description or fetched_description


def _probe_download(url: str, output: Path, cookies_file: Path) -> bool:
    command = ["yt-dlp", "--no-playlist", "--no-part", "--download-sections",
               "*00:10:00-00:11:30", "--extractor-args", "youtube:player_client=web",
               "--merge-output-format", "mp4", "-f", "worst[height<=360]/worst",
               "-o", str(output), url]
    if cookies_file.is_file():
        command[1:1] = ["--cookies", str(cookies_file)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=240,
                       creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    return output.is_file()


def _queue_sidecar(item: dict[str, str], reason: str) -> None:
    game_id = str(item.get("game_id") or "unknown")
    footage_content_gate.write_quarantine_sidecar(
        QUARANTINE_DIR / (game_id + ".queue.json"), reason,
        {"queue_item": item, "gate": "queue_content_gate"})


def _probe_result(item: dict[str, str], sport: str, cookies_file: Path) -> GateResult:
    game_id = str(item.get("game_id") or "unknown")
    with tempfile.TemporaryDirectory(prefix="queue_content_gate_") as directory:
        probe = Path(directory) / (sport + "__" + game_id + ".mp4")
        if not _probe_download(item.get("url", ""), probe, cookies_file):
            return GateResult("SUSPECT", "probe_download_unavailable", "", "")
        try:
            row, frames = footage_census.census_clip(probe, sample_count=12)
        except (OSError, ValueError, footage_census.cv2.error) as exc:
            return GateResult("SUSPECT", "probe_census_unavailable:%s" % str(exc)[:80], "", "")
        if row.verdict == "JUNK":
            footage_content_gate.quarantine_manual(probe, "queue_probe_census_junk",
                                                    destination=QUARANTINE_DIR)
            return GateResult("JUNK", "probe_census_junk", "", "")
        if row.verdict == "SUSPECT":
            review = REVIEW_DIR / game_id
            footage_census.render_sample(frames, game_id, review)
            return GateResult("SUSPECT", "probe_census_suspect", "", "", str(review))
        return GateResult("USABLE", "probe_census_usable", "", "")


def screen_item(item: dict[str, str], sport: str, cookies_file: Path) -> GateResult:
    """Screen one queue entry using title evidence then a 12-frame probe census."""
    title, description = _metadata(item)
    reason = title_rejection(sport, title, description)
    if reason and reason.startswith("title_reject:"):
        _queue_sidecar(item, reason)
        return GateResult("JUNK", reason, title, description)
    result = _probe_result(item, sport, cookies_file)
    if reason == "title_ambiguous":
        return GateResult(result.decision, reason, title, description, result.review_dir)
    if not title and not description:
        return GateResult(result.decision, "title_unknown:%s" % result.reason,
                          title, description, result.review_dir)
    return GateResult(result.decision, result.reason, title, description, result.review_dir)


def _already_screened(item: dict[str, str]) -> bool:
    marker = item.get("content_gate")
    return (isinstance(marker, dict) and marker.get("version") == GATE_VERSION
            and marker.get("decision") in {"USABLE", "SUSPECT"})


def gate_items(items: list[dict[str, str]], sport: str, cookies_file: Path) -> list[dict[str, str]]:
    """Keep USABLE/SUSPECT entries and persist their audit marker in queue JSON."""
    kept: list[dict[str, str]] = []
    for item in items:
        if _already_screened(item):
            kept.append(item)
            continue
        result = screen_item(item, sport, cookies_file)
        if result.decision == "JUNK":
            continue
        marked = dict(item)
        marked["title"] = result.title
        marked["description"] = result.description
        marked["content_gate"] = {"version": GATE_VERSION, "decision": result.decision,
                                  "reason": result.reason, "review_dir": result.review_dir}
        kept.append(marked)
    return kept
