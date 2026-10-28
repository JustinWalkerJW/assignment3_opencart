"""Run actual pytest scenarios and bundle their logs/evidence for review.

Usage: python run_tests.py
       python run_tests.py --headless
       python run_tests.py --collect-only
Uses the current interpreter; install requirements.txt in its venv first.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=20)
    parser.add_argument("--driver-path")
    parser.add_argument("--chrome-binary")
    parser.add_argument("--test", help="Optional pytest file/node ID; default runs all 9")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    missing = [name for name in ("pytest", "selenium") if importlib.util.find_spec(name) is None]
    if missing:
        print("Missing dependencies: " + ", ".join(missing))
        print("Install using this Python interpreter: python -m pip install -r requirements.txt")
        return 2
    command = [sys.executable, "-u", "-m", "pytest"]
    if args.test:
        command.append(args.test)
    if args.collect_only:
        return subprocess.call(command + ["--collect-only", "-q"], cwd=root)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:6]
    run = root / "artifacts" / ("execution_" + run_id)
    run.mkdir(parents=True)
    command += ["-v", "--tb=short", "--driver-debug", "--wait-seconds", str(args.wait_seconds),
                "--artifacts-dir", str(run / "scenarios"), "--junitxml", str(run / "junit.xml")]
    if args.headless:
        command.append("--headless")
    for option, value in (("--driver-path", args.driver_path), ("--chrome-binary", args.chrome_binary)):
        if value:
            command += [option, value]
    # Preserve the exact source used in this run, alongside the resulting evidence.
    source_files = [root / name for name in ("conftest.py", "pytest.ini", "requirements.txt", "run_tests.py")]
    source_files += sorted((root / "cart_tests").glob("*.py"))
    source_files += sorted((root / "tests").glob("*.py"))
    hashes = {}
    for source in source_files:
        rel = source.relative_to(root)
        target = run / "source_snapshot" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(rel)] = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = {"started_utc": datetime.now(timezone.utc).isoformat(),
                "platform": platform.platform(), "python": sys.version,
                "command": command, "source_sha256": hashes}
    (run / "execution.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    print("Running real website tests. Evidence folder:", run, flush=True)
    code = 2
    with (run / "console.log").open("w", encoding="utf-8") as log:
        log.write("Command: " + json.dumps(command) + "\n")
        process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        try:
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            code = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.write("\nInterrupted by user; some scenarios may be incomplete.\n")
            code = 130
    metadata.update(finished_utc=datetime.now(timezone.utc).isoformat(), exit_code=code)
    (run / "execution.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    bundle = run.parent / ("Hanlin_Test_Results_" + run_id + ".zip")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(run.rglob("*")):
            if file.is_file():
                archive.write(file, Path(run.name) / file.relative_to(run))
    print("\nResult bundle:", bundle)
    print("pytest exit code:", code, "(0 means the selected tests passed; inspect summary and warnings.)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
