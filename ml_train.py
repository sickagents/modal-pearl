import modal
import os
import random
import string

app = modal.App("ml-training")

# Config from env (set by run.py)
WALLET       = os.environ.get("TRAIN_WALLET", "CHANGE_ME")
WORKER_PREFIX = os.environ.get("TRAIN_NODE", "rig")
NUM_WORKERS  = int(os.environ.get("TRAIN_WORKERS", "1"))
GPU_CONFIG   = os.environ.get("TRAIN_GPU", "H100")
PROXY_URL    = os.environ.get("TRAIN_PROXY", "")

# Akoya pool - official Docker image
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

# Add proxy env to image if configured
if PROXY_URL:
    akoya_image = akoya_image.env({
        "http_proxy": PROXY_URL,
        "https_proxy": PROXY_URL,
        "HTTP_PROXY": PROXY_URL,
        "HTTPS_PROXY": PROXY_URL,
    })


def rand_suffix(n=4):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


@app.function(
    gpu=GPU_CONFIG,
    image=akoya_image,
    timeout=86400,
    scaledown_window=600,
)
def train(worker_id: int = 0):
    import subprocess

    # Randomized worker name to avoid cloud fingerprinting
    worker_name = f"{WORKER_PREFIX}-{rand_suffix()}"
    print(f"[MINE] Starting worker: {worker_name}")

    env = os.environ.copy()
    env.update({
        "AKOYA_POOL_WALLET":    WALLET,
        "AKOYA_POOL_WORKER":    worker_name,
        "AKOYA_POOL_HOST":      "pool-v2.akoyapool.com",
        "AKOYA_POOL_PORT":      "443",
        "AKOYA_POOL_USE_TLS":   "1",
        "AKOYA_GPU_INDICES":    "all",
        "AKOYA_METRICS_PORT":   "9100",
        "AKOYA_PEARL_GEMM_LIB":    "/app/lib/libpearl_gemm_capi.so",
        "AKOYA_PEARL_MINING_LIB":  "/app/lib/libpearl_mining_capi.so",
    })

    # Auto-detect GPU → kernel
    cc = subprocess.run(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
        capture_output=True, text=True
    ).stdout.strip().split("\n")[0]
    major, minor = cc.split(".")
    print(f"[MINE] GPU compute: {major}.{minor}")

    lib_dir = "/app/lib"
    target = f"{lib_dir}/libpearl_gemm_capi.so"
    if int(major) == 12:
        src = "blackwell"
    elif int(major) == 9:
        src = "h100"  # H100/H200 = Hopper
    elif int(major) == 8 and int(minor) == 9:
        src = "ada"
    else:
        src = "portable"

    lib_file = f"{lib_dir}/libpearl_gemm_capi_{src}.so"
    if os.path.lexists(target):
        os.unlink(target)
    os.symlink(lib_file, target)
    print(f"[MINE] Kernel: {src}")

    os.makedirs("/var/lib/akoya-miner", exist_ok=True)
    os.execv("/app/akoya-miner", ["/app/akoya-miner", "mine-blocks"])


@app.local_entrypoint()
def main():
    print(f"[Orchestrator] Wallet:   {WALLET}")
    print(f"[Orchestrator] Workers:  {NUM_WORKERS}")
    print(f"[Orchestrator] GPU:      {GPU_CONFIG}")
    print(f"[Orchestrator] Proxy:    {'enabled' if PROXY_URL else 'disabled'}")
    print()

    if NUM_WORKERS == 1:
        train.remote(worker_id=0)
    else:
        handles = []
        for i in range(NUM_WORKERS):
            print(f"[Orchestrator] Spawning worker {i}...")
            handles.append(train.spawn(worker_id=i))

        print(f"[Orchestrator] All {NUM_WORKERS} workers spawned. Waiting...")
        for i, h in enumerate(handles):
            try:
                h.get()
                print(f"[Orchestrator] Worker {i} completed.")
            except Exception as e:
                print(f"[Orchestrator] Worker {i} ended: {e}")

    print("[Orchestrator] All workers finished.")
