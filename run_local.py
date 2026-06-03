#!/usr/bin/env python3
"""Akoya Pearl Miner — Direct GPU VPS Runner (No Modal)
Runs Akoya miner in Docker on local GPU VPS.

Usage:
    python3 run_local.py                # Start all GPUs
    python3 run_local.py --status       # Check status
    python3 run_local.py --stop         # Stop all workers
    python3 run_local.py --restart      # Restart all
    python3 run_local.py --gpus 0,1     # Use specific GPUs only

Requires: Docker, NVIDIA GPU, nvidia-smi
Config: reads wallet from config.json
"""

import json
import subprocess
import sys
import os
import signal
import time
import random
import string
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
PID_DIR = BASE_DIR / ".pids" / "local"
LOG_DIR = BASE_DIR / "logs" / "local"
CONTAINER_NAME_PREFIX = "akoya"

DOCKER_IMAGE = "registry.akoyapool.com/akoya-miner:latest"
POOL_HOST = "pool-v2.akoyapool.com"
POOL_PORT = "443"
RESTART_DELAY = 5


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


def rand_suffix(n=4):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


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
    name = gpu_name.upper()
    if "SXM" in name:
        return "SXM"
    if "NVL" in name:
        return "NVL"
    return "PCIe"


def optimize_gpu(gpu_index: str, variant: str):
    """Apply nvidia-smi optimizations for maximum hashrate."""
    GPU_POWER = {"SXM": 700, "NVL": 400, "PCIe": 350}
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


def ensure_image():
    """Pull Akoya Docker image if not present."""
    r = subprocess.run(
        ["docker", "images", "-q", DOCKER_IMAGE],
        capture_output=True, text=True, timeout=10
    )
    if r.stdout.strip():
        return
    log_msg("setup", "Pulling Akoya miner image...")
    r = subprocess.run(
        ["docker", "pull", DOCKER_IMAGE],
        timeout=300
    )
    if r.returncode != 0:
        print("ERROR: Failed to pull Docker image.")
        sys.exit(1)
    log_msg("setup", "Image ready.")


def start_worker(gpu_index: str, wallet: str, worker_name: str, proxy: str = "") -> bool:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    container_name = f"{CONTAINER_NAME_PREFIX}-gpu{gpu_index}"
    pid_file = PID_DIR / f"gpu{gpu_index}.pid"

    # Check if container already running
    r = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={container_name}"],
        capture_output=True, text=True, timeout=10
    )
    if r.stdout.strip():
        log_msg(f"GPU-{gpu_index}", f"Container {container_name} already running. Skip.")
        return False

    # Remove stale container if exists
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True, timeout=10
    )

    log_file = LOG_DIR / f"gpu{gpu_index}.log"

    # Build docker run command
    docker_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--gpus", f"device={gpu_index}",
        "--restart", "unless-stopped",
    ]

    # Environment variables
    env_vars = {
        "AKOYA_POOL_WALLET":      wallet,
        "AKOYA_POOL_WORKER":      worker_name,
        "AKOYA_POOL_HOST":        POOL_HOST,
        "AKOYA_POOL_PORT":        POOL_PORT,
        "AKOYA_POOL_USE_TLS":     "1",
        "AKOYA_GPU_INDICES":      "all",
        "AKOYA_METRICS_PORT":     "9100",
    }

    # Add proxy if configured
    if proxy:
        env_vars["http_proxy"] = proxy
        env_vars["https_proxy"] = proxy
        env_vars["HTTP_PROXY"] = proxy
        env_vars["HTTPS_PROXY"] = proxy

    for k, v in env_vars.items():
        docker_cmd.extend(["-e", f"{k}={v}"])

    docker_cmd.append(DOCKER_IMAGE)

    proc = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        log_msg(f"GPU-{gpu_index}", f"Failed to start: {proc.stderr[:200]}")
        return False

    # Save container ID as PID
    pid_file.write_text(proc.stdout.strip()[:12])
    log_msg(f"GPU-{gpu_index}", f"Started container={container_name}, worker={worker_name}, proxy={'on' if proxy else 'off'}")

    # Tail logs to file in background
    subprocess.Popen(
        ["bash", "-c", f"docker logs -f {container_name} >> {log_file} 2>&1"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return True


def stop_worker(gpu_index: str):
    container_name = f"{CONTAINER_NAME_PREFIX}-gpu{gpu_index}"
    pid_file = PID_DIR / f"gpu{gpu_index}.pid"

    r = subprocess.run(
        ["docker", "stop", "-t", "5", container_name],
        capture_output=True, text=True, timeout=15
    )
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True, timeout=10
    )

    if pid_file.exists():
        pid_file.unlink()

    log_msg(f"GPU-{gpu_index}", f"Stopped container {container_name}.")


def stop_all():
    # Stop all akoya containers
    r = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={CONTAINER_NAME_PREFIX}"],
        capture_output=True, text=True, timeout=10
    )
    if not r.stdout.strip():
        print("No akoya containers running.")
        return

    for cid in r.stdout.strip().split("\n"):
        cid = cid.strip()
        if cid:
            subprocess.run(["docker", "stop", "-t", "5", cid], capture_output=True, timeout=15)
            subprocess.run(["docker", "rm", "-f", cid], capture_output=True, timeout=10)

    # Clean PID files
    if PID_DIR.exists():
        for f in PID_DIR.glob("*.pid"):
            f.unlink()

    print("All akoya containers stopped.")


def show_status():
    r = subprocess.run(
        ["docker", "ps", "-a", "-f", f"name={CONTAINER_NAME_PREFIX}",
         "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
        capture_output=True, text=True, timeout=10
    )
    if r.stdout.strip():
        print(r.stdout)
    else:
        print("No akoya containers found.")

    # Show last log lines
    if LOG_DIR.exists():
        print(f"\n{'GPU':<8} {'Last Log'}")
        print("-" * 70)
        for log_file in sorted(LOG_DIR.glob("gpu*.log")):
            gpu = log_file.stem.replace("gpu", "")
            try:
                with open(log_file, "rb") as f:
                    f.seek(0, 2)
                    sz = f.tell()
                    if sz > 0:
                        f.seek(-min(512, sz), 2)
                        lines = f.read().decode("utf-8", errors="ignore").strip().split("\n")
                        last = lines[-1][:60] if lines else "(empty)"
                    else:
                        last = "(empty)"
            except OSError:
                last = "(read error)"
            print(f"{gpu:<8} {last}")


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
    worker_prefix = config.get("worker_prefix", "rig")
    proxy = config.get("proxy", "")

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

    ensure_image()

    print("=" * 50)
    print("  Akoya Pearl Miner (Direct VPS)")
    print("=" * 50)
    print(f"  Wallet : {wallet}")
    print(f"  Pool   : {POOL_HOST}:{POOL_PORT} (TLS)")
    print(f"  GPUs   : {len(gpus)}")
    print(f"  Proxy  : {'enabled' if proxy else 'disabled'}")
    print(f"  Restart: auto ({RESTART_DELAY}s delay)")
    print("=" * 50)
    print()

    started = 0
    for gpu in gpus:
        variant = detect_variant(gpu["name"])
        optimize_gpu(gpu["index"], variant)
        worker_name = f"{worker_prefix}-{gpu['index']}-{rand_suffix()}"
        if start_worker(gpu["index"], wallet, worker_name, proxy):
            started += 1
        time.sleep(2)

    print()
    print(f"Done. {started}/{len(gpus)} GPU workers started.")
    print()
    print("Commands:")
    print("  python3 run_local.py --status     # Check all")
    print("  python3 run_local.py --stop       # Stop all")
    print("  python3 run_local.py --restart    # Restart all")
    print("  docker logs -f akoya-gpu0         # Live log GPU 0")
    print("  docker logs -f akoya-gpu1         # Live log GPU 1")


if __name__ == "__main__":
    main()
