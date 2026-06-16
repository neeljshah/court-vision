"""test_no_leak_paths_staged.py -- pre-push guard against re-leaking local-only data.

The repo's binding invariant is that ``data/``, ``vault/``, ``.planning/``, secrets
(``.env``), and any betting-ledger path (bets/bankroll/CLV/PnL/odds-lines) stay LOCAL
and are NEVER tracked/pushed to the public origin. Betting ledgers + the whole data/
tree were once tracked on public ``origin/master`` (see docs/SECURITY_REMEDIATION.md,
local); after the 2026-06-15 scrub only a short audited non-betting whitelist under
data/ remains tracked.

This test fails if any *staged* (index) path matches a forbidden pattern, so a careless
``git add`` cannot re-introduce the leak. It is a guard, not a coverage test: with a
clean index it is a no-op (the common case in CI).

Run standalone (never the full suite -- it freezes the box):
    python -m pytest tests/platform/test_no_leak_paths_staged.py -q
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# Always-forbidden: env secrets and the internal planning tree.
_SECRET = re.compile(r"(^|/)\.env($|\.)|(^|/)\.planning/")

# Betting-DATA tokens. Source CODE (src/scripts/api/tests/apps/domains/kernel) that
# merely has 'bankroll'/'clv'/'ledger' in its name is PUBLIC -- only DATA files
# (csv/json/parquet/db/jsonl) carrying betting records are forbidden. So a loose
# betting token only counts as a leak when the file has a data extension.
_BETTING_TOKEN = re.compile(
    r"(^|/)(bets/|bankroll|clv[_/]|pnl_ledger|bet_log|live_bets/|historical_lines/|lines/)",
    re.IGNORECASE,
)
_DATA_EXT = re.compile(r"\.(csv|json|jsonl|parquet|db|sqlite3?)$", re.IGNORECASE)

# Any staged vault/ path is forbidden (vault is local working memory, fully ignored).
_VAULT = re.compile(r"^vault/")

# Staged data/ paths are forbidden UNLESS they match the audited whitelist.
_DATA = re.compile(r"^data/")
_DATA_WHITELIST = re.compile(
    r"^data/(README\.md|__init__\.py|jersey_name_map\.json|team_colors\.json"
    r"|models/(\.gitkeep|model_registry\.json|.*_metrics\.json|hyperparams_.*\.json"
    r"|prop_corr_matrix\.json|props_stl_v2_metrics\.json|matchup_model_meta\.json"
    r"|dnp_model_meta\.json|probe_defender_feature\.json|load_management\.json)"
    r"|nba/(team_stats_.*\.json|player_avgs_.*\.json))$"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _staged_paths() -> list[str]:
    """Names of files currently staged in the index (added/modified), or []."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=AM"],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pytest.skip("git not available")
    if out.returncode != 0:
        pytest.skip("not a git work tree")
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def _is_leak(path: str) -> bool:
    if _SECRET.search(path):
        return True
    if _VAULT.search(path):
        return True
    if _DATA.search(path):
        return not _DATA_WHITELIST.match(path)
    # Betting DATA outside data/ (e.g. a root bankroll.json) -- only data-extension files.
    return bool(_BETTING_TOKEN.search(path) and _DATA_EXT.search(path))


def test_no_forbidden_paths_staged():
    """No local-only / betting / secret path may be staged for commit."""
    offenders = [p for p in _staged_paths() if _is_leak(p)]
    assert not offenders, (
        "Forbidden local-only/betting/secret paths are STAGED -- unstage them before "
        "committing (they must never reach the public origin):\n  "
        + "\n  ".join(offenders)
    )


def test_guard_classifier_matches_known_cases():
    """Lock the classifier so the guard cannot silently weaken."""
    leaks = [
        "data/bets/strategy_d_2026-05-27.csv",
        "data/cache/bankroll_state.json",
        "data/cache/clv_running_total.json",
        "data/cache/live_bets/x.json",
        "data/external/historical_lines/nba_2024-2025.csv",
        "data/lines/2026-05-26_pin.csv",
        "vault/Reports/backtest_2026-05-27.md",
        ".env",
        ".env.production",
        ".planning/platform/x.md",
        "data/pnl_ledger.csv",
        "bankroll.json",
    ]
    allowed = [
        "data/models/win_prob_metrics.json",
        "data/models/hyperparams_pts.json",
        "data/nba/team_stats_2024-25.json",
        "data/jersey_name_map.json",
        "data/team_colors.json",
        "domains/basketball_nba/predictor.py",
        "scripts/platformkit/cohesive_read.py",
        "docs/PREDICTOR_PLATFORM.md",
        "src/betting/pnl_ledger.py",  # source CODE is public; only DATA ledgers are forbidden
    ]
    for p in leaks:
        assert _is_leak(p), f"should be flagged as a leak: {p}"
    for p in allowed:
        assert not _is_leak(p), f"should be allowed: {p}"
