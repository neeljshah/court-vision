"""scripts.platformkit.brain_critic — LLM-Judge / Critic: adversarial self-check before memory write.

META-COGNITION ORGAN (the gate as conscience; 06_INTELLIGENCE.md §4.3).
AUDITS findings before brain writes; NEVER originates or modifies a number.
A REJECT is an honest success.  Pure stdlib; no pandas/pyarrow.

Five checks:
  1. DEDUP           — token-Jaccard vs existing notes >= threshold => SHARPEN.
  2. LEAK-FLAG HONESTY — claims leak_safe but has leak markers => flag False.
  3. VERDICT CALIBRATION — predicted vs actual verdict mismatch => NON-BLOCKING.
  4. CITATION COVERAGE — numeric claims must carry provenance chip >= min_citation.
  5. EDGE-CLAIM DETECTION — ROI / beats the market / profitable / guaranteed => HARD FAIL.

passes = (not is_duplicate) and leak_flag_honest and (not edge_claim_detected)
         and (citation_coverage >= min_citation).  verdict_calibrated is NON-BLOCKING.

CLI: python -m scripts.platformkit.brain_critic <findings.jsonl> [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants (explicit, tunable, tested)
# ---------------------------------------------------------------------------

_LEAK_MARKERS: tuple = (
    "in-season", "in_season", "inseason", "season-final", "season_final",
    "post-hoc", "post_hoc", "posthoc", "future", "lookahead", "look-ahead",
    "look_ahead", "same-day-outcome", "same_day_outcome", "same day outcome",
    "forward-looking", "forward_looking",
)

_EDGE_CLAIM_PATTERNS: tuple = (
    re.compile(r"\broi\b", re.IGNORECASE),
    re.compile(r"beats?\s+the\s+market", re.IGNORECASE),
    re.compile(r"\+\s*\d+(?:\.\d+)?\s*%\s*edge", re.IGNORECASE),
    re.compile(r"\bprofitable\b", re.IGNORECASE),
    re.compile(r"\bguaranteed\b", re.IGNORECASE),
    re.compile(r"\bproven\s+edge\b", re.IGNORECASE),
)

_PROVENANCE_PATTERNS: tuple = (
    re.compile(r"[A-Za-z0-9_\-/\\]+\.(py|parquet|json|jsonl|md|csv|pkl)\b", re.IGNORECASE),
    re.compile(r"as[_\-\s]of\s*[\d\-/]+", re.IGNORECASE),
    re.compile(r"artifact[:\s]", re.IGNORECASE),
    re.compile(r"\[\[[\w\-_ ]+\]\]"),
    re.compile(r"scripts?/[\w/\-]+", re.IGNORECASE),
    re.compile(r"data/[\w/\-]+", re.IGNORECASE),
    re.compile(r"\bgate[:\s]", re.IGNORECASE),
)

_NUMERIC_CLAIM_RE: re.Pattern = re.compile(
    r"\b\d+(?:\.\d+)?\s*%|\b\d{2,}(?:\.\d+)?\b|MAE|RMSE|Brier|ATS|CLV|ROI|n=\d+",
    re.IGNORECASE,
)

_DEFAULT_DEDUP_THRESHOLD: float = 0.6
_DEFAULT_MIN_CITATION: float = 0.95


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Critique:
    passes: bool; is_duplicate: bool; leak_flag_honest: bool
    verdict_calibrated: bool  # NON-BLOCKING — does not gate passes
    citation_coverage: float; edge_claim_detected: bool
    reasons: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))

def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b: return 0.0
    return len(a & b) / len(a | b)

def _extract_claim_text(f: Dict) -> str:
    for k in ("claim", "text"):
        v = f.get(k)
        if isinstance(v, str) and v.strip(): return v.strip()
    return ""

def _extract_full_text(f: Dict) -> str:
    parts: List[str] = []
    for k in ("claim", "text", "construction", "rationale", "why", "provenance", "citations"):
        v = f.get(k)
        if isinstance(v, str): parts.append(v)
        elif isinstance(v, list): parts.extend(str(x) for x in v)
    return " ".join(parts)

def _is_leak_safe(f: Dict) -> bool:
    for k in ("leak_safe", "leak_flag"):
        v = f.get(k)
        if v is True: return True
        if isinstance(v, str) and v.lower() in ("safe", "true", "yes"): return True
    return False


def _has_leak_markers(text: str) -> bool:
    lower = text.lower()
    return any(m in lower for m in _LEAK_MARKERS)

def _citation_coverage(f: Dict) -> float:
    """Fraction of numeric claim spans with a provenance chip within ±150 chars."""
    full_text = _extract_full_text(f)
    citation_blob = " ".join(
        (f.get(k) if isinstance(f.get(k), str) else " ".join(str(x) for x in (f.get(k) or [])))
        for k in ("citations", "provenance")
    )
    spans = list(_NUMERIC_CLAIM_RE.finditer(full_text))
    if not spans:
        return 1.0
    covered = sum(
        1 for m in spans
        if any(p.search(full_text[max(0, m.start()-150):m.end()+150] + " " + citation_blob)
               for p in _PROVENANCE_PATTERNS)
    )
    return covered / len(spans)


def _detect_edge_claims(text: str) -> bool: return any(p.search(text) for p in _EDGE_CLAIM_PATTERNS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def critique_finding(
    finding: Dict,
    existing: Optional[List[Dict]] = None,
    *,
    dedup_threshold: float = _DEFAULT_DEDUP_THRESHOLD,
    min_citation: float = _DEFAULT_MIN_CITATION,
) -> Critique:
    """Adversarially audit *finding* before it is written to the brain.

    All keys in *finding* are optional; missing keys degrade gracefully.
    passes = (not is_duplicate) and leak_flag_honest and (not edge_claim_detected)
             and (citation_coverage >= min_citation).
    verdict_calibrated is reported but NON-BLOCKING (a miscalibrated proposer prior
    is a signal to recalibrate, not a gate).
    """
    reasons: List[str] = []
    claim_text = _extract_claim_text(finding)
    full_text = _extract_full_text(finding)

    # 1. DEDUP
    is_duplicate = False
    if existing and claim_text:
        toks = _tokenize(claim_text)
        for ex in existing:
            ex_text = _extract_claim_text(ex)
            if ex_text and _jaccard(toks, _tokenize(ex_text)) >= dedup_threshold:
                is_duplicate = True
                reasons.append(
                    f"DEDUP: Jaccard >= {dedup_threshold} vs existing note "
                    f"'{ex_text[:60]}...' => SHARPEN the existing note, do not duplicate."
                )
                break

    # 2. LEAK-FLAG HONESTY
    leak_flag_honest = True
    if _is_leak_safe(finding):
        scan_text = (finding.get("construction") or "") + " " + full_text
        if _has_leak_markers(scan_text):
            leak_flag_honest = False
            reasons.append(
                "LEAK-FLAG: claims leak_safe=True but construction/text contains leakage "
                "marker(s). Mark leak_safe=False or remove the in-season/lookahead reference."
            )

    # 3. VERDICT CALIBRATION (non-blocking)
    predicted = finding.get("predicted_verdict")
    actual = finding.get("actual_verdict")
    verdict_calibrated = True
    if predicted is not None and actual is not None:
        if str(predicted).upper().strip() != str(actual).upper().strip():
            verdict_calibrated = False
            reasons.append(
                f"VERDICT: predicted={predicted!r} != actual={actual!r} — proposer prior "
                f"MISCALIBRATED (non-blocking; update LLM prior for this hypothesis family)."
            )

    # 4. CITATION COVERAGE
    cov = _citation_coverage(finding)
    citation_ok = cov >= min_citation
    if not citation_ok:
        reasons.append(
            f"CITATION: {cov:.1%} of numeric claims carry provenance chips "
            f"(threshold={min_citation:.0%}). Add file:line, artifact ref, or as-of tag."
        )

    # 5. EDGE-CLAIM DETECTION (hard fail)
    edge_claim_detected = _detect_edge_claims(full_text)
    if edge_claim_detected:
        reasons.append(
            "EDGE-CLAIM: forbidden assertion detected (ROI / beats the market / profitable / "
            "guaranteed / proven edge). No edge claimed without real forward CLV. HARD FAIL."
        )

    passes = (
        not is_duplicate
        and leak_flag_honest
        and not edge_claim_detected
        and citation_ok
    )
    return Critique(
        passes=passes,
        is_duplicate=is_duplicate,
        leak_flag_honest=leak_flag_honest,
        verdict_calibrated=verdict_calibrated,
        citation_coverage=cov,
        edge_claim_detected=edge_claim_detected,
        reasons=reasons,
    )


def critique_batch(findings: List[Dict]) -> List[Critique]:
    """Critique each finding vs all others in the batch (cross-batch dedup)."""
    return [critique_finding(f, [o for j, o in enumerate(findings) if j != i])
            for i, f in enumerate(findings)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="brain_critic — adversarial memory-write check.")
    p.add_argument("findings_jsonl", help="Path to a JSONL file of findings dicts.")
    p.add_argument("--json", action="store_true", default=False)
    p.add_argument("--dedup-threshold", type=float, default=_DEFAULT_DEDUP_THRESHOLD)
    p.add_argument("--min-citation", type=float, default=_DEFAULT_MIN_CITATION)
    args = p.parse_args(argv)

    path = Path(args.findings_jsonl)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    findings: List[Dict] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"ERROR: line {lineno}: {exc}", file=sys.stderr)
                return 2

    if not findings:
        print("No findings to critique.")
        return 0

    critiques = critique_batch(findings)

    if args.json:
        print(json.dumps([
            {"index": i, "claim": _extract_claim_text(f), "passes": c.passes,
             "is_duplicate": c.is_duplicate, "leak_flag_honest": c.leak_flag_honest,
             "verdict_calibrated": c.verdict_calibrated,
             "citation_coverage": round(c.citation_coverage, 4),
             "edge_claim_detected": c.edge_claim_detected, "reasons": c.reasons}
            for i, (f, c) in enumerate(zip(findings, critiques))
        ], indent=2))
    else:
        n_pass = sum(1 for c in critiques if c.passes)
        print(f"\nbrain_critic: {len(findings)} finding(s) — {n_pass} PASS, "
              f"{len(critiques) - n_pass} FAIL\n")
        for i, (f, c) in enumerate(zip(findings, critiques)):
            preview = _extract_claim_text(f)[:60] or f"(finding {i})"
            print(f"  [{'PASS' if c.passes else 'FAIL'}] #{i}: {preview}")
            for r in c.reasons:
                print(f"         * {r}")
        print()

    return 0 if all(c.passes for c in critiques) else 1


if __name__ == "__main__":
    sys.exit(_main())
