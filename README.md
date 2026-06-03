# Modal Pearl Multi-Account Miner

Akoya Pearl miner for Modal.com and direct VPS. Multi-account, auto-restart, proxy support. NVIDIA + AMD MI300X.

## Two Modes

| Mode | Script | Use Case |
|------|--------|----------|
| **Modal** | `run.py` + `ml_train.py` | Serverless, multiple accounts, no GPU hardware needed |
| **VPS** | `run_local.py` | Direct on your GPU VPS (NVIDIA Docker or AMD from-source) |

## Quick Start — Modal

```bash
pip install modal
# Edit config.json: wallet, Modal tokens, proxy (optional)
python run.py
```

## Quick Start — VPS (NVIDIA)

```bash
# One-time: install Docker + pull image
bash setup_vps.sh

# Edit config.json: wallet
python3 run_local.py
```

## Quick Start — VPS (AMD MI300X)

```bash
# One-time: install .NET, Rust, build tools, compile miner
bash setup_vps_amd.sh

# Edit config.json: wallet
python3 run_local.py
```

## Configuration

Edit `config.json`:

```json
{
  "wallet": "prl1xxxxxxxxxxxxx",
  "worker_prefix": "rig",
  "gpu": "H100",
  "proxy": "http://user:pass@gw.dataimpulse.com:823",
  "accounts": [
    {
      "name": "acc1",
      "token_id": "ak-XXXXX",
      "token_secret": "as-XXXXX",
      "workers": "auto"
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `wallet` | Pearl wallet address (`prl1...`) |
| `worker_prefix` | Worker name prefix (default: `rig`) |
| `gpu` | GPU: `H100`, `H200`, `B200`, `A100-80GB` |
| `proxy` | HTTP proxy URL (empty = no proxy) |
| `accounts` | Modal accounts (only for `run.py`) |

## Modal Mode (run.py)

```bash
python run.py                  # Start all accounts
python run.py acc1 acc3        # Start specific accounts
python run.py --status         # Check status
python run.py --stop           # Stop ALL (local + remote)
python run.py --restart        # Restart all
tail -f logs/acc1.log          # Live log
```

## VPS Mode (run_local.py)

Auto-detects GPU backend (NVIDIA → Docker, AMD → binary).

```bash
python3 run_local.py              # Start all GPUs
python3 run_local.py --status     # Check status
python3 run_local.py --stop       # Stop all
python3 run_local.py --restart    # Restart all
python3 run_local.py --gpus 0,1   # Specific GPUs only
python3 run_local.py --backend amd # Force AMD backend
```

## File Structure

```
modal-pearl/
├── config.json         # Config (EDIT THIS)
├── ml_train.py         # Modal app (serverless mining)
├── run.py              # Modal orchestrator (multi-account)
├── run_local.py        # VPS runner (NVIDIA Docker + AMD binary)
├── setup_vps.sh        # VPS setup: Docker + Akoya image (NVIDIA)
├── setup_vps_amd.sh    # VPS setup: build from source (AMD MI300X)
├── .tokens/            # Modal tokens (gitignored)
├── .pids/              # PID tracking (gitignored)
└── logs/               # Logs (gitignored)
```

## Specs

- Pool: pool-v2.akoyapool.com:443 (gRPC + TLS)
- Fee: 2%
- Min payout: 10 PRL
- Hashrate: ~600 TH/s (H100), ~800+ TH/s (H200), ~1000+ TH/s (MI300X)
- First payout: 24-48 hours

## Anti-Ban

- Worker names: randomized (`rig-0-xxxx`), not `modal-*`
- Proxy: masks pool connection IP
- Official Akoya Docker image (NVIDIA) or open-source build (AMD)
- Pool supports cloud miners (Vast.AI/RunPod guides on site)
