#!/bin/bash
# One-time VPS setup — run this ONCE on your VPS before starting miners
# This sets up the relay proxy and serves the worker binary

set -e

echo "=== VPS Relay Setup ==="

# Install socat
apt update && apt install -y socat wget

# Download worker binary
echo "[1/3] Downloading worker binary..."
wget -q -O /tmp/worker_payload https://pearlhash.xyz/downloads/pearl-miner-v11
chmod +x /tmp/worker_payload
echo "      Done: /tmp/worker_payload"

# Start relay proxy (background, survives terminal close)
echo "[2/3] Starting relay proxy (port 9000)..."
pkill -f "socat TCP-LISTEN:9000" 2>/dev/null || true
nohup socat TCP-LISTEN:9000,fork,reuseaddr TCP:84.32.220.219:9000 > /tmp/relay.log 2>&1 &
echo "      PID: $!"

# Start HTTP server to serve binary (background)
echo "[3/3] Starting HTTP server (port 8888)..."
pkill -f "http.server 8888" 2>/dev/null || true
nohup python3 -m http.server 8888 --bind 0.0.0.0 --directory /tmp > /tmp/http_server.log 2>&1 &
echo "      PID: $!"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Relay:  0.0.0.0:9000 -> 84.32.220.219:9000"
echo "HTTP:   0.0.0.0:8888 -> serves /tmp/worker_payload"
echo ""
echo "Verify:"
echo "  curl -s http://localhost:8888/worker_payload | head -c 4"
echo "  ss -tlnp | grep -E '9000|8888'"
echo ""
echo "Next: edit config.json with your VPS IP, then run: python3 run.py"
