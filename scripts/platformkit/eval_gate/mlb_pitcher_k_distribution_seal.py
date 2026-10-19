"""S450 FIX 1e/1f: sealed-preregistration validation + launch-ledger gate
(AMENDMENT 5(a), tightened by AMENDMENT 6(c)/(d)).

Split out of mlb_pitcher_k_distribution_realrun.py under the 300 LOC rail (a
7th helper module -- AMENDMENT 6(a)'s per-row cpcv scoring already used the
flagged 6th slot; every file still <= 300 lines is the binding rail, not the
module count).

Seal convention reused from scripts/platformkit/execution/ingame_scoreboard.py's
``_seal``: a content hash (the prereg's own trailing ``SHA: <hex>`` line ==
sha256 of the LF-normalised bytes before it) PLUS a git-tracked check (on-disk
bytes == what is committed at HEAD, LF-normalised). AMENDMENT 6(d) adds: the
seal also binds a machine-parseable scoring-parameter block, and the real-run
CLI refuses any runtime value that differs from it. AMENDMENT 6(c) adds: the
launch K is READ from the family ledger (next_k_family), never hard-coded.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple


def file_identity(path: Path) -> dict:
    """A9 for TEXT files: path, byte size, sha256 of the LF-normalised bytes.
    Moved here from mlb_pitcher_k_distribution.py under AMENDMENT 14(d) to
    keep that CLI module under the 300 LOC rail."""
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    return {"path": str(path.resolve()), "bytes": len(raw),
            "sha256_lf_normalized": hashlib.sha256(normalized).hexdigest()}


def raw_file_identity(path: Path) -> dict:
    """A9 for BINARY files (the gamelogs parquet): sha256 of the UNCHANGED
    bytes, never LF-normalised (AMENDMENT 6(e): that would alter identity)."""
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_arms import BETA_GRID, R_GRID

SHA_TRAILER = "SHA: "
LAUNCH_FAMILY = "s450_mlb_pitcher_k"
PARAMS_BEGIN = "<!-- SEALED_PARAMS"
PARAMS_END = "SEALED_PARAMS -->"
SEALED_PARAM_KEYS = ("seed", "draws", "fit_start", "fit_end", "holdout_a_start",
                    "holdout_b_start", "holdout_b_end", "r_grid", "beta_grid",
                    "cluster_unit", "abstention_policy", "null_decision_rule")

# AMENDMENT 7(d): the canonical runtime constants/policies every sealed param
# is checked against -- grids are DERIVED from the real fitting grids
# (mlb_pitcher_k_distribution_arms), never copied from the prereg text, so a
# drifted prereg is actually caught rather than trivially matching itself.
CANONICAL_CLUSTER_UNIT = "game_date"
CANONICAL_ABSTENTION_POLICY = "common_all_or_nothing"
CANONICAL_NULL_DECISION_RULE = "real_paired_delta_must_beat_same_holdout_null_paired_delta"


def _fmt_grid(grid: Tuple[float, ...]) -> str:
    """"4,6,8" style formatting: whole-number floats drop their ".0"."""
    parts = []
    for val in grid:
        text = f"{val:g}"
        parts.append(text)
    return ",".join(parts)


def _git_show_head(repo_root: Path, relative_posix: str) -> Optional[bytes]:
    """Real `git show HEAD:<path>`; None if not tracked or git fails."""
    result = subprocess.run(["git", "-C", str(repo_root), "show", f"HEAD:{relative_posix}"],
                            capture_output=True)
    return None if result.returncode != 0 else result.stdout


def _git_rev_parse_head(repo_root: Path) -> Optional[str]:
    """Real `git rev-parse HEAD`; None if git fails. Injectable (see
    ``validate_prereg_seal``'s ``git_rev_parse`` param) so a construct test can
    simulate a resolved commit without a real commit."""
    result = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                            capture_output=True)
    if result.returncode != 0:
        return None
    return result.stdout.decode("ascii", errors="replace").strip()


def parse_sealed_params(body: bytes) -> Optional[Dict[str, str]]:
    """The sealed scoring parameters, parsed from a
    ``<!-- SEALED_PARAMS ... SEALED_PARAMS -->`` block inside the ALREADY
    seal-validated prereg body. None if the block is absent or incomplete."""
    text = body.decode("ascii", errors="replace")
    start, end = text.find(PARAMS_BEGIN), text.find(PARAMS_END)
    if start == -1 or end == -1 or end < start:
        return None
    params: Dict[str, str] = {}
    for line in text[start + len(PARAMS_BEGIN):end].splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        params[key.strip()] = value.strip()
    if not set(SEALED_PARAM_KEYS).issubset(params):
        return None
    return params


def validate_prereg_seal(prereg_path: Path, *, repo_root: Optional[Path] = None,
                         git_show: Callable = _git_show_head,
                         git_rev_parse: Callable = _git_rev_parse_head
                         ) -> Tuple[Optional[str], Optional[Dict[str, str]], Optional[str], Optional[str]]:
    """(seal_sha, sealed_params, commit_sha, None)/(None, None, None, reason);
    reason in {"prereg_absent", "prereg_mismatch", "prereg_params_incomplete",
    "commit_unresolved"}. Never raises. ``git_show``/``git_rev_parse`` are
    injectable so a construct test can simulate a committed match without a
    real commit (the rails forbid committing here). AMENDMENT 7(e):
    ``commit_sha`` is the resolved HEAD sha the prereg is tracked at, archived
    by the caller alongside the resolved prereg path so a scored artifact
    names a reconstructible, committed prereg."""
    if not prereg_path.is_file():
        return None, None, None, "prereg_absent"
    raw = prereg_path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    idx = normalized.rfind(b"\n" + SHA_TRAILER.encode("ascii"))
    if idx == -1:
        return None, None, None, "prereg_mismatch"
    body = normalized[:idx + 1]
    trailer = normalized[idx + 1:].decode("ascii", errors="replace").rstrip("\n")
    if not trailer.startswith(SHA_TRAILER):
        return None, None, None, "prereg_mismatch"
    recorded = trailer[len(SHA_TRAILER):].strip()
    computed = hashlib.sha256(body).hexdigest()
    if recorded != computed:
        return None, None, None, "prereg_mismatch"
    root = repo_root or Path(__file__).resolve().parents[3]
    try:
        relative = prereg_path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None, None, None, "prereg_mismatch"
    committed = git_show(root, relative)
    if committed is None or committed.replace(b"\r\n", b"\n") != normalized:
        return None, None, None, "prereg_mismatch"
    params = parse_sealed_params(body)
    if params is None:
        return None, None, None, "prereg_params_incomplete"
    commit_sha = git_rev_parse(root)
    if not commit_sha:
        return None, None, None, "commit_unresolved"
    return computed, params, commit_sha, None


def params_mismatch(sealed: Dict[str, str], args) -> Optional[str]:
    """The real-run CLI refuses any runtime value that differs from the
    sealed one -- seed/draws/fit/holdout come from CLI flags; grids,
    cluster-unit, abstention and the null-decision-rule are sealed-only (no
    CLI flag exists for them, so drift can only come from the prereg text
    itself) and are checked against the CANONICAL runtime constants/policies
    (AMENDMENT 7(d)) -- every SEALED_PARAM_KEYS value, not a subset.
    AMENDMENT 9(a): ``holdout_b_end`` (the second holdout's declared end
    date, previously derived silently from the input corpus's own latest
    date -- BLOCKING in ``_verdict_s450_1i.md``) is now sealed and CLI-bound
    exactly like ``fit_start``/``holdout_a``/``holdout_b``; a refreshed
    corpus cannot move the scored window without also changing this seal."""
    if str(args.seed) != sealed["seed"]:
        return "seed_mismatch"
    if str(args.draws) != sealed["draws"]:
        return "draws_mismatch"
    if args.fit_start != sealed["fit_start"] or args.fit_end != sealed["fit_end"]:
        return "fit_range_mismatch"
    if args.holdout_a != sealed["holdout_a_start"] or args.holdout_b != sealed["holdout_b_start"]:
        return "holdout_range_mismatch"
    if args.holdout_b_end != sealed["holdout_b_end"]:
        return "holdout_b_end_mismatch"
    if sealed["r_grid"] != _fmt_grid(R_GRID) or sealed["beta_grid"] != _fmt_grid(BETA_GRID):
        return "grid_mismatch"
    if sealed["cluster_unit"] != CANONICAL_CLUSTER_UNIT:
        return "cluster_unit_mismatch"
    if sealed["abstention_policy"] != CANONICAL_ABSTENTION_POLICY:
        return "abstention_policy_mismatch"
    if sealed["null_decision_rule"] != CANONICAL_NULL_DECISION_RULE:
        return "null_decision_rule_mismatch"
    return None


def corpus_bound_mismatch(sealed: Dict[str, str], observed_holdout_b_end: Optional[str]) -> Optional[str]:
    """AMENDMENT 11(b), tightening 10(b): the corpus's own observed maximum
    date (read by the caller, ISO YYYY-MM-DD) must EXACTLY EQUAL the sealed
    holdout_b_end BEFORE any charge -- refuses holdout_b_end_mismatch on ANY
    difference, not just a later one. A row PAST the sealed bound silently
    widens the scored window; a corpus that has NOT YET reached the sealed
    bound is an INCOMPLETE denominator (the preregistration commits to
    scoring through the sealed date -- fewer rows silently understates the
    sample, the verifier's exact repro: sealed 2026-07-02, observed
    2026-06-30 used to return None, permitting a charge on an incomplete
    corpus). A missing observed date (e.g. an empty or dateless corpus) is
    refused the same way -- there is no bound to confirm, so it is never
    treated as a pass. Plain ISO-string equality is correct here (fixed
    YYYY-MM-DD width compares chronologically)."""
    if observed_holdout_b_end is None:
        return "holdout_b_end_mismatch"
    if observed_holdout_b_end != sealed["holdout_b_end"]:
        return "holdout_b_end_mismatch"
    return None


def next_k_family(ledger_path: Path, family: str) -> int:
    """The current same-family launch K, READ from the ledger before
    scoring -- never hard-coded. A ledger with one prior same-family row
    (k_family=1) yields 2; a missing/empty ledger yields 1. AMENDMENT 7(c):
    FAILS CLOSED -- raises ValueError("ledger_malformed") on any unparseable
    JSON line, any non-dict row, any row missing "family", or any row whose
    "k_family" is missing or not a plain int (a float such as 3.0 included).
    AMENDMENT 8(b): the "k_family" check runs on EVERY parsed row BEFORE the
    same-family filter -- an unrelated-family row with a malformed k_family
    (e.g. {"family": "other", "k_family": 3.0}) must still refuse; the
    round-7 bug validated k_family only after unrelated families were
    already skipped, so a malformed unrelated-family row silently passed
    through. Never silently skips a row that could undercharge the family."""
    if not ledger_path.is_file():
        return 1
    max_k = 0
    for line in ledger_path.read_text(encoding="ascii").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise ValueError("ledger_malformed") from None
        if not isinstance(row, dict) or "family" not in row:
            raise ValueError("ledger_malformed")
        k_val = row.get("k_family")
        if not isinstance(k_val, int) or isinstance(k_val, bool):
            raise ValueError("ledger_malformed")
        if row["family"] != family:
            continue
        if k_val > max_k:
            max_k = k_val
    return max_k + 1


def append_charge_row(ledger_path: Path, family: str, k_family: int, instant: int,
                      prereg_seal: str) -> dict:
    """The launch charge row, appended BEFORE build_report. Raises
    ValueError("ledger_unwritable") on any I/O failure, never silently."""
    row = {"family": family, "k_family": k_family, "instant": instant, "prereg_seal": prereg_seal}
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a", encoding="ascii") as fh:
            fh.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    except OSError as exc:
        raise ValueError("ledger_unwritable") from exc
    return row
