"""Push one SEALED signal family through the landed leak-free gate on ONE charge.
Order, fixed (Q1/Q2): seal -> git-committed manifest (commit SHA recorded; the bypass is a
test-only keyword seam, never a CLI flag, recorded as manifest_committed false) -> prior
max K -> validate corpus -> ONE charge -> charge.json -> score, K being the charged row's OWN
k_cumulative. A crash after the charge leaves charge.json and failure.json (the charge
stands); an occupied --out is REFUSED; an identical digest needs explicit failure resume.
The declared link fits training rows only; paired losses and model traces are archived.
Romano-Wolf is secondary. Stdout: accounting lines only. Calibration language only.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple
import numpy as np
from scripts.platformkit.combo.fwer_budget import cumulative_k, eps_eff, min_corpora_eff
from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger, assert_canonical_ledger, load_states
from scripts.platformkit.eval_gate import signal_audit_catalog as catalog
from scripts.platformkit.eval_gate.ledger import load_fwer
from scripts.platformkit.eval_gate.signal_audit_family import (
    EVALUABLE, MEMBER_FIELDS, charged_run, check_seal, resolve_builder, strict_int, validate_manifest, write_text_atomic,
)
from scripts.platformkit.eval_gate.signal_audit_verdicts import (
    EPS_FAMILY, census, member_row, not_evaluable_row, paired_series, refused_row,
    render_series, score_member, survivors, underpowered_row, common_romano_wolf,
)
from scripts.platformkit.eval_gate.walkforward import walk_forward, EMBARGO_DAYS, assert_vintage, redact_test_view
from scripts.platformkit.ingame.gate_a0_ingame_vs_market import N_BOOT, N_MIN_GAMES, SEED
SPEC_ID = "scripts.platformkit.eval_gate.signal_audit_runner:family"
MIN_TRAIN, RIDGE, NEWTON_STEPS, _ETA_CLIP = 20, 1.0, 25, 700.0
CODE_FILES = ("signal_audit_catalog.py", "signal_audit_family.py", "signal_audit_runner.py", "signal_audit_verdicts.py")
REFERENCE_CHANNEL = ("p_close is served from a runner side table keyed by game_id, NOT through "
                     "redact_test_view, which drops devig_close_prob from the test view")
MANIFEST_PRINTED = ("n_members", "n_declared_evaluable", "n_not_evaluable")
AVAILABILITY_FIELDS = frozenset(("reference_available_at", "settled_at"))
NOT_VERIFIED = ["no corpus outside the single window named by the manifest was scored",
                "the declared link is one additive logit link; other forms are untested",
                "an AHEAD(SINGLE-WINDOW) row is not a result and is never promoted here"]
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x >= 0.0 else math.exp(x) / (1.0 + math.exp(x))
def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))
def _close(value: object, game_id: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("reference close for %r is %r, not a real number" % (game_id, value))
    if not math.isfinite(p := float(value)) or not 0.0 < p < 1.0:
        raise ValueError("reference close %r for %r is not a probability in (0,1)" % (p, game_id))
    return p
def fit_beta(z: np.ndarray, offset: np.ndarray, y: np.ndarray) -> float:
    """Newton from beta=0 on the TRAINING SLICE ONLY: close as offset, fixed declared ridge."""
    beta = 0.0
    for _step in range(NEWTON_STEPS):
        p = 1.0 / (1.0 + np.exp(-np.clip(offset + beta * z, -_ETA_CLIP, _ETA_CLIP)))
        grad = float(np.dot(z, y - p)) - RIDGE * beta
        hess = float(np.dot(z * z, p * (1.0 - p))) + RIDGE
        if not math.isfinite(grad) or not math.isfinite(hess) or hess <= 0.0:
            return 0.0
        beta += (step := grad / hess)
        if abs(step) < 1e-10:
            break
    return float(beta) if math.isfinite(beta) else 0.0
def reference_fn(close_by_game: Dict[str, float], train: Sequence[dict], test: dict, select_inside: bool) -> float:
    """The reference arm: the devigged close itself (REFERENCE_CHANNEL, not the test view)."""
    return _close(close_by_game[test["game_id"]], test["game_id"])
def make_candidate_fn(new_build: Callable[[], Callable[[dict], float]],
                      close_by_game: Dict[str, float], settled_by_game: Dict[str, str]) -> Callable:
    """Fit the declared link on settled training rows with a fresh builder per fold."""
    trace: List[dict] = []
    def predict(train: Sequence[dict], test: dict, select_inside: bool) -> float:
        train = [r for r in train if settled_by_game[r["game_id"]] <= test["state_ts"]]
        p_close = _close(close_by_game[test["game_id"]], test["game_id"])
        ids = "|".join(str(row["game_id"]) for row in train).encode("ascii")
        step = {"game_id": str(test["game_id"]), "ts": str(test["state_ts"]), "beta": None,
                "n_train": len(train), "train_ids_sha256": hashlib.sha256(ids).hexdigest(),
                "mu": None, "sd": None, "x_feature": None}
        trace.append(step)
        if len(train) < MIN_TRAIN:
            return p_close                  # no build on a head state: it fits nothing here
        build = new_build()
        xs, offsets, ys = [], [], []
        for row in train:
            xs.append(build(row))
            offsets.append(_logit(_close(row["devig_close_prob"], row["game_id"])))
            ys.append(float(strict_int(row["outcome"], "outcome")))
        values = np.asarray(xs, dtype=float)
        mu, sd = float(values.mean()), float(values.std())
        if not math.isfinite(sd) or sd <= 0.0:
            return p_close
        beta = fit_beta((values - mu) / sd, np.asarray(offsets, float), np.asarray(ys, float))
        x_test = build(test)                # the test row is built LAST, after the fit
        eta = _logit(p_close) + beta * ((x_test - mu) / sd)
        if not math.isfinite(eta):
            raise ValueError("non-finite linear predictor for %r" % test["game_id"])
        step.update({"beta": beta, "mu": mu, "sd": sd, "x_feature": x_test})
        return _sigmoid(eta)
    predict.trace = trace
    return predict
def assert_committed(path: Path) -> str:
    """Q1: the manifest must be committed BEFORE the run. Returns its commit SHA."""
    posix = Path(path).as_posix()
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args, "--", posix], capture_output=True, text=True)
    if git("ls-files", "--error-unmatch").returncode != 0:
        raise ValueError("manifest %s is not git-committed; commit the seal before any run" % path)
    dirty = git("status", "--porcelain").stdout.strip()
    if dirty:
        raise ValueError("manifest %s has uncommitted changes: %r" % (path, dirty))
    sha = git("log", "-1", "--format=%H").stdout.strip()
    if len(sha) != 40:
        raise ValueError("no commit records manifest %s; the seal is staged, not committed" % path)
    return sha
def _allowances(k_at_launch: int, n_evaluable: int) -> Tuple[Decimal, Decimal | None]:
    """Decimal allowances whose float value IS the landed eps_eff bar, byte for byte."""
    family = Decimal(repr(bar := eps_eff(EPS_FAMILY, k_at_launch)))
    if float(family) != bar:
        raise AssertionError("the Decimal allowance is not the landed bar: %s != %r" % (family, bar))
    if n_evaluable <= 0:
        return family, None
    if not (member := family / Decimal(n_evaluable)) > 0:
        raise ValueError("member allowance underflowed to %s at %d members" % (member, n_evaluable))
    return family, member
def _romano_wolf(payloads: Sequence[dict], rw_n_bootstrap: int | None, n_min: int = N_MIN_GAMES) -> dict:
    return common_romano_wolf(payloads, rw_n_bootstrap, n_min)
def run_family_audit(manifest_path: Path, ledger_path: Path, out_dir: Path, *,
                     dry_run: bool = False, states_loader: Callable = load_states,
                     repo: Path | None = None, n_boot: int = N_BOOT, seed: int = SEED,
                     n_min: int = N_MIN_GAMES, rw_n_bootstrap: int | None = None,
                     allow_noncanonical_ledger: bool = False, allow_uncommitted_manifest: bool = False,
                     resume_charge: str | None = None, resume_from: Path | None = None) -> dict:
    """Seal -> committed -> validate rows -> ONE charge -> full-matrix artifact."""
    manifest_path, ledger_path, out = Path(manifest_path), Path(ledger_path), Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("--out %s is occupied; use a NEW directory" % out)
    out.mkdir(parents=True, exist_ok=True)
    before, raw = manifest_path.stat(), manifest_path.read_bytes()
    digest = check_seal(manifest_path, raw)
    commit = None if allow_uncommitted_manifest else assert_committed(manifest_path)
    manifest = validate_manifest(json.loads(raw))
    if any(getattr(manifest_path.stat(), k) != getattr(before, k)
           for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")):
        raise ValueError("manifest_changed_during_validation")
    sport, start, end = manifest["sport"], manifest["start"], manifest["end"]
    n_eval = strict_int(manifest["n_declared_evaluable"], "n_declared_evaluable")
    canonical = assert_canonical_ledger(ledger_path, allow_noncanonical_ledger)
    prior = max((strict_int(row["k_cumulative"], "k_cumulative") for row in load_fwer(ledger_path)
                 if row.get("k_cumulative") is not None), default=0)
    print("ledger %s\nfamily %s\nprior_max_k %d\n" % (ledger_path.as_posix(), manifest["family"], prior)
          + "\n".join("%s %d" % (n, strict_int(manifest[n], n)) for n in MANIFEST_PRINTED))
    availability_declared = (states_loader is not load_states and
                            AVAILABILITY_FIELDS <= set(getattr(states_loader, "availability_fields", ())))
    if dry_run:
        print("k_if_charged %d\ncharged 0" % cumulative_k(prior, 1))
        print("validation NOT VALIDATED")
        return {"dry_run": True, "prior_max_k": prior, "family": manifest["family"],
                "k_if_charged": cumulative_k(prior, 1), "n_declared_evaluable": n_eval,
                "validation": "NOT VALIDATED", "availability_declared_informational": availability_declared}
    try:
        states, settled = catalog.prepare_states(deepcopy(states_loader(sport, start, end, repo, corpus_counts := {})))
        seen = set()
        for state in states:
            try:
                game_id = state["game_id"]
                if not isinstance(game_id, str) or not game_id:
                    raise ValueError("game_id_invalid")
                if game_id in seen:
                    raise ValueError("duplicate game_id: " + game_id)
                seen.add(game_id)
                _close(state["devig_close_prob"], game_id)
                if type(state.get("outcome")) is not int or state["outcome"] not in (0, 1):
                    raise ValueError("outcome_not_strict_binary")
                assert_vintage(state)
                redact_test_view(state, strict=True)
            except (KeyError, TypeError, ValueError, AssertionError) as exc:
                raise type(exc)("%s; game_id=%r; value=%r" % (exc, state.get("game_id"), state)) from exc
        if not states:
            raise ValueError("corpus_empty")
        if len(states) < n_min:
            raise ValueError("corpus_below_n_min: count=%d n_min=%d" % (len(states), n_min))
    except Exception as exc:
        write_text_atomic(out / "validation.json", json.dumps({"validation": "NOT VALIDATED",
            "reason": str(exc), "charged": 0}, allow_nan=False) + "\n")
        raise
    with charged_run(ledger_path, out, manifest, digest, prior, commit, resume_charge, resume_from,
                     _charge_ledger, load_fwer, write_text_atomic, SPEC_ID) as charge:
        k_at_launch = strict_int(charge["k_cumulative"], "k_cumulative")
        family_allowance, member_allowance = _allowances(k_at_launch, n_eval)
        receipt = json.loads((out / "charge.json").read_text(encoding="ascii"))
        receipt.update(family_allowance=str(family_allowance),
                       member_allowance=None if member_allowance is None else str(member_allowance))
        write_text_atomic(out / "charge.json", json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n")
        print("k_at_launch %d" % k_at_launch)
        report = {"spec_id": SPEC_ID, "family": manifest["family"], "sport": sport,
                  "window": [start, end], "tier": manifest["tier"], "hypothesis_hash": digest,
                  "manifest_path": manifest_path.as_posix(), "ledger_path": ledger_path.as_posix(),
                  "ledger_canonical": canonical, "prior_max_k": prior, "k_at_launch": k_at_launch,
                  "manifest_committed": commit is not None, "manifest_commit": commit,
                  "reference_channel": REFERENCE_CHANNEL, "n_allowance_divisor": n_eval,
                  "allowance_source": "eps_eff(0.05, k_at_launch), Bonferroni over evaluable members",
                  "family_allowance": str(family_allowance), "charge": charge,
                  "member_allowance": None if member_allowance is None else str(member_allowance),
                  "identities": {"manifest_sha256": digest, "code_sha256": {name: hashlib.sha256(
                      (Path(__file__).resolve().parent / name).read_bytes()).hexdigest() for name in CODE_FILES}},
                  "min_corpora_eff_at_launch_k": int(min_corpora_eff(1, k_at_launch))}
        report.update(_score_family(manifest, digest, member_allowance, out, (states, settled, corpus_counts), n_boot, seed, n_min, rw_n_bootstrap),
                      generated_at=datetime.now(timezone.utc).isoformat(), not_verified=NOT_VERIFIED)
        write_text_atomic(out / "family_audit.json", json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n")
        print("\n".join("%s %d" % (name, report[name]) for name in ("n_states", "n_games", "n_refused")))
        return report
def _score_family(manifest: dict, digest: str, member_allowance: Decimal | None, out: Path, snapshot: tuple,
                  n_boot: int, seed: int, n_min: int, rw_n_bootstrap: int | None) -> dict:
    """Reference arm once, then every evaluable member. Nothing here runs before the charge."""
    states, settled, corpus_counts = snapshot
    counts_sha = hashlib.sha256(json.dumps(corpus_counts, sort_keys=True).encode("ascii")).hexdigest()
    identity = (("manifest_sha256", digest), ("corpus_counts_sha256", counts_sha))  # a moved CSV self-identifies
    close_by_game = {s["game_id"]: s["devig_close_prob"] for s in states}
    reference = walk_forward(states, partial(reference_fn, close_by_game), strict_redaction=True, guard_state_keys=True).records
    rows, payloads, refused = [], [], 0
    for index, member in enumerate(manifest["members"]):
        if member["alias_of"] is not None:
            continue
        if member["evaluability"] != EVALUABLE:
            rows.append(not_evaluable_row(member))
            continue
        if member_allowance is None:
            raise ValueError("an evaluable member with no member allowance")
        try:
            scope, cover = states, None
            if member["source"] == catalog.SOURCE:
                new_build, scope, cover = catalog.arm(member, states)
                if strict_int(cover["n_games_finite"], "n_games_finite") < n_min:
                    rows.append(underpowered_row(member, catalog.coverage_note(cover, n_min), cover))
                    continue
            else:
                new_build = partial(resolve_builder, member["feature_builder"])
            fn = make_candidate_fn(new_build, close_by_game, settled)
            wf = walk_forward(scope, fn, strict_redaction=True, guard_state_keys=True)
            brier_rows, logloss_rows = paired_series(wf.records, reference, fn.trace)
            scored = score_member(brier_rows, logloss_rows, member_allowance, n_boot, seed, n_min)
            scored["n_states_at_min_train"] = sum(s["n_train"] < MIN_TRAIN for s in fn.trace)
        except (KeyError, TypeError, ValueError) as exc:
            rows.append(refused_row(member, "%s: %s" % (type(exc).__name__, exc)))
            refused += 1
            continue
        paths = {label: write_text_atomic(out / "paired_loss" / ("%03d_%s.csv" % (index, label)), render_series(series, identity)).relative_to(out).as_posix()
                 for label, series in (("brier", brier_rows), ("logloss", logloss_rows))}
        payloads.append({"member": member, "brier": brier_rows, "scored": scored,
                         "paths": paths, "coverage": cover})
    for alias in (m for m in manifest["members"] if m["alias_of"] is not None):
        shared = next((p for p in payloads if p["member"]["member_key"] == alias["alias_of"]), None)
        if shared is not None:
            payloads.append(dict(shared, member=alias))
        else:
            shared = next(r for r in rows if r["member_key"] == alias["alias_of"])
            rows.append(member_row(alias, **{k: v for k, v in shared.items() if k not in MEMBER_FIELDS}))
            refused += int(shared["verdict"] == "REFUSED")
    payloads.sort(key=lambda p: p["member"]["member_key"])
    rw = _romano_wolf(payloads, rw_n_bootstrap, n_min)
    for position, item in enumerate(payloads):
        rows.append(member_row(item["member"], paired_loss_series=item["paths"], coverage=item["coverage"],
                               rw_adjusted_p=(float(rw["adjusted_p"][position]) if rw else None),
                               rw_adjusted_reject=(bool(rw["rejected"][position]) if rw else None),
                               note="Romano-Wolf is secondary and never decides; the verdict is the interval",
                               **item["scored"]))
    rows.sort(key=lambda row: row["member_key"])
    return {"corpus_counts": corpus_counts, "n_states": int(n_states := len(reference)),
            "n_games": int(n_games := len({r["game_id"] for r in reference})), "n_refused": int(refused),
            "corpus_counts_sha256": counts_sha, "clustering_inert_at_grain": n_games == n_states,
            "bootstrap": {"n_boot": int(n_boot), "seed": int(seed), "n_min_games": int(n_min),
                          "romano_wolf_n_bootstrap": rw.get("n_bootstrap"), "n_states_common": rw.get("n_states_common", 0)},
            "link": manifest["link"], "catalog_context": catalog.CONTEXT_DECLARATION,
            "fit": {"min_train": MIN_TRAIN, "ridge": RIDGE, "newton_steps": NEWTON_STEPS, "embargo_days": EMBARGO_DAYS},
            "counts": census(rows), "members": rows, "survivors": survivors(rows)}
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="signal_audit_runner", description=__doc__.splitlines()[0])
    parser.add_argument("--family-manifest", required=True, help="a SEALED, COMMITTED manifest")
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="a NEW dir; an occupied one is refused")
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="census and the K it would read")
    parser.add_argument("--resume-charge", help="existing ledger row id (k_cumulative); requires failure.json")
    parser.add_argument("--resume-from", type=Path, help="prior failed output directory; defaults to siblings of --out")
    return parser
def main(argv: Sequence[str] | None = None) -> int:   # no bypass reaches the CLI: Q1 and Q2 hold
    args = _parser().parse_args(argv)
    run_family_audit(Path(args.family_manifest), args.ledger, args.out,
                     dry_run=args.dry_run, repo=args.repo, resume_charge=args.resume_charge, resume_from=args.resume_from)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
