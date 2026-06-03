# Modal Pearl Multi-Account Miner

Multi-account Akoya Pearl miner on Modal.com. Single wallet, multiple Modal accounts, auto-restart, proxy support.

## Features

- **Multi-account**: Run unlimited Modal accounts simultaneously
- **Akoya pool**: Uses official Docker image (`registry.akoyapool.com/akoya-miner:latest`)
- **Auto-restart**: Miners auto-restart after 24h Modal timeout
- **Auto-maximize workers**: `\"auto\"` spawns 5 workers per account
- **Proxy support**: HTTP proxy to mask pool connection IP
- **Clean stop**: `--stop` kills local + remote Modal containers
- **GPU auto-detect**: H100/H200/B200/Ada kernel selection
- **Generic worker names**: Randomized names (not cloud-related)

## Setup

```bash
git clone https://github.com/sickagents/modal-pearl.git
cd modal-pearl
pip install modal
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
| `worker_prefix` | Prefix for worker names (default: `rig`) |
| `gpu` | GPU type: `H100`, `H200`, `B200`, `A100-80GB` |
| `proxy` | HTTP proxy URL (empty = no proxy) |
| `accounts[].name` | Account identifier |
| `accounts[].token_id` | Modal token ID |
| `accounts[].token_secret` | Modal token secret |
| `accounts[].workers` | `"auto"` (5 workers) or specific number |

## Usage

```bash
# Start all accounts
python run.py

# Start specific accounts
python run.py acc1 acc3

# Check status
python run.py --stop

# Stop ALL (local + remote containers)
python run.py --stop

# Restart all
python run.py --restart
```

## Monitoring

```bash
# Live log
tail -f logs/acc1.log

# All logs
tail -f logs/*.log

# Quick status
python run.py --status

# Akoya dashboard
# https://akoyapool.com → paste your wallet
```

## File Structure

```
modal-pearl/
├── config.json       # Accounts & wallet config (EDIT THIS)
├── ml_train.py       # Modal app (runs on Modal cloud)
├── run.py            # Orchestrator (start/stop/status/restart)
├── run_local.py      # Direct VPS runner (no Modal)
├── setup_vps.sh      # VPS relay setup (for run_local.py)
├── .tokens/          # Auto-generated token files (gitignored)
├── .pids/            # PID tracking (gitignored)
└── logs/             # Per-account logs (gitignored)
```

## How It Works

1. `run.py` reads `config.json` and starts a background process per account
2. Each process runs `modal run ml_train.py` in a loop (auto-restart on exit)
3. `ml_train.py` pulls Akoya Docker image, detects GPU, selects kernel
4. Each worker mines with randomized worker name
5. After 24h (Modal timeout), workers exit → loop restarts automatically
6. `--stop` kills local processes AND runs `modal app stop` on remote

## Anti-Ban

- Worker names: randomized (`rig-xxxx`), not `modal-*` or `h100-*`
- Proxy: masks pool connection IP (set in config.json)
- Official Akoya Docker image: pool supports cloud miners
- Pool supports Vast.AI and RunPod (see their Get Started page)

## Notes

- Pool fee: 2%
- Min payout: 10 PRL
- First payout: 24-48 hours
- Free Modal tier: ~$30/month credit ≈ 7-8 hours H100
- Hashrate: ~600 TH/s per H100, ~800+ TH/s per H200
