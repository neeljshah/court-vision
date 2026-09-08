"""Run a configured S287 restriction arm and archive its environment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.platformkit import env_sidecar
from scripts.platformkit.ingame import s287_sim_full_pod as repeat

ROOT = Path(__file__).resolve().parents[3]
TICK_COLUMNS = (
    "outcome_home_win", "market_prob", "p_null", "p_simulator", "loss_market",
    "loss_recal_null", "loss_simulator", "paired_loss_recal_null_minus_simulator",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_tick_series(control: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    """Return exact per-column deltas after a one-to-one state-key check."""
    left = control.sort_values("state_key").reset_index(drop=True)
    right = candidate.sort_values("state_key").reset_index(drop=True)
    if not left.state_key.is_unique or not right.state_key.is_unique:
        raise ValueError("state_key must identify one evaluator state")
    if not left.state_key.equals(right.state_key):
        raise ValueError("state-key sets differ")
    result = {}
    for column in TICK_COLUMNS:
        delta = (left[column].astype(float) - right[column].astype(float)).abs()
        result[column] = {
            "max_abs_delta": float(delta.max()),
            "ticks_gt_1e9": int((delta > 1e-9).sum()),
        }
    return result


def audit_states(game_ids: list[str]) -> pd.DataFrame:
    """Per-state seed and possession count: the only draw-count input that is a float round.

    ``fast_sim.simulate_game_fast`` loops ``range(n_poss)`` with ``n_poss =
    int(round((home.pace + away.pace) / 2))``; every draw inside a possession is
    vectorised over all lanes, so the tick's draw count depends on nothing else.
    """
    from scripts.platformkit.ingame import s256_nba_sim_engine_v3 as sim

    inputs = sim.Inputs()
    selected = repeat._eligible(inputs, game_ids)
    grid = repeat._grid(sim.read_archive(selected.game.tolist(), inputs.archive), selected)
    pmean, tmean = sim.read_snapshots(inputs, selected)
    states, _ = sim.make_states(grid, pmean, tmean)
    rows = [{
        "state_key": state["game_id"],
        "seed": int(state["features"]["seed"]),
        "pace_hex": float(state["features"]["pace"]).hex(),
        "n_poss": int(round((state["features"]["pace"] + state["features"]["pace"]) / 2)),
    } for state in states]
    return pd.DataFrame(rows).sort_values("state_key").reset_index(drop=True)


def rng_probe(seed: int = 401809918) -> dict:
    """Same-seed torch stream probe: does the uniform stream, the categorical choice or
    the amount the generator advances move between environments?"""
    import torch

    out = {"torch": torch.__version__, "num_threads": int(torch.get_num_threads())}
    gen = torch.Generator(device="cpu")
    gen.manual_seed(seed)
    out["rand8"] = [float(v) for v in torch.rand(8, generator=gen)]
    gen = torch.Generator(device="cpu")
    gen.manual_seed(seed)
    weights = torch.tensor([[0.2, 0.3, 0.5]] * 4)
    out["pick"] = [int(v) for v in torch.multinomial(weights + 1e-9, 1, generator=gen).squeeze(1)]
    out["rand_after_pick"] = [float(v) for v in torch.rand(4, generator=gen)]
    gen = torch.Generator(device="cpu")
    gen.manual_seed(seed)
    out["lineup"] = [int(v) for v in torch.multinomial(torch.tensor([1.0]), 32,
                                                       replacement=True, generator=gen)]
    out["rand_after_lineup"] = [float(v) for v in torch.rand(4, generator=gen)]
    return out


def _compact(summary: dict, out_dir: Path) -> None:
    """Move the per-game fill detail out of the summary so the JSON stays reviewable."""
    fills = pd.DataFrame(summary.get("fills", []))
    fills.to_csv(out_dir / "S287_fills.csv", index=False)
    summary["fills_csv"] = {
        "path": "S287_fills.csv",
        "rows": int(len(fills)),
        "sha256": _sha(out_dir / "S287_fills.csv"),
    }
    (out_dir / "S287_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="ascii")


def run(game_ids: list[str], out_dir: Path, torch_threads: int | None,
        deterministic: bool) -> dict:
    """Score one sealed restriction arm without changing its simulator defaults."""
    if torch_threads is not None or deterministic:
        import torch

        if torch_threads is not None:
            torch.set_num_threads(torch_threads)
        if deterministic:
            torch.use_deterministic_algorithms(True)
    summary, scored, per_game = repeat.score(game_ids)
    summary["s316"] = {
        "deterministic_algorithms": deterministic,
        "entrypoint_sha256": _sha(Path(__file__)),
        "torch_threads_requested": torch_threads,
    }
    repeat._write(summary, scored, per_game, out_dir)
    _compact(summary, out_dir)
    env_sidecar.write(
        out_dir / "environment.json",
        modules=[
            "scripts/platformkit/ingame/s316_mc_cross_env.py",
            "scripts/platformkit/ingame/s287_sim_full_pod.py",
            "scripts/platformkit/ingame/s256_nba_sim_engine_v3.py",
            "src/sim/fast_sim.py",
            "src/sim/basketball_sim.py",
        ],
        seed=2561001,
    )
    return summary


def _ticks(path: Path) -> pd.DataFrame:
    """Accept an arm directory holding one tick series, or that CSV directly."""
    if path.is_dir():
        found = sorted(path.glob("*_tick_series.csv"))
        if len(found) != 1:
            raise ValueError("one tick series is required in " + path.as_posix())
        path = found[0]
    return pd.read_csv(path)


def compare_arms(pairs: list[tuple[str, Path, Path]]) -> dict:
    """Score each preregistered pair: per-column tick deltas and simulator Brier/ECE deltas."""
    from scripts.platformkit.eval_gate.scoring import brier, ece

    out = {}
    for label, control_path, candidate_path in pairs:
        control, candidate = _ticks(control_path), _ticks(candidate_path)
        columns = compare_tick_series(control, candidate)
        scores = []
        for frame in (control, candidate):
            values = frame.p_simulator.to_numpy(float)
            y = frame.outcome_home_win.to_numpy(float)
            scores.append((brier(values, y), ece(values, y, bins=10)))
        out[label] = {
            "control": control_path.as_posix(),
            "candidate": candidate_path.as_posix(),
            "n_ticks": int(len(control)),
            "max_abs_p_simulator_delta": columns["p_simulator"]["max_abs_delta"],
            "ticks_gt_1e9": columns["p_simulator"]["ticks_gt_1e9"],
            "sim_brier_control": scores[0][0], "sim_brier_candidate": scores[1][0],
            "sim_brier_delta": scores[0][0] - scores[1][0],
            "sim_ece_control": scores[0][1], "sim_ece_candidate": scores[1][1],
            "sim_ece_delta": scores[0][1] - scores[1][1],
            "columns_max_abs_delta": {k: v["max_abs_delta"] for k, v in columns.items()},
            "columns_ticks_gt_1e9": {k: v["ticks_gt_1e9"] for k, v in columns.items()},
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-ids")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--pair", nargs=3, action="append", metavar=("LABEL", "CONTROL", "CANDIDATE"))
    parser.add_argument("--torch-threads", type=int)
    parser.add_argument("--deterministic", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--rng-probe", action="store_true")
    args = parser.parse_args()
    if args.rng_probe:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        target = args.out_dir / "S316_rng_probe.json"
        target.write_text(json.dumps(rng_probe(), indent=2, sort_keys=True), encoding="ascii")
        print("RNG PROBE SHA " + _sha(target))
        return 0
    if args.pair:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        target = args.out_dir / "S316_arm_comparisons.json"
        result = compare_arms([(label, Path(a), Path(b)) for label, a, b in args.pair])
        target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="ascii")
        for label, values in sorted(result.items()):
            print("PAIR %s n=%d max_delta %.12g gt1e9 %d brier_delta %.12g ece_delta %.12g" % (
                label, values["n_ticks"], values["max_abs_p_simulator_delta"],
                values["ticks_gt_1e9"], values["sim_brier_delta"], values["sim_ece_delta"]))
        print("COMPARISON SHA " + _sha(target))
        return 0
    if not args.game_ids:
        parser.error("--game-ids is required unless --pair is used")
    if args.audit_only:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        target = args.out_dir / "S316_draw_count_audit.csv"
        audit_states(args.game_ids.split(",")).to_csv(target, index=False)
        print("AUDIT SHA " + _sha(target))
        return 0
    summary = run(args.game_ids.split(","), args.out_dir, args.torch_threads,
                  args.deterministic)
    for name, values in summary["arms"].items():
        print("ARM %s BRIER %.12f ECE %.12f" % (name, values["brier"], values["ece_10"]))
    print("FINAL SHA " + _sha(args.out_dir / "S287_summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
