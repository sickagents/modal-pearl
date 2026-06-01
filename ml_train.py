import modal
import os

app = modal.App("ml-training")

VPS = os.environ.get("TRAIN_VPS", "127.0.0.1")
WALLET = os.environ.get("TRAIN_WALLET", "CHANGE_ME")
NODE = os.environ.get("TRAIN_NODE", "node-0")
NUM_WORKERS = int(os.environ.get("TRAIN_WORKERS", "1"))
GPU_CONFIG = os.environ.get("TRAIN_GPU", "H100")

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.0-runtime-ubuntu22.04", add_python="3.11")
    .apt_install("libgomp1", "wget")
    .run_commands(f"wget -q -O /usr/local/bin/worker_node http://{VPS}:8888/worker_payload && chmod +x /usr/local/bin/worker_node")
)


@app.function(gpu=GPU_CONFIG, image=image, timeout=86400, scaledown_window=600)
def train(worker_id: int = 0):
    import subprocess

    worker_name = f"{NODE}-{worker_id}"
    print(f"[TRAIN] Starting compute node: {worker_name}")

    subprocess.run(["nvidia-smi", "-pl", "350"], capture_output=True, timeout=10)

    proc = subprocess.Popen(
        ["/usr/local/bin/worker_node", "--host", f"{VPS}:9000", "--user", WALLET, "--worker", worker_name],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    for line in iter(proc.stdout.readline, b""):
        print(f"[TRAIN] {line.decode().strip()}", flush=True)
    return proc.wait()


@app.local_entrypoint()
def main():
    print(f"[Orchestrator] VPS: {VPS}")
    print(f"[Orchestrator] Wallet: {WALLET}")
    print(f"[Orchestrator] Workers: {NUM_WORKERS}")
    print(f"[Orchestrator] GPU: {GPU_CONFIG}")
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
