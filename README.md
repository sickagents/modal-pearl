# Modal Pearl Multi-Account Miner

Akoya Pearl miner for Modal.com and direct VPS. Multi-account, auto-restart, proxy support.

## Two Modes

| Mode | Script | Use Case |
|------|--------|----------|
| **Modal** | `run.py` + `ml_train.py` | Serverless, multiple accounts, no GPU hardware needed |
| **VPS** | `run_local.py` + `setup_vps.sh` | Direct on your GPU VPS, Docker-based |

## Quick Start — Modal

```bash
pip install modal
# Edit config.json: wallet, Modal tokens, proxy (optional)
python run.py
```

## Quick Start — VPS

```bash
# One-time setup
bash setup_vps.sh

# Edit config.json: wallet, proxy (optional)
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

Multi-account serverless mining on Modal.com.

```bash
python run.py                  # Start all accounts
python run.py acc1 acc3        # Start specific accounts
python run.py --status         # Check status
python run.py --stop           # Stop ALL (local + remote)
python run.py --restart        # Restart all
tail -f logs/acc1.log          # Live log
```

## VPS Mode (run_local.py)

Direct Docker mining on your GPU VPS.

```bash
python3 run_local.py              # Start all GPUs
python3 run_local.py --status     # Check status
python3 run_local.py --stop       # Stop all containers
python3 run_local.py --restart    # Restart all
python3 run_local.py --gpus 0,1   # Specific GPUs only
docker logs -f akoya-gpu0         # Live log
```

## How It Works — Modal

1. `run.py` reads `config.json`, starts background process per account
2. Each process runs `modal run ml_train.py` in a loop
3. `ml_train.py` pulls Akoya Docker image, detects GPU, mines
4. After 24h timeout → auto-restart within 10s

## How It Works — VPS

1. `setup_vps.sh` installs Docker + pulls Akoya image (one-time)
2. `run_local.py` detects GPUs, applies power/clock optimizations
3. Starts one Docker container per GPU with `--gpus device=N`
4. Containers auto-restart on crash (`--restart unless-stopped`)
5. Logs tailed to `logs/local/gpuN.log`

## File Structure

```
modal-pearl/
├── config.json       # Config (EDIT THIS)
├── ml_train.py       # Modal app (serverless mining)
├── run.py            # Modal orchestrator (multi-account)
├── run_local.py      # VPS runner (Docker-based)
├── setup_vps.sh      # VPS one-time setup
├── .tokens/          # Modal tokens (gitignored)
├── .pids/            # PID tracking (gitignored)
└── logs/             # Logs (gitignored)
```

## Specs

- Pool: pool-v2.akoyapool.com:443 (gRPC + TLS)
- Fee: 2%
- Min payout: 10 PRL
- Hashrate: ~600 TH/s (H100), ~800+ TH/s (H200)
- First payout: 24-48 hours

## Anti-Ban

- Worker names: randomized (`rig-0-xxxx`), not `modal-*`
- Proxy: masks pool connection IP
- Official Akoya Docker image
- Pool supports cloud miners (Vast.AI/RunPod guides on site)
