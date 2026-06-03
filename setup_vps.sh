#!/bin/bash
# Akoya Miner VPS Setup — run once on your GPU VPS
# Installs Docker + pulls Akoya miner image

set -e

echo "=== Akoya VPS Setup ==="

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "[1/3] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    echo "      Done."
else
    echo "[1/3] Docker already installed."
fi

# Pull Akoya miner image
echo "[2/3] Pulling Akoya miner image..."
docker pull registry.akoyapool.com/akoya-miner:latest
echo "      Done."

# Verify
echo "[3/3] Verifying..."
docker run --rm registry.akoyapool.com/akoya-miner:latest --help 2>/dev/null || true

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next: edit config.json with your wallet, then run:"
echo "  python3 run_local.py"
echo ""
echo "Commands:"
echo "  python3 run_local.py              # Start all GPUs"
echo "  python3 run_local.py --status     # Check status"
echo "  python3 run_local.py --stop       # Stop all"
echo "  python3 run_local.py --restart    # Restart all"
