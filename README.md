# Modal Pearl Multi-Account Miner

Multi-account Akoya Pearl miner on Modal.com (H100). Single wallet, multiple Modal accounts, auto-maximize workers, auto-restart.

## Features

- **Multi-account**: Run unlimited Modal accounts simultaneously
- **Auto-restart**: Miners auto-restart after 24h Modal timeout (continuous mining)
- **Auto-maximize workers**: `"auto"` spawns 5 workers per account — Modal runs as many as quota allows
- **Clean stop**: `--stop` kills local processes AND stops remote Modal containers (saves credit)
- **Per-account logs**: Each account has its own log file
- **Staggered start**: 10s delay between accounts to avoid API rate limits

## Setup

```bash
git clone https://github.com/nopperabbo/modal-pearl-multi.git
cd modal-pearl-multi
pip install modal
```

## Configuration

Edit `config.json`:

```json
{
  "wallet": "YOUR_PEARL_WALLET_ADDRESS",
  "pool_host": "pool-v2.akoyapool.com",
  "pool_port": "443",
  "gpu": "H100",
  "accounts": [
    {
      "name": "acc1",
      "token_id": "ak-XXXXX1",
      "token_secret": "as-XXXXX1",
      "workers": "auto"
    },
    {
      "name": "acc2",
      "token_id": "ak-XXXXX2",
      "token_secret": "as-XXXXX2",
      "workers": "auto"
    }
  ]
}
```

### Workers Setting

| Value | Behavior |
|-------|----------|
| `"auto"` | Spawns 5 workers — Modal runs as many as your GPU quota allows, queues the rest |
| `1`, `2`, `3`... | Spawns exact number specified |

> Modal doesn't expose a quota API. `"auto"` spawns 5 workers. Modal runs up to your quota concurrently and queues the rest. Queued workers start when a slot opens. This gives continuous mining.

## Usage

```bash
# Start all accounts (auto-restart enabled)
python run.py

# Start specific accounts only
python run.py acc1 acc3

# Check status
python run.py --status

# Stop ALL miners (local + remote Modal containers)
python run.py --stop

# Stop specific account
python run.py --stop acc2

# Restart all
python run.py --restart

# Restart specific account
python run.py --restart acc1
```

## Monitoring

```bash
# Live log for specific account
tail -f logs/acc1.log

# All logs at once
tail -f logs/*.log

# Quick status check
python run.py --status
```

## How It Works

1. `run.py` reads `config.json` and starts a background process per account
2. Each process runs `modal run miner.py` in a loop (auto-restart on exit)
3. `miner.py` spawns N workers (H100 containers) on Modal
4. Each worker runs the Akoya miner binary with your wallet
5. After 24h (Modal timeout), workers exit → loop restarts them automatically
6. `--stop` kills local processes AND runs `modal app stop` to halt remote containers

## File Structure

```
modal-pearl-multi/
├── config.json       # Accounts & wallet config (EDIT THIS)
├── miner.py          # Modal app (runs on Modal cloud)
├── run.py            # Orchestrator (start/stop/status/restart)
├── .tokens/          # Auto-generated token files (gitignored)
├── .pids/            # PID tracking (gitignored)
└── logs/             # Per-account logs (gitignored)
```

## Important Notes

- **Free tier**: ~$30/month credit per Modal account ≈ 7-8 hours H100
- **Hashrate**: ~600 TH/s per H100 worker
- **Auto-restart**: Enabled by default. After Modal's 24h timeout, mining restarts within 10 seconds
- **Stop = full stop**: `--stop` ensures remote containers are also terminated (no credit waste)
- **One wallet**: All accounts mine to the same wallet address
- **Worker names**: Auto-generated as `{account}-h100-{id}` for pool identification
