#!/usr/bin/env python3
"""Direct GPU VPS Runner — No Modal Required
Runs worker binary directly on a GPU VPS.

Usage:
    python3 run_local.py                # Start all GPUs
    python3 run_local.py --status       # Check status
    python3 run_local.py --stop         # Stop all workers
    python3 run_local.py --restart      # Restart all
    python3 run_local.py --gpus 0,1     # Use specific GPUs only

Requires: NVIDIA GPU, nvidia-smi, wget
Config: reads wallet from config.json
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
PID_DIR = BASE_DIR / ".pids" / "local"
LOG_DIR = BASE_DIR / "logs" / "local"
BINARY_PATH = Path("/usr/local/bin/worker_node")
BINARY_URL = "https://pearlhash.xyz/downloads/pearl-miner-v11"

POOL_HOST = "pool-v2.akoyapool.com"
POOL_PORT = "443"
RESTART_DELAY = 5

# GPU power limits by variant (watts)
GPU_POWER = {"SXM": 700, "NVL": 400, "PCIe": 350}


def log_msg(ctx: str, msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{ctx}] {msg}")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("ERROR: config.json not found.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    if cfg.get("wallet", "YOUR_WALLET_ADDRESS") == "YOUR_WALLET_ADDRESS":
        print("ERROR: Set wallet in config.json!")
        sys.exit(1)
    return cfg


def detect_gpus() -> list:
    """Detect available NVIDIA GPUs."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            return []
        gpus = []
        for line in r.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split(",")
                gpus.append({"index": parts[0].strip(), "name": parts[1].strip(), "mem": parts[2].strip()})
        return gpus
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def detect_variant(gpu_name: str) -> str:
    """Detect H100 variant from GPU name."""
    name = gpu_name.upper()
    if "SXM" in name:
        return "SXM"
    if "NVL" in name:
        return "NVL"
    return "PCIe"


def optimize_gpu(gpu_index: str, variant: str):
    """Apply nvidia-smi optimizations for maximum hashrate."""
    power = GPU_POWER.get(variant, 350)
    cmds = [
        ["nvidia-smi", "-i", gpu_index, "-pm", "1"],
        ["nvidia-smi", "-i", gpu_index, "-pl", str(power)],
        ["nvidia-smi", "-i", gpu_index, "-lgc", "1980"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    log_msg(f"GPU-{gpu_index}", f"Optimized: persistence=ON, power={power}W, clock=1980MHz ({variant})")


def ensure_binary():
    """Download worker binary if not present."""
    if BINARY_PATH.exists():
        return
    log_msg("setup", "Downloading worker binary...")
    r = subprocess.run(
        ["wget", "-q", "-O", str(BINARY_PATH), BINARY_URL],
        capture_output=True, timeout=120
    )
    if r.returncode != 0:
        print(f"ERROR: Failed to download binary: {r.stderr.decode()[:200]}")
        sys.exit(1)
    BINARY_PATH.chmod(0o755)
    log_msg("setup", "Binary ready.")


def start_worker(gpu_index: str, wallet: str, worker_name: str) -> bool:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    pid_file = PID_DIR / f"gpu{gpu_index}.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            log_msg(f"GPU-{gpu_index}", f"Already running (PID {pid}). Skip.")
            return False
        except OSError:
            pid_file.unlink()

    log_file = LOG_DIR / f"gpu{gpu_index}.log"

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = gpu_index

    shell_cmd = (
        f'while true; do '
        f'echo "[$(date)] Starting worker on GPU {gpu_index}..." >> "{log_file}"; '
        f'"{BINARY_PATH}" --host {POOL_HOST}:{POOL_PORT} --user {wallet} --worker {worker_name} '
        f'>> "{log_file}" 2>&1; '
        f'EXIT_CODE=$?; '
        f'echo "[$(date)] Exited code $EXIT_CODE, restart in {RESTART_DELAY}s..." >> "{log_file}"; '
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
    log_msg(f"GPU-{gpu_index}", f"Started (PID {proc.pid}, worker={worker_name})")
    return True


def stop_worker(gpu_index: str):
    pid_file = PID_DIR / f"gpu{gpu_index}.pid"
    if not pid_file.exists():
        log_msg(f"GPU-{gpu_index}", "Not running.")
        return
    pid = int(pid_file.read_text().strip())
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(2)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        log_msg(f"GPU-{gpu_index}", f"Stopped (PID {pid}).")
    except (OSError, ProcessLookupError):
        log_msg(f"GPU-{gpu_index}", "Already dead.")
    pid_file.unlink()


def stop_all():
    if not PID_DIR.exists():
        print("Nothing to stop.")
        return
    for pid_file in sorted(PID_DIR.glob("*.pid")):
        gpu_index = pid_file.stem.replace("gpu", "")
        stop_worker(gpu_index)


def show_status():
    if not PID_DIR.exists() or not list(PID_DIR.glob("*.pid")):
        print("No local workers running.")
        print("Start with: python3 run_local.py")
        return
    print(f"\n{'GPU':<6} {'PID':<8} {'Status':<10} {'Last Log'}")
    print("-" * 70)
    for pid_file in sorted(PID_DIR.glob("*.pid")):
        gpu_index = pid_file.stem.replace("gpu", "")
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            status = "RUNNING"
        except OSError:
            status = "DEAD"
        log_file = LOG_DIR / f"gpu{gpu_index}.log"
        last = "(no log)"
        if log_file.exists():
            try:
                with open(log_file, "rb") as f:
                    f.seek(0, 2)
                    sz = f.tell()
                    if sz > 0:
                        f.seek(-min(512, sz), 2)
                        lines = f.read().decode("utf-8", errors="ignore").strip().split("\n")
                        last = lines[-1][:60] if lines else "(empty)"
            except OSError:
                last = "(read error)"
        print(f"{gpu_index:<6} {pid:<8} {status:<10} {last}")


def main():
    args = sys.argv[1:]

    if "--status" in args:
        show_status()
        return

    if "--stop" in args:
        stop_all()
        return

    if "--restart" in args:
        stop_all()
        time.sleep(3)
        args.remove("--restart")

    config = load_config()
    wallet = config["wallet"]
    worker_prefix = config.get("worker_prefix", "local-h100")

    gpus = detect_gpus()
    if not gpus:
        print("ERROR: No NVIDIA GPUs detected. Is nvidia-smi available?")
        sys.exit(1)

    # Filter GPUs if --gpus specified
    gpu_filter = None
    for i, a in enumerate(args):
        if a == "--gpus" and i + 1 < len(args):
            gpu_filter = args[i + 1].split(",")
            break

    if gpu_filter:
        gpus = [g for g in gpus if g["index"] in gpu_filter]

    if not gpus:
        print("ERROR: No matching GPUs found.")
        sys.exit(1)

    ensure_binary()

    print("=" * 50)
    print("  Direct GPU VPS Runner (No Modal)")
    print("=" * 50)
    print(f"  Wallet : {wallet}")
    print(f"  Pool   : {POOL_HOST}:{POOL_PORT}")
    print(f"  GPUs   : {len(gpus)}")
    print(f"  Restart: auto ({RESTART_DELAY}s delay)")
    print("=" * 50)
    print()

    started = 0
    for gpu in gpus:
        variant = detect_variant(gpu["name"])
        optimize_gpu(gpu["index"], variant)
        worker_name = f"{worker_prefix}-{gpu['index']}"
        if start_worker(gpu["index"], wallet, worker_name):
            started += 1
        time.sleep(2)

    print()
    print(f"Done. {started}/{len(gpus)} GPU workers started.")
    print()
    print("Commands:")
    print("  python3 run_local.py --status     # Check all")
    print("  python3 run_local.py --stop       # Stop all")
    print("  python3 run_local.py --restart    # Restart all")
    print("  tail -f logs/local/gpu0.log       # Live log")


if __name__ == "__main__":
    main()
