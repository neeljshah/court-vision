"""One-command proof: run every reference test module and print a consolidated scoreboard.

    C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe run_all.py

Exit 0 iff all modules pass. This mirrors the eval gate's own fail-closed contract: the reference
core is itself only "shipped" when every test is green. No network, no data/, calibration-only.
"""
from __future__ import annotations
import importlib, sys, traceback

MODULES = ["test_eval_core", "test_walkforward", "test_shin", "test_ingame_blend",
           "test_freshness", "test_ledger"]


def run_module(name: str) -> tuple:
    mod = importlib.import_module(name)
    fns = [v for k, v in sorted(vars(mod).items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
        except Exception:
            print(f"  FAIL {name}.{fn.__name__}")
            traceback.print_exc()
    return passed, len(fns)


def main() -> int:
    total_p, total_n = 0, 0
    print("eval-gate reference core -- test scoreboard")
    print("-" * 44)
    for m in MODULES:
        p, n = run_module(m)
        total_p += p
        total_n += n
        flag = "OK " if p == n else "XX "
        print(f"  {flag}{m:<20} {p}/{n}")
    print("-" * 44)
    print(f"  TOTAL                {total_p}/{total_n}")
    ok = total_p == total_n and total_n > 0
    print("\nALL GREEN" if ok else "\nFAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
