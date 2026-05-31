# Modal Pearl Multi-Account Miner

Multi-account Akoya Pearl miner on Modal.com (H100). Single wallet, multiple Modal accounts, auto-maximize workers.

## Setup

```bash
git clone https://github.com/YOUR_USER/modal-pearl-multi.git
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
      "workers": 3
    }
  ]
}
```

### Workers Setting

| Value | Behavior |
|-------|----------|
| `"auto"` | Spawns 5 workers — Modal runs as many as your quota allows, queues the rest |
| `1`, `2`, `3`... | Spawns exact number specified |

> **Note:** Modal doesn't expose a quota API. `"auto"` spawns 5 workers per account. Modal will run up to your GPU quota concurrently and queue the rest. Queued workers start when a slot opens (after 24h timeout cycle). This gives continuous mining without manual intervention.

## Usage

```bash
# Run all accounts
python run.py

# Run specific accounts
python run.py acc1 acc3

# Check status
python run.py --status

# Stop all
python run.py --stop

# Stop specific account
python run.py --stop acc2
```

## Monitoring

```bash
# Live log for specific account
tail -f logs/acc1.log

# Modal dashboard logs
MODAL_CONFIG_PATH=.tokens/acc1.toml modal app logs akoya-pearl-miner

# Quick status
python run.py --status
```

## File Structure

```
modal-pearl-multi/
├── config.json       # Your accounts & wallet config
├── miner.py          # Modal app (deployed per account)
├── run.py            # Orchestrator (start/stop/status)
├── .tokens/          # Auto-generated Modal token files (gitignored)
├── .pids/            # PID tracking (gitignored)
└── logs/             # Per-account logs (gitignored)
```

## Adding Accounts

Just add entries to `config.json`:

```json
{
  "name": "acc3",
  "token_id": "ak-XXXXX3",
  "token_secret": "as-XXXXX3",
  "workers": "auto"
}
```

Then `python run.py acc3` or restart all with `python run.py`.

## How It Works

1. `run.py` reads `config.json`
2. For each account, sets `MODAL_CONFIG_PATH` to the account's token
3. Runs `modal run miner.py` as a background process
4. `miner.py` spawns N workers (H100 containers) on Modal
5. Each worker runs the Akoya miner binary with your wallet
6. Workers auto-restart after 24h timeout (Modal limit)

## Tips

- **Free tier**: ~$30/month credit per account ≈ 7-8 hours H100 time
- **Hashrate**: ~600 TH/s per H100 worker
- **Worker names**: Auto-generated as `{account}-h100-{id}` for pool identification
- **Stagger**: Accounts start with 10s delay to avoid Modal API rate limits
