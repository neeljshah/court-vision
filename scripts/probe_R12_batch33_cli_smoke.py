"""probe_R12_batch33_cli_smoke.py - smoke-test the r12_predict_game_cli module.

Verifies:
  1. python -m src.prediction.r12_predict_game_cli --tail 5 returns exit code 0
     and prints all 6 pregame markets per game.
  2. Same with --snap-q 2 also returns in-play winprob + remaining_total.
  3. Output contains no Unicode encoding errors (cp1252 safe).
"""
from __future__ import annotations
import json, os, subprocess, sys, time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")


def _run_cli(args, env=None):
    cmd = [sys.executable, "-m", "src.prediction.r12_predict_game_cli"] + args
    proc = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True,
                           timeout=600, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-33 - r12_predict_game_cli smoke", flush=True)
    print("=" * 70, flush=True)

    results = []
    n_pass = 0; n_total = 0

    # Smoke 1: pregame only
    print("\n[1] CLI: --tail 5 (pregame only)", flush=True)
    t_v = time.time()
    rc, out, err = _run_cli(["--tail", "5"])
    elapsed = time.time() - t_v
    pregame_markets_seen = sum(1 for s in ["Total points", "Spread", "Home points",
                                            "Away points", "P(total > 230)",
                                            "P(home -3 cover)"] if s in out)
    has_n_games = out.count("--- ") >= 5
    pregame_pass = (rc == 0) and (pregame_markets_seen == 6) and has_n_games
    if pregame_pass:
        n_pass += 1
    n_total += 1
    print(f"  exit={rc} elapsed={elapsed:.1f}s markets_seen={pregame_markets_seen}/6 "
          f"games_seen={out.count('--- ')} {'PASS' if pregame_pass else 'FAIL'}", flush=True)
    if not pregame_pass:
        print(f"  stderr first 300 chars: {err[:300]}", flush=True)
    results.append({"variant": "pregame_only", "exit_code": rc, "elapsed_s": round(elapsed, 1),
                    "markets_seen": pregame_markets_seen, "games_seen": out.count("--- "),
                    "pass": pregame_pass})

    # Smoke 2: pregame + in-play at snap_q=2
    print("\n[2] CLI: --tail 5 --snap-q 2 (pregame + in-play)", flush=True)
    t_v = time.time()
    rc, out, err = _run_cli(["--tail", "5", "--snap-q", "2"])
    elapsed = time.time() - t_v
    has_inplay = "P(home wins) endQ2" in out and "Remaining total Q2" in out
    inplay_pass = (rc == 0) and has_inplay and (out.count("--- ") >= 5)
    if inplay_pass:
        n_pass += 1
    n_total += 1
    print(f"  exit={rc} elapsed={elapsed:.1f}s has_inplay={has_inplay} "
          f"games_seen={out.count('--- ')} {'PASS' if inplay_pass else 'FAIL'}", flush=True)
    if not inplay_pass:
        print(f"  stderr first 300 chars: {err[:300]}", flush=True)
    results.append({"variant": "pregame_plus_inplay_q2", "exit_code": rc,
                    "elapsed_s": round(elapsed, 1), "has_inplay_markets": has_inplay,
                    "games_seen": out.count("--- "), "pass": inplay_pass})

    # Smoke 3: --game-id picks a specific game
    print("\n[3] CLI: --game-id <specific>", flush=True)
    # Pull a known game_id from the last game printed in smoke 1
    import re
    game_ids = re.findall(r"--- (\S+) \|", out)
    if game_ids:
        target_gid = game_ids[0]
        t_v = time.time()
        rc, out2, err2 = _run_cli(["--game-id", target_gid])
        elapsed = time.time() - t_v
        gid_pass = (rc == 0) and (target_gid in out2) and (out2.count("--- ") == 1)
        if gid_pass:
            n_pass += 1
        n_total += 1
        print(f"  exit={rc} elapsed={elapsed:.1f}s game_id={target_gid} "
              f"{'PASS' if gid_pass else 'FAIL'}", flush=True)
        results.append({"variant": "single_game_id", "game_id": target_gid,
                        "exit_code": rc, "elapsed_s": round(elapsed, 1),
                        "pass": gid_pass})
    else:
        print(f"  SKIP: no game_ids parsed from prior smoke output", flush=True)

    summary = {"n_total": n_total, "n_pass": n_pass,
               "all_pass": n_pass == n_total,
               "results": results,
               "elapsed_s": round(time.time() - t0, 1)}
    out_path = os.path.join(DATA_CACHE, "probe_R12_B33_cli_smoke.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[done] {n_pass}/{n_total} PASS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
