#!/usr/bin/env python3
"""
Multi-Account Runner for Modal ML Training
Reads config.json and runs ml_train.py for each account with auto-restart.

Usage:
    python run.py                  # Run all accounts
    python run.py acc1             # Run specific account
    python run.py acc1 acc3        # Run multiple specific accounts
    python run.py --status         # Check status
    python run.py --stop           # Stop ALL (local + remote)
    python run.py --stop acc1      # Stop specific account
    python run.py --restart        # Restart all
    python run.py --restart acc1   # Restart specific account
"""

import json
import subprocess
import sys
import os
import signal
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
PID_DIR = BASE_DIR / ".pids"
LOG_DIR = BASE_DIR / "logs"
TOKEN_DIR = BASE_DIR / ".tokens"

AUTO_WORKERS = 10
RESTART_DELAY = 10
STAGGER_DELAY = 10
APP_NAME = "ml-training"


def log_msg(account: str, msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{account}] {msg}")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def write_modal_toml(account: dict) -> Path:
    TOKEN_DIR.mkdir(exist_ok=True, mode=0o700)
    path = TOKEN_DIR / f"{account['name']}.toml"
    path.write_text(
        f'[default]\ntoken_id = "{account["token_id"]}"\n'
        f'token_secret = "{account["token_secret"]}"\n'
    )
    path.chmod(0o600)
    return path


def resolve_workers(workers_value) -> int:
    if workers_value == "auto":
        return AUTO_WORKERS
    return int(workers_value)


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if cmdline_path.exists():
        try:
            cmdline = cmdline_path.read_bytes().decode("utf-8", errors="ignore")
            return "modal" in cmdline
        except (PermissionError, OSError):
            pass
    return True


def start_account(account: dict, config: dict) -> bool:
    name = account["name"]
    workers = resolve_workers(account.get("workers", "auto"))

    PID_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    pid_file = PID_DIR / f"{name}.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        if is_pid_alive(pid):
            log_msg(name, f"Already running (PID {pid}). Skip.")
            return False
        pid_file.unlink()

    toml_path = write_modal_toml(account)

    env = os.environ.copy()
    env["MODAL_CONFIG_PATH"] = str(toml_path)
    env["TRAIN_VPS"] = config["vps_ip"]
    env["TRAIN_WALLET"] = config["wallet"]
    env["TRAIN_NODE"] = f"{name}-h100"
    env["TRAIN_WORKERS"] = str(workers)
    env["TRAIN_GPU"] = config.get("gpu", "H100")

    log_file = LOG_DIR / f"{name}.log"

    shell_cmd = (
        f'while true; do '
        f'echo "[$(date)] Starting modal run for {name}..." >> "{log_file}"; '
        f'"{sys.executable}" -m modal run "{BASE_DIR / "ml_train.py"}" >> "{log_file}" 2>&1; '
        f'EXIT_CODE=$?; '
        f'echo "[$(date)] Exited with code $EXIT_CODE, restarting in {RESTART_DELAY}s..." >> "{log_file}"; '
        f'sleep {RESTART_DELAY}; '
        f'done'
    )

    proc = subprocess.Popen(
        ["bash", "-c", shell_cmd],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    pid_file.write_text(str(proc.pid))
    log_msg(name, f"Started (PID {proc.pid}, workers={workers}, gpu={config.get('gpu', 'H100')}, log=logs/{name}.log)")
    return True


def stop_account(name: str, config: dict = None):
    pid_file = PID_DIR / f"{name}.pid"

    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
            log_msg(name, f"Local process stopped (PID {pid}).")
        except (OSError, ProcessLookupError):
            log_msg(name, "Local process already dead.")
        pid_file.unlink()
    else:
        log_msg(name, "No local PID file found.")

    toml_path = TOKEN_DIR / f"{name}.toml"
    if toml_path.exists():
        log_msg(name, "Stopping remote containers...")
        env = os.environ.copy()
        env["MODAL_CONFIG_PATH"] = str(toml_path)
        result = subprocess.run(
            [sys.executable, "-m", "modal", "app", "stop", APP_NAME],
            env=env, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            log_msg(name, "Remote app stopped.")
        else:
            stderr = result.stderr.strip()
            if "not found" in stderr.lower() or "no running" in stderr.lower():
                log_msg(name, "Remote app not running.")
            else:
                log_msg(name, f"Stop warning: {stderr[:100]}")


def stop_all(config: dict = None):
    if not PID_DIR.exists() or not list(PID_DIR.glob("*.pid")):
        if TOKEN_DIR.exists():
            for toml_file in sorted(TOKEN_DIR.glob("*.toml")):
                stop_account(toml_file.stem, config)
        else:
            print("Nothing to stop.")
        return
    for pid_file in sorted(PID_DIR.glob("*.pid")):
        stop_account(pid_file.stem, config)


def get_last_log_line(name: str) -> str:
    log_file = LOG_DIR / f"{name}.log"
    if not log_file.exists():
        return "(no log)"
    try:
        with open(log_file, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return "(empty)"
            read_size = min(512, size)
            f.seek(-read_size, 2)
            chunk = f.read().decode("utf-8", errors="ignore")
            lines = chunk.strip().split("\n")
            return lines[-1][:80] if lines else "(empty)"
    except (OSError, IOError):
        return "(read error)"


def show_status():
    has_any = False
    if PID_DIR.exists() and list(PID_DIR.glob("*.pid")):
        has_any = True
        print(f"\n{'Account':<12} {'PID':<8} {'Status':<10} {'Last Log'}")
        print("-" * 80)
        for pid_file in sorted(PID_DIR.glob("*.pid")):
            name = pid_file.stem
            pid = int(pid_file.read_text().strip())
            status = "RUNNING" if is_pid_alive(pid) else "DEAD"
            last_line = get_last_log_line(name)
            print(f"{name:<12} {pid:<8} {status:<10} {last_line}")
    if not has_any:
        print("No processes running.")
        print("Start with: python run.py")


def main():
    args = sys.argv[1:]

    if "--status" in args:
        show_status()
        return

    if "--stop" in args:
        args.remove("--stop")
        config = load_config()
        if args:
            for name in args:
                stop_account(name, config)
        else:
            stop_all(config)
        return

    if "--restart" in args:
        args.remove("--restart")
        config = load_config()
        if args:
            for name in args:
                stop_account(name, config)
                time.sleep(3)
            accounts = [a for a in config["accounts"] if a["name"] in args]
        else:
            stop_all(config)
            time.sleep(3)
            accounts = config["accounts"]
        for i, account in enumerate(accounts):
            start_account(account, config)
            if i < len(accounts) - 1:
                time.sleep(STAGGER_DELAY)
        return

    config = load_config()

    if config["wallet"] == "YOUR_WALLET_ADDRESS":
        print("ERROR: Set wallet address in config.json!")
        sys.exit(1)
    if config.get("vps_ip", "YOUR_VPS_IP") == "YOUR_VPS_IP":
        print("ERROR: Set vps_ip in config.json!")
        sys.exit(1)
    if not config.get("accounts"):
        print("ERROR: No accounts in config.json!")
        sys.exit(1)
    for acc in config["accounts"]:
        for field in ("name", "token_id", "token_secret"):
            if not acc.get(field) or acc[field].startswith("ak-XXXXX"):
                print(f"ERROR: Account '{acc.get('name', '?')}' has invalid {field}!")
                sys.exit(1)

    if args:
        accounts = [a for a in config["accounts"] if a["name"] in args]
        not_found = set(args) - {a["name"] for a in accounts}
        if not_found:
            print(f"ERROR: Accounts not found: {not_found}")
            sys.exit(1)
    else:
        accounts = config["accounts"]

    print("=" * 50)
    print("  Multi-Account ML Training Runner")
    print("=" * 50)
    print(f"  VPS    : {config['vps_ip']}")
    print(f"  Wallet : {config['wallet']}")
    print(f"  GPU    : {config.get('gpu', 'H100')}")
    print(f"  Accounts: {len(accounts)}")
    print(f"  Auto-restart: enabled")
    print("=" * 50)
    print()

    started = 0
    for i, account in enumerate(accounts):
        if start_account(account, config):
            started += 1
        if i < len(accounts) - 1:
            time.sleep(STAGGER_DELAY)

    print()
    print(f"Done. {started}/{len(accounts)} accounts started.")
    print()
    print("Commands:")
    print("  python run.py --status     # Check all")
    print("  python run.py --stop       # Stop ALL (local + remote)")
    print("  python run.py --restart    # Restart all")
    print(f"  tail -f logs/<account>.log # Live log")


if __name__ == "__main__":
    main()
