"""Consolidated P10 headless regression runner; commands and verdict are auditable.

Windows x64 with D3D12, Python, NumPy, Zig/SDK required for native cases.
python run_world_sweep.py --full
python run_world_sweep.py              # CPU unit tests + three native demos
"""
from pathlib import Path
import argparse
import json
import os
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence" / "p10" / "world-sweep"


def execute(name, argv, timeout, results):
    start = time.perf_counter()
    log = EVIDENCE / (name + ".log")
    with log.open("w", encoding="utf-8") as out:
        try:
            proc = subprocess.run([sys.executable, *argv], cwd=ROOT,
                                  stdout=out, stderr=subprocess.STDOUT,
                                  timeout=timeout, check=False)
            status = "PASS" if proc.returncode == 0 else "FAIL"
            error = None if proc.returncode == 0 else "nonzero exit"
            code = proc.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            status, error, code = "FAIL", str(exc), None
    row = {"name": name, "command": [sys.executable, *argv], "status": status,
           "exit_code": code, "seconds": time.perf_counter() - start,
           "log": str(log.relative_to(ROOT)), "failure": error}
    if status == "PASS" and name.startswith("world-"):
        demo = ROOT / "evidence" / "p10" / (name + ".json")
        try:
            parsed = json.loads(demo.read_text())
            row["measurements"] = parsed["summary"]
            row["interaction_class"] = parsed["workload"]
            row["device"] = parsed["adapter"]
        except (OSError, KeyError, ValueError) as error:
            row.update(status="FAIL", failure=f"missing/invalid JSON: {error}")
    results.append(row)
    print(status, name, flush=True)
    return status == "PASS"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true",
                   help="also run native P10 physics, legacy pool/rail and 10K/100K/1M")
    p.add_argument("--skip-stress", action="store_true",
                   help="explicitly mark large native stress cases unverified")
    args = p.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    rows = []
    result = {"status": "NO-GO", "scope": "application-facing headless world API",
              "host": {"platform": platform.platform(), "python": sys.version},
              "tests": rows, "native_physics": "NOT RUN", "legacy": "NOT RUN",
              "stress": "NOT RUN", "production_release": "NOT QUALIFIED",
              "P9": "PR #6 merged as incomplete evidence, bitwise replay UNSUPPORTED",
              "claims": "No unsupported tail latency, deadline or topology claims"}
    try:
        execute("cpu-world", ["-m", "unittest", "test_sunder_world", "-q"], 90, rows)
        # One build for all native users; no generated shaders edited by hand.
        native = platform.system() == "Windows"
        if not native:
            result["native_physics"] = "NOT RUN: Windows/D3D12 host required"
        else:
            built = execute("build", ["build_physics3.py"], 300, rows)
            if built:
                for name, n, bodies, steps in [
                    ("world-empty", 1, 0, 4),
                    ("world-16", 16, 16, 8),
                    ("world-1024", 1024, 1024, 8)]:
                    execute(name, ["headless_demo.py", "--capacity", str(n),
                                   "--bodies", str(bodies), "--steps", str(steps),
                                   "--replay", "--out",
                                   str(Path("evidence/p10") / (name + ".json"))], 180, rows)
                if args.full:
                    execute("native-physics", ["test_physics3.py", "--smoke"], 240, rows)
                    result["native_physics"] = rows[-1]["status"]
                    execute("legacy-pool-rail", ["dev_test.py", "full"], 900, rows)
                    result["legacy"] = rows[-1]["status"]
                    if not args.skip_stress:
                        execute("native-stress", ["test_physics3.py", "--stress",
                                                  "10000", "100000", "1000000"], 600, rows)
                        result["stress"] = rows[-1]["status"]
                    else:
                        result["stress"] = "NOT RUN: user requested --skip-stress"
                else:
                    result["native_physics"] = "NOT RUN: require --full for full physics oracle"
        result["status"] = ("PASS: bounded executed cases; NOT production-qualified"
                            if rows and all(r["status"] == "PASS" for r in rows)
                            and native and (not args.full or
                            result["native_physics"] == result["legacy"] == "PASS" and
                            result["stress"] == "PASS")
                            else "NO-GO: incomplete or failed applicable qualification")
    finally:
        result["applicable_gates_completed"] = result["status"].startswith("PASS")
        (EVIDENCE / "consolidated.json").write_text(json.dumps(result, indent=2))
        print(json.dumps({"verdict": result["status"],
                          "evidence": str(EVIDENCE / "consolidated.json")}, indent=2))
    return 0 if result["applicable_gates_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
