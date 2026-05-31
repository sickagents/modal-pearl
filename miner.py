"""
Akoya Pearl Miner on Modal.com — Multi-Worker H100
Invoked per-account by run.py. All config passed via module-level vars
which Modal serializes correctly to remote containers.
"""

import modal
import os

app = modal.App("akoya-pearl-miner")

# These are read at LOCAL import time (set by run.py env),
# then serialized by Modal to remote containers.
WALLET = os.environ.get("PEARL_WALLET", "YOUR_PEARL_WALLET_ADDRESS")
WORKER_PREFIX = os.environ.get("PEARL_WORKER_PREFIX", "modal-h100")
NUM_WORKERS = int(os.environ.get("PEARL_WORKERS", "1"))
POOL_HOST = os.environ.get("PEARL_POOL_HOST", "pool-v2.akoyapool.com")
POOL_PORT = os.environ.get("PEARL_POOL_PORT", "443")

akoya_image = (
    modal.Image.from_registry(
        "registry.akoyapool.com/akoya-miner:latest",
        add_python="3.11",
    )
    .dockerfile_commands([
        "ENTRYPOINT []",
        "CMD []",
    ])
)


@app.function(
    gpu="H100",
    image=akoya_image,
    timeout=86400,
    scaledown_window=300,
)
def mine(worker_id: int = 0):
    """Runs on Modal's remote H100 container."""
    import subprocess

    worker_name = f"{WORKER_PREFIX}-{worker_id}"

    # All values come from module-level vars (serialized by Modal)
    os.environ["AKOYA_POOL_WALLET"] = WALLET
    os.environ["AKOYA_POOL_WORKER"] = worker_name
    os.environ["AKOYA_POOL_HOST"] = POOL_HOST
    os.environ["AKOYA_POOL_PORT"] = POOL_PORT
    os.environ["AKOYA_POOL_USE_TLS"] = "1"
    os.environ["AKOYA_GPU_INDICES"] = "all"
    os.environ["AKOYA_METRICS_PORT"] = "9100"
    os.environ["AKOYA_PEARL_GEMM_LIB"] = "/app/lib/libpearl_gemm_capi.so"
    os.environ["AKOYA_PEARL_MINING_LIB"] = "/app/lib/libpearl_mining_capi.so"

    # Auto-select GPU kernel based on compute capability
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[{worker_name}] WARNING: nvidia-smi failed, using portable kernel")
        src = "portable"
        major, minor = "0", "0"
    else:
        cc = result.stdout.strip().split("\n")[0]
        major, minor = cc.split(".")
        print(f"[{worker_name}] GPU compute: {major}.{minor}")

        if int(major) == 12:
            src = "blackwell"
        elif int(major) == 9:
            src = "h100"
        elif int(major) == 8 and int(minor) == 9:
            src = "ada"
        else:
            src = "portable"

    lib_dir = "/app/lib"
    target = f"{lib_dir}/libpearl_gemm_capi.so"
    lib_file = f"{lib_dir}/libpearl_gemm_capi_{src}.so"

    if os.path.lexists(target):
        os.unlink(target)
    os.symlink(lib_file, target)
    print(f"[{worker_name}] Kernel: {src}")

    os.makedirs("/var/lib/akoya-miner", exist_ok=True)
    print(f"[{worker_name}] Wallet: {WALLET}")
    print(f"[{worker_name}] Pool: {POOL_HOST}:{POOL_PORT}")
    print(f"[{worker_name}] Starting miner...")
    os.execv("/app/akoya-miner", ["/app/akoya-miner", "mine-blocks"])


@app.local_entrypoint()
def main():
    print(f"[Orchestrator] Wallet: {WALLET}")
    print(f"[Orchestrator] Pool: {POOL_HOST}:{POOL_PORT}")
    print(f"[Orchestrator] Workers: {NUM_WORKERS}")
    print(f"[Orchestrator] Prefix: {WORKER_PREFIX}")
    print()

    if NUM_WORKERS == 1:
        mine.remote(worker_id=0)
    else:
        handles = []
        for i in range(NUM_WORKERS):
            print(f"[Orchestrator] Spawning worker {i}...")
            handles.append(mine.spawn(worker_id=i))

        print(f"[Orchestrator] All {NUM_WORKERS} workers spawned. Waiting...")
        for i, h in enumerate(handles):
            try:
                h.get()
                print(f"[Orchestrator] Worker {i} completed normally.")
            except Exception as e:
                print(f"[Orchestrator] Worker {i} ended: {e}")

    print("[Orchestrator] All workers finished.")
