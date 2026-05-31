#!/usr/bin/env python3
"""
Modal Pearl Multi-Account Runner
Reads config.json and runs miner.py for each account.

Usage:
    python run.py                  # Run all accounts
    python run.py acc1             # Run specific account
    python run.py acc1 acc3        # Run multiple specific accounts
    python run.py --status         # Check status of running miners
    python run.py --stop           # Stop all miners
    python run.py --stop acc1      # Stop specific account
"""

import json
import subprocess
import sys
import os
import signal
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
PID_DIR = BASE_DIR / ".pids"
LOG_DIR = BASE_DIR / "logs"

AUTO_WORKERS = 5  # "auto" spawns this many; Modal limits by quota


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_modal_toml_path(account_name: str) -> Path:
    toml_dir = BASE_DIR / ".tokens"
    toml_dir.mkdir(exist_ok=True)
    return toml_dir / f"{account_name}.toml"


def write_modal_toml(account: dict) -> Path:
    path = get_modal_toml_path(account["name"])
    path.write_text(
        f'[default]\ntoken_id = "{account["token_id"]}"\ntoken_secret = "{account["token_secret"]}"\n'
    )
    path.chmod(0o600)
    return path


def resolve_workers(workers_value) -> int:
    if workers_value == "auto":
        return AUTO_WORKERS
    return int(workers_value)


def start_account(account: dict, config: dict):
    name = account["name"]
    workers = resolve_workers(account.get("workers", "auto"))

    PID_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    # Check if already running
    pid_file = PID_DIR / f"{name}.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            print(f"[{name}] Already running (PID {pid}). Skip.")
            return
        except OSError:
            pid_file.unlink()

    # Write token file
    toml_path = write_modal_toml(account)

    # Environment for this account
    env = os.environ.copy()
    env["MODAL_CONFIG_PATH"] = str(toml_path)
    env["PEARL_WALLET"] = config["wallet"]
    env["PEARL_WORKER_PREFIX"] = f"{name}-h100"
    env["PEARL_WORKERS"] = str(workers)
    env["PEARL_POOL_HOST"] = config.get("pool_host", "pool-v2.akoyapool.com")
    env["PEARL_POOL_PORT"] = config.get("pool_port", "443")

    # Start miner process
    log_file = LOG_DIR / f"{name}.log"
    log_fd = open(log_file, "a")

    proc = subprocess.Popen(
        [sys.executable, "-m", "modal", "run", str(BASE_DIR / "miner.py")],
        env=env,
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    pid_file.write_text(str(proc.pid))
    print(f"[{name}] Started (PID {proc.pid}, workers={workers}, log={log_file})")


def stop_account(name: str):
    pid_file = PID_DIR / f"{name}.pid"
    if not pid_file.exists():
        print(f"[{name}] Not running.")
        return

    pid = int(pid_file.read_text().strip())
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        print(f"[{name}] Stopped (PID {pid}).")
    except (OSError, ProcessLookupError):
        print(f"[{name}] Process already dead.")
    pid_file.unlink()


def show_status():
    if not PID_DIR.exists():
        print("No miners running.")
        return

    print(f"{'Account':<12} {'PID':<8} {'Status':<10} {'Log'}")
    print("-" * 60)

    for pid_file in sorted(PID_DIR.glob("*.pid")):
        name = pid_file.stem
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            status = "RUNNING"
        except OSError:
            status = "DEAD"

        log_file = LOG_DIR / f"{name}.log"
        last_line = ""
        if log_file.exists():
            lines = log_file.read_text().strip().split("\n")
            last_line = lines[-1][:50] if lines else ""

        print(f"{name:<12} {pid:<8} {status:<10} {last_line}")


def stop_all():
    if not PID_DIR.exists():
        print("No miners to stop.")
        return
    for pid_file in sorted(PID_DIR.glob("*.pid")):
        stop_account(pid_file.stem)


def main():
    args = sys.argv[1:]

    if "--status" in args:
        show_status()
        return

    if "--stop" in args:
        args.remove("--stop")
        if args:
            for name in args:
                stop_account(name)
        else:
            stop_all()
        return

    config = load_config()

    if config["wallet"] == "YOUR_PEARL_WALLET_ADDRESS":
        print("ERROR: Set your wallet address in config.json first!")
        sys.exit(1)

    # Filter accounts if specified
    if args:
        accounts = [a for a in config["accounts"] if a["name"] in args]
        not_found = set(args) - {a["name"] for a in accounts}
        if not_found:
            print(f"ERROR: Accounts not found in config: {not_found}")
            sys.exit(1)
    else:
        accounts = config["accounts"]

    print(f"Wallet: {config['wallet']}")
    print(f"Pool: {config.get('pool_host', 'pool-v2.akoyapool.com')}")
    print(f"Accounts: {len(accounts)}")
    print()

    for i, account in enumerate(accounts):
        start_account(account, config)
        if i < len(accounts) - 1:
            time.sleep(10)  # Stagger to avoid rate limits

    print()
    print("All accounts started. Use 'python run.py --status' to monitor.")


if __name__ == "__main__":
    main()
