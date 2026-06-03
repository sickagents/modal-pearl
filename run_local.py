#!/usr/bin/env python3
"""Akoya Pearl Miner — Direct GPU VPS Runner (No Modal)
Supports NVIDIA (Docker) and AMD MI300X (from-source build).

Usage:
    python3 run_local.py                # Start all GPUs
    python3 run_local.py --status       # Check status
    python3 run_local.py --stop         # Stop all workers
    python3 run_local.py --restart      # Restart all
    python3 run_local.py --gpus 0,1     # Use specific GPUs only
    python3 run_local.py --backend amd  # Force AMD (skip Docker)

Requires: NVIDIA GPU + Docker OR AMD GPU + ROCm + built binary
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

# Paths for from-source build (AMD)
BINARY_PATH = Path("/opt/akoya-miner/out/akoya-miner")

# Docker image for NVIDIA
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


def detect_amd_gpus() -> list:
    """Detect available AMD GPUs via ROCm."""
    try:
        r = subprocess.run(
            ["rocm-smi", "--showid", "--csv"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            # Fallback: check /dev/kfd
            if Path("/dev/kfd").exists():
                return [{"index": "0", "name": "AMD GPU", "mem": "unknown"}]
            return []
        gpus = []
        for line in r.stdout.strip().split("\n")[1:]:  # skip header
            if line.strip():
                parts = line.split(",")
                if len(parts) >= 1:
                    gpus.append({"index": parts[0].strip(), "name": "AMD GPU", "mem": "unknown"})
        return gpus
    except (FileNotFoundError, subprocess.TimeoutExpired):
        if Path("/dev/kfd").exists():
            return [{"index": "0", "name": "AMD GPU", "mem": "unknown"}]
        return []


def detect_backend(force_backend=None) -> str:
    """Auto-detect GPU backend: nvidia (Docker) or amd (binary)."""
    if force_backend:
        return force_backend

    # Check NVIDIA first
    try:
        r = subprocess.run(["nvidia-smi"], capture_output=True, timeout=10)
        if r.returncode == 0:
            return "nvidia"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check AMD
    if BINARY_PATH.exists():
        return "amd"
    if Path("/dev/kfd").exists():
        return "amd"

    return "unknown"


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
    r = subprocess.run(["docker", "pull", DOCKER_IMAGE], timeout=300)
    if r.returncode != 0:
        print("ERROR: Failed to pull Docker image.")
        sys.exit(1)
    log_msg("setup", "Image ready.")


def ensure_binary():
    """Check that the built binary exists."""
    if not BINARY_PATH.exists():
        print(f"ERROR: Binary not found at {BINARY_PATH}")
        print("Run: bash setup_vps_amd.sh")
        sys.exit(1)
    log_msg("setup", f"Binary found: {BINARY_PATH}")


# ---- NVIDIA (Docker) ----

def start_worker_nvidia(gpu_index: str, wallet: str, worker_name: str, proxy: str = "") -> bool:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    container_name = f"{CONTAINER_NAME_PREFIX}-gpu{gpu_index}"
    pid_file = PID_DIR / f"gpu{gpu_index}.pid"

    r = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={container_name}"],
        capture_output=True, text=True, timeout=10
    )
    if r.stdout.strip():
        log_msg(f"GPU-{gpu_index}", f"Container {container_name} already running. Skip.")
        return False

    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)

    log_file = LOG_DIR / f"gpu{gpu_index}.log"

    docker_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--gpus", f"device={gpu_index}",
        "--restart", "unless-stopped",
    ]

    env_vars = {
        "AKOYA_POOL_WALLET":    wallet,
        "AKOYA_POOL_WORKER":    worker_name,
        "AKOYA_POOL_HOST":      POOL_HOST,
        "AKOYA_POOL_PORT":      POOL_PORT,
        "AKOYA_POOL_USE_TLS":   "1",
        "AKOYA_GPU_INDICES":    "all",
        "AKOYA_METRICS_PORT":   "9100",
    }

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
        log_msg(f"GPU-{gpu_index}", f"Failed: {proc.stderr[:200]}")
        return False

    pid_file.write_text(proc.stdout.strip()[:12])
    log_msg(f"GPU-{gpu_index}", f"Started container={container_name}, worker={worker_name}")

    subprocess.Popen(
        ["bash", "-c", f"docker logs -f {container_name} >> {log_file} 2>&1"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


# ---- AMD (from-source binary) ----

def start_worker_amd(gpu_index: str, wallet: str, worker_name: str, proxy: str = "") -> bool:
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
    env.update({
        "AKOYA_POOL_WALLET":    wallet,
        "AKOYA_POOL_WORKER":    worker_name,
        "AKOYA_POOL_HOST":      POOL_HOST,
        "AKOYA_POOL_PORT":      POOL_PORT,
        "AKOYA_POOL_TLS":       "true",
        "AKOYA_GPU_INDICES":    gpu_index,
        "ROCR_VISIBLE_DEVICES": gpu_index,
        "HIP_VISIBLE_DEVICES":  gpu_index,
    })

    if proxy:
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy

    shell_cmd = (
        f'while true; do '
        f'echo "[$(date)] Starting akoya-miner on GPU {gpu_index}..." >> "{log_file}"; '
        f'"{BINARY_PATH}" >> "{log_file}" 2>&1; '
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
    log_msg(f"GPU-{gpu_index}", f"Started PID={proc.pid}, worker={worker_name}, binary={BINARY_PATH}")
    return True


def stop_all(backend="nvidia"):
    if backend == "nvidia":
        r = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={CONTAINER_NAME_PREFIX}"],
            capture_output=True, text=True, timeout=10
        )
        if r.stdout.strip():
            for cid in r.stdout.strip().split("\n"):
                cid = cid.strip()
                if cid:
                    subprocess.run(["docker", "stop", "-t", "5", cid], capture_output=True, timeout=15)
                    subprocess.run(["docker", "rm", "-f", cid], capture_output=True, timeout=10)
            print("All Docker containers stopped.")
        else:
            print("No akoya containers running.")
    else:
        # AMD: kill by PID
        if not PID_DIR.exists() or not list(PID_DIR.glob("*.pid")):
            print("No local workers running.")
            return
        for pid_file in sorted(PID_DIR.glob("*.pid")):
            pid = int(pid_file.read_text().strip())
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(2)
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                print(f"Stopped PID {pid}.")
            except (OSError, ProcessLookupError):
                print(f"PID {pid} already dead.")
            pid_file.unlink()

    # Clean PID files
    if PID_DIR.exists():
        for f in PID_DIR.glob("*.pid"):
            f.unlink()


def show_status():
    # Docker containers
    r = subprocess.run(
        ["docker", "ps", "-a", "-f", f"name={CONTAINER_NAME_PREFIX}",
         "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
        capture_output=True, text=True, timeout=10
    )
    if r.stdout.strip():
        print("[Docker]")
        print(r.stdout)

    # PID-based workers
    if PID_DIR.exists() and list(PID_DIR.glob("*.pid")):
        print("\n[Local Workers]")
        print(f"{'GPU':<8} {'PID':<10} {'Status'}")
        print("-" * 30)
        for pid_file in sorted(PID_DIR.glob("*.pid")):
            gpu = pid_file.stem.replace("gpu", "")
            pid = int(pid_file.read_text().strip())
            try:
                os.kill(pid, 0)
                status = "RUNNING"
            except OSError:
                status = "DEAD"
            print(f"{gpu:<8} {pid:<10} {status}")

    if not r.stdout.strip() and (not PID_DIR.exists() or not list(PID_DIR.glob("*.pid"))):
        print("No workers running.")


def main():
    args = sys.argv[1:]

    # Parse --backend
    force_backend = None
    for i, a in enumerate(args):
        if a == "--backend" and i + 1 < len(args):
            force_backend = args[i + 1]
            args.pop(i + 1)
            args.pop(i)
            break

    if "--status" in args:
        show_status()
        return

    if "--stop" in args:
        backend = detect_backend(force_backend)
        stop_all(backend)
        return

    if "--restart" in args:
        backend = detect_backend(force_backend)
        stop_all(backend)
        time.sleep(3)
        args.remove("--restart")

    config = load_config()
    wallet = config["wallet"]
    worker_prefix = config.get("worker_prefix", "rig")
    proxy = config.get("proxy", "")

    backend = detect_backend(force_backend)

    if backend == "nvidia":
        gpus = detect_gpus()
        if not gpus:
            print("ERROR: No NVIDIA GPUs detected.")
            sys.exit(1)
    elif backend == "amd":
        gpus = detect_amd_gpus()
        ensure_binary()
        if not gpus:
            print("ERROR: No AMD GPUs detected.")
            sys.exit(1)
    else:
        print("ERROR: No GPU backend detected.")
        print("NVIDIA: install Docker + nvidia-container-toolkit")
        print("AMD:    run setup_vps_amd.sh")
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

    if backend == "nvidia":
        ensure_image()

    print("=" * 50)
    print(f"  Akoya Pearl Miner (Direct VPS — {backend.upper()})")
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
        worker_name = f"{worker_prefix}-{gpu['index']}-{rand_suffix()}"

        if backend == "nvidia":
            variant = detect_variant(gpu["name"])
            optimize_gpu(gpu["index"], variant)
            ok = start_worker_nvidia(gpu["index"], wallet, worker_name, proxy)
        else:
            ok = start_worker_amd(gpu["index"], wallet, worker_name, proxy)

        if ok:
            started += 1
        time.sleep(2)

    print()
    print(f"Done. {started}/{len(gpus)} GPU workers started.")
    print()
    print("Commands:")
    print("  python3 run_local.py --status     # Check all")
    print("  python3 run_local.py --stop       # Stop all")
    print("  python3 run_local.py --restart    # Restart all")
    if backend == "nvidia":
        print("  docker logs -f akoya-gpu0         # Live log GPU 0")
    else:
        print("  tail -f logs/local/gpu0.log       # Live log GPU 0")


if __name__ == "__main__":
    main()
