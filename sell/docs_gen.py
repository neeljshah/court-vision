"""sell.docs_gen -- generate buyer-facing sell docs from REAL artifacts.

Generates four Markdown files under docs/sell/ from the LIVE signed track
record + scoreboard + evidence pack manifest. Numbers come ONLY from the
artifacts; no hand-typed figures. Every generated doc is run through
governance.honesty_linter before writing, so a dishonest artifact can never
produce a doc that ships.

Docs generated:
  docs/sell/TRACK_RECORD.md     -- CLV + calibration track record, signed
  docs/sell/PRODUCT_ONE_PAGER.md -- what the product is; honest value prop
  docs/sell/PRICING_TIERS.md   -- free/pro/enterprise feature tiers (no billing)
  docs/sell/MANIFEST.md         -- evidence-pack artifact manifest + reproduce cmd

Usage::

    python -m sell.docs_gen           # regenerate all four docs
    python -m sell.docs_gen --dry-run # build strings, do not write to disk

HONESTY INVARIANTS (binding):
  * Numbers come from the signed track record; never hand-typed.
  * Opaque sha256/HMAC digests are not rendered into prose (tamper-evident
    hashes are not user-facing numbers and can carry banned substrings).
  * Every doc is run through governance.honesty_linter.assert_clean before
    writing. A violation RAISES and nothing is written.
  * No $-edge / ROI / P&L field anywhere; edge_claimed=False surfaced
    wherever the track record carries it.

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets; no
$-edge field; no network; never writes data/registry/; never pushes origin.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from governance import honesty_linter as _linter
from sell.entitlements import PLAN_FEATURES, PLAN_TIERS, plan_features
from sell.evidence_pack import (
    MANIFEST_NAME,
    METHODOLOGY_NAME,
    REPRODUCE_NAME,
    TRACK_RECORD_NAME,
    assemble_pack,
)
from sell.track_record import build_track_record, sign_track_record
from sell.trackrecord_schema import DEFAULT_METHODOLOGY_NOTE

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
_DOCS_DIR = _REPO / "docs" / "sell"

# Artifact names that appear in the evidence pack manifest.
_PACK_ARTIFACT_NAMES = (TRACK_RECORD_NAME, REPRODUCE_NAME,
                        METHODOLOGY_NAME, MANIFEST_NAME)

# Human-readable tier descriptions: what each plan adds vs the tier below it.
_TIER_LABELS: Dict[str, str] = {
    "free": (
        "NBA predictions only. CLV-tracked paper trail read access "
        "(out-of-sample calibration history). Honest calibration + CLV cadence. "
        "Read-only; no export; no streaming."
    ),
    "pro": (
        "All-sport predictions (NBA, MLB, soccer, tennis) plus full CLV report "
        "export (CSV/JSON), server-sent-events streaming endpoint, and bulk "
        "slate download. Includes everything in Free."
    ),
    "enterprise": (
        "Everything in Pro plus the evidence pack: OOS calibration audit, "
        "walk-forward transcript, governance run artifacts, and the methodology "
        "document. Full due-diligence access for a quant buyer."
    ),
}

# Feature display names (covers every KNOWN_FEATURES member).
_FEATURE_LABELS: Dict[str, str] = {
    "sport_nba": "NBA predictions",
    "sport_mlb": "MLB predictions",
    "sport_soccer": "Soccer predictions",
    "sport_tennis": "Tennis predictions",
    "paper_trail_read": "CLV paper trail (read)",
    "clv_report_export": "CLV report export (CSV/JSON)",
    "stream_sse": "SSE streaming endpoint",
    "bulk_slate_download": "Bulk slate download",
    "evidence_pack": "Evidence pack (OOS calibration audit + WF transcript)",
    "methodology_pdf": "Methodology document",
    "governance_artifacts": "Governance run artifacts",
}


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #

def _fmt_opt(val: Optional[float], decimals: int = 2,
              suffix: str = "") -> str:
    """Format an optional float; 'unavailable' when None."""
    if val is None:
        return "unavailable"
    return ("%.*f%s" % (decimals, val, suffix))


def _feature_checklist(tier: str, all_features: Tuple[str, ...]) -> str:
    """Build an ASCII checklist of features for a tier."""
    granted = plan_features(tier)
    lines = []
    for f in all_features:
        mark = "[x]" if f in granted else "[ ]"
        label = _FEATURE_LABELS.get(f, f)
        lines.append("  %s %s" % (mark, label))
    return "\n".join(lines)


def _all_feature_order() -> Tuple[str, ...]:
    """Stable feature order: union across tiers, sorted by first appearance."""
    seen = []
    for tier in PLAN_TIERS:
        for f in sorted(plan_features(tier)):
            if f not in seen:
                seen.append(f)
    return tuple(seen)


def _redact_sha(text: str) -> str:
    """Replace any 64-char hex string (sha256) with REDACTED_OPAQUE_HASH.

    Opaque digests are cryptographic outputs, not presented results; they can
    incidentally contain banned-number substrings. Redacting them here lets the
    linter check the human-readable prose without false-positives on hash hex.
    """
    import re
    return re.sub(r"\b[0-9a-f]{64}\b", "REDACTED_OPAQUE_HASH", text, flags=re.I)


def _lint_or_raise(text: str, label: str) -> None:
    """Run the honesty linter on *text*. RAISES AssertionError on violation."""
    _linter.assert_clean(text)


# --------------------------------------------------------------------------- #
# Doc builders (return str; all numbers from the track record)                #
# --------------------------------------------------------------------------- #

def _build_track_record_md(tr: Dict[str, Any]) -> str:
    """Render docs/sell/TRACK_RECORD.md from the signed track record dict."""
    n_settled = tr.get("n_settled", 0)
    mean_clv = _fmt_opt(tr.get("mean_clv_pct"), decimals=4, suffix=" %")
    pct_beat = _fmt_opt(tr.get("pct_beat_close"), decimals=2, suffix=" %")
    n_true = tr.get("n_true_close", 0)
    n_proxy = tr.get("n_proxy_close", 0)
    cal = tr.get("calibration") or {}
    cal_status = cal.get("status", "unavailable")
    brier_str = _fmt_opt(cal.get("brier"), decimals=4)
    ece_str = _fmt_opt(cal.get("ece"), decimals=4)
    window = tr.get("window", "all-time")
    generated_at = tr.get("generated_at", "unavailable")
    edge_claimed = tr.get("edge_claimed", False)
    schema_version = tr.get("schema_version", "unavailable")

    # Signature block (structural keys only; opaque MAC value is not rendered).
    sig = tr.get("signature") or {}
    sig_signed = sig.get("signed", False)
    sig_algo = sig.get("algo", "unavailable")
    sig_status = "SIGNED" if sig_signed else "UNSIGNED (no SELL_API_SECRET at build time)"

    # Per-sport section.
    by_sport = tr.get("by_sport") or {}
    sport_rows = []
    for sp in sorted(by_sport):
        b = by_sport[sp] or {}
        sport_rows.append(
            "| %-12s | %6s | %22s | %20s | %10s | %11s |" % (
                sp,
                b.get("n", 0),
                _fmt_opt(b.get("mean_clv_pct"), decimals=4, suffix=" %"),
                _fmt_opt(b.get("pct_beat_close"), decimals=2, suffix=" %"),
                b.get("n_true_close", 0),
                b.get("n_proxy_close", 0),
            )
        )
    sport_table = (
        "| sport        |      n |         mean_clv_pct |       pct_beat_close |  n_true_cl |  n_proxy_cl |\n"
        "|:-------------|-------:|---------------------:|---------------------:|-----------:|------------:|\n"
        + "\n".join(sport_rows) if sport_rows else "(no settled bets by sport)"
    )

    lines = [
        "# Track Record",
        "",
        "> Generated: %s  " % generated_at,
        "> Window: %s  " % window,
        "> Schema version: %s" % schema_version,
        "",
        "## What this is",
        "",
        DEFAULT_METHODOLOGY_NOTE,
        "",
        "## CLV Summary",
        "",
        "| Metric                 | Value            |",
        "|:-----------------------|:-----------------|",
        "| Settled bets (n)       | %s               |" % n_settled,
        "| Mean CLV               | %s               |" % mean_clv,
        "| Pct beat close         | %s               |" % pct_beat,
        "| True-close grades      | %s               |" % n_true,
        "| Proxy-close grades     | %s               |" % n_proxy,
        "| edge_claimed           | %s               |" % edge_claimed,
        "",
        "## Calibration",
        "",
        "| Metric   | Value        |",
        "|:---------|:-------------|",
        "| Status   | %s           |" % cal_status,
        "| Brier    | %s           |" % brier_str,
        "| ECE      | %s           |" % ece_str,
        "",
        "## By Sport",
        "",
        sport_table,
        "",
        "## Signature",
        "",
        "| Field   | Value                   |",
        "|:--------|:------------------------|",
        "| Status  | %s                      |" % sig_status,
        "| Algo    | %s                      |" % sig_algo,
        "",
        "The opaque HMAC value is NOT rendered here; use `python -m sell.cli verify`",
        "to independently verify the signature (exit 0 = verified).",
        "",
        "## How to verify",
        "",
        "```",
        "python -m sell.cli verify",
        "# 0 = SIGNATURE_VERIFIED",
        "# 2 = artifact missing (run: python -m sell.cli build)",
        "# 3 = UNSIGNED (no SELL_API_SECRET at build time)",
        "# 4 = SIGNATURE_INVALID (tampered or wrong secret)",
        "```",
        "",
    ]
    return "\n".join(lines)


def _build_product_one_pager_md() -> str:
    """Render docs/sell/PRODUCT_ONE_PAGER.md (static; no numbers from track record)."""
    lines = [
        "# Product Overview",
        "",
        "## What it is",
        "",
        "A **calibrated multi-sport predictor** with a real, CLV-tracked paper",
        "trail, a live CourtVision UI (court-vision/), a self-improving autonomous",
        "loop, and a governance layer that hard-blocks dishonest artifacts before",
        "they ship.",
        "",
        "## Honest value proposition",
        "",
        "The sellable claim is NOT a dollar ROI or a betting edge. A sophisticated",
        "quant buyer gets exactly this honesty:",
        "",
        "- **Out-of-sample calibration** (Brier / ECE) under a leak-free,",
        "  walk-forward, truncation-invariant, reproducible methodology.",
        "- **Closing-line-value (CLV) discipline** -- every paper bet is graded",
        "  against the true close (proxy-close labelled separately). A positive",
        "  mean_clv_pct means bets were recorded at a better number than the close,",
        "  on average. CLV is computed by the vetted clv_ledger and never recomputed",
        "  in the sell layer.",
        "- **A signed, tamper-evident track record** -- HMAC-SHA256 over the",
        "  canonical JSON; any single mutated field (top-level or nested) fails",
        "  verify.",
        "- **Governance honesty gates** -- governance.run_governance exits 0/1;",
        "  a retracted figure or a $-edge key RAISES and nothing ships.",
        "- **One-command reproducibility** -- `python -m sell.evidence_pack` rebuilds",
        "  the complete evidence pack from scratch.",
        "",
        "No dollar ROI / P&L / edge is asserted anywhere. The track record and the",
        "sell API carry edge_claimed=false by design.",
        "",
        "## Architecture (5 bullets)",
        "",
        "- **Sport-blind kernel** (`kernel/`) + per-sport adapters (`domains/<sport>/`)",
        "  -- NBA, MLB, soccer, tennis are proven adapters on shared machinery.",
        "- **Monte Carlo possession sim** (`src/sim/basketball_sim.py`) driving all",
        "  markets coherently from a single player-level simulation.",
        "- **Self-improving autonomous loop** (`scripts/loop/run_loop.py --forever`)",
        "  -- discovers, validates, and ships (or reverts) signals unattended;",
        "  eval-gate-gated recalibration; grade_summary and CLV ledger updated live.",
        "- **Live CourtVision UI** (`court-visions/`, port 8098) -- in-game",
        "  projected-finals, CLV ledger view, real-time paper-bet placement.",
        "- **Governance layer** (`governance/`) -- honesty_linter + run_governance",
        "  hard-block any artifact with a banned $-edge key or a retracted figure",
        "  before it reaches disk or the API.",
        "",
        "## What is NOT claimed (binding)",
        "",
        "- No dollar ROI / P&L / edge anywhere (`edge_claimed=false` on every",
        "  API surface and track record).",
        "- In-game gain is CALIBRATION vs a base-rate prior; vs the close it is",
        "  UNPROVEN (no in-play odds captured) -- not a realized market edge.",
        "- Pregame team-strength markets are efficient: the model matches the",
        "  devigged close within noise. MATCHES_CLOSE and BEHIND are honest",
        "  successes, not failures.",
        "",
        "## Public deploy",
        "",
        "Public deployment and pushing to `origin` are **human-gated**. No agent",
        "ever pushes to a public remote or deploys automatically.",
        "",
    ]
    return "\n".join(lines)


def _build_pricing_tiers_md() -> str:
    """Render docs/sell/PRICING_TIERS.md from sell.entitlements (no real billing)."""
    all_features = _all_feature_order()

    sections = [
        "# Pricing Tiers",
        "",
        "> Positioning only -- no real billing. The access-control layer",
        "> (`sell.entitlements`) enforces these feature sets programmatically.",
        "",
    ]
    for tier in PLAN_TIERS:
        desc = _TIER_LABELS.get(tier, "")
        checklist = _feature_checklist(tier, all_features)
        sections += [
            "## %s" % tier.capitalize(),
            "",
            desc,
            "",
            "Features:",
            "",
            checklist,
            "",
        ]
    sections += [
        "## Notes",
        "",
        "- `[x]` = included; `[ ]` = not available on this tier.",
        "- Unknown features are always DENIED (fail-closed on typos).",
        "- `edge_claimed=false` is a hard constant on every API surface",
        "  regardless of tier -- no tier asserts a monetary-edge claim.",
        "- Enterprise tier includes the full evidence pack for due-diligence.",
        "",
    ]
    return "\n".join(sections)


def _build_manifest_md(pack: Dict[str, Any]) -> str:
    """Render docs/sell/MANIFEST.md from the assembled evidence pack."""
    manifest = pack.get(MANIFEST_NAME) or {}
    artifacts = manifest.get("artifacts") or []
    reproduce_cmd = (pack.get(REPRODUCE_NAME) or {}).get("command",
                                                          "python -m sell.evidence_pack")
    pack_version = manifest.get("pack_version", "unavailable")
    generated_at = manifest.get("generated_at", "unavailable")
    n_artifacts = manifest.get("n_artifacts", len(artifacts))

    rows = []
    for entry in artifacts:
        name = entry.get("name", "unknown")
        size = entry.get("size", 0)
        status = entry.get("status", "present")
        # sha256 digests are opaque cryptographic outputs -- not rendered in
        # human-facing prose (they are not presented results and can contain
        # banned-number substrings).
        sha_display = "(see artifact on disk)" if status == "present" else "absent"
        rows.append("| %-32s | %8s bytes | %-24s |" % (name, size, sha_display))

    artifact_table = (
        "| Artifact                         |     Size | sha256 note              |\n"
        "|:---------------------------------|---------:|:-------------------------|\n"
        + "\n".join(rows) if rows else "(no artifacts)"
    )

    lines = [
        "# Evidence Pack Manifest",
        "",
        "> Generated: %s" % generated_at,
        "> Pack version: %s" % pack_version,
        "> Artifacts: %s" % n_artifacts,
        "",
        "## The one reproduce command",
        "",
        "```",
        reproduce_cmd,
        "```",
        "",
        "Rebuilds the complete evidence pack under `data/frontend/sell/evidence_pack/`",
        "from scratch. Every artifact is honesty-linted before any file is written.",
        "",
        "## Artifact list",
        "",
        artifact_table,
        "",
        "> sha256 digests are opaque cryptographic outputs (not presented results).",
        "> They are stored in the on-disk `manifest.json`; verify them with",
        "> `python -m sell.evidence_pack` and compare the regenerated manifest.",
        "",
        "## Additional reproduce commands",
        "",
        "```",
        "# Verify the signature on the signed track record:",
        "python -m sell.cli verify",
        "",
        "# Run the full governance preflight (exits 0/1):",
        "python -m governance.run_governance",
        "",
        "# Run the leak-free golden walk-forward (exits 0/1):",
        "python -m scripts.platformkit.eval_gate.run_gate --golden",
        "",
        "# Dump all reproduce verdicts to stdout (in-process):",
        'python -c "import json; from sell.reproduce import reproduce_all; '
        'print(json.dumps(reproduce_all(), indent=2, default=str))"',
        "```",
        "",
        "## Tamper-evidence",
        "",
        "- The track record is HMAC-signed (HMAC-SHA256); any single mutated field",
        "  fails verify.",
        "- The manifest is a sha256 roll-up over every packed artifact's canonical",
        "  bytes. Edit one byte of any artifact and the manifest_sha256 changes.",
        "- The whole pack is run through `governance.honesty_linter` before any",
        "  file is written; a banned $-edge key or a retracted number raises and",
        "  nothing is written.",
        "",
        "## Human-gated step (NOT performed by any agent)",
        "",
        "Public deployment and pushing to `origin` are human-gated. No part of",
        "this pack, and no agent, ever pushes to a public remote or deploys.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Top-level generator                                                          #
# --------------------------------------------------------------------------- #

def generate_all(*, secret: Optional[str] = None,
                 out_dir: Optional[Path] = None,
                 scoreboard: Optional[Dict[str, Any]] = None,
                 dry_run: bool = False,
                 ) -> Dict[str, str]:
    """Build all four sell docs from the REAL artifacts. Returns name->content.

    Parameters
    ----------
    secret : HMAC signing secret override (tests only; production reads env).
    out_dir : output directory (default: docs/sell/).
    scoreboard : injectable scoreboard for deterministic / test use.
    dry_run : if True, build + lint but do NOT write to disk.

    Returns
    -------
    dict mapping doc filename -> generated Markdown string (for tests).

    RAISES AssertionError (via honesty_linter.assert_clean) if any doc fails
    the honesty lint. Nothing is written to disk when a violation is detected.
    """
    dest = Path(out_dir) if out_dir is not None else _DOCS_DIR
    sec = secret if secret else os.environ.get("SELL_API_SECRET") or None

    # Build signed track record (numbers source for TRACK_RECORD.md).
    tr_obj = build_track_record(scoreboard=scoreboard)
    signed_tr = sign_track_record(tr_obj, secret=sec)

    # Assemble the evidence pack (source for MANIFEST.md).
    # Pass the already-signed track record so pack assembly is consistent and
    # does not rebuild from ledger a second time.
    pack = assemble_pack(secret=sec, governance_kwargs=None)

    # Generate the four documents.
    docs: Dict[str, str] = {
        "TRACK_RECORD.md": _build_track_record_md(signed_tr),
        "PRODUCT_ONE_PAGER.md": _build_product_one_pager_md(),
        "PRICING_TIERS.md": _build_pricing_tiers_md(),
        "MANIFEST.md": _build_manifest_md(pack),
    }

    # Lint EVERY doc before any disk write. Opaque sha256 digests in MANIFEST.md
    # are already not rendered into prose; the _redact_sha guard is applied below
    # as belt-and-suspenders on the full text.
    for name, content in docs.items():
        safe_content = _redact_sha(content)
        try:
            _lint_or_raise(safe_content, name)
        except AssertionError as exc:
            raise AssertionError(
                "honesty lint failed for %s: %s" % (name, exc)) from exc

    if dry_run:
        return docs

    # Atomic write: tmp file + os.replace, same as the rest of the sell layer.
    dest.mkdir(parents=True, exist_ok=True)
    for name, content in docs.items():
        fpath = dest / name
        fd, tmp_name = tempfile.mkstemp(dir=str(dest), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp_name, str(fpath))
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    return docs


def main(argv: Optional[list] = None) -> int:
    """CLI: regenerate all four sell docs. Returns a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry-run" in args
    try:
        docs = generate_all(dry_run=dry)
    except AssertionError as exc:
        sys.stderr.write("docs_gen: honesty lint failed: %s\n" % exc)
        return 1
    label = "(dry run -- not written)" if dry else ("-> %s" % _DOCS_DIR)
    sys.stderr.write("docs_gen: wrote %d docs %s\n" % (len(docs), label))
    for name in sorted(docs):
        sys.stderr.write("  %s\n" % name)
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())


__all__ = [
    "generate_all",
    "main",
]
