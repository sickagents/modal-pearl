#!/bin/bash
# Akoya Miner Build from Source — AMD MI300X (ROCm)
# Run this on your MI300X VPS

set -e

echo "=== Akoya Miner Build (AMD MI300X) ==="

# Fix cross-device link issue for rustup
export TMPDIR=/root/.rustup/tmp_local
mkdir -p "$TMPDIR"

# 1. Install .NET 10 SDK
if ! command -v dotnet &> /dev/null; then
    echo "[1/5] Installing .NET 10 SDK..."
    curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 10.0
    export PATH="$HOME/.dotnet:$PATH"
    grep -q '.dotnet' ~/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.dotnet:$PATH"' >> ~/.bashrc
    echo "      Done."
else
    echo "[1/5] .NET already installed: $(dotnet --version)"
fi

# 2. Install Rust (with TMPDIR fix)
if ! command -v cargo &> /dev/null; then
    echo "[2/5] Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    . "$HOME/.cargo/env"
    echo "      Done."
else
    echo "[2/5] Rust already installed: $(cargo --version)"
fi

# Verify cargo works
if ! cargo --version &> /dev/null; then
    echo "ERROR: cargo not working. Try:"
    echo "  rm -rf ~/.rustup"
    echo "  export TMPDIR=/tmp"
    echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"
    exit 1
fi

# 3. Install build tools
echo "[3/5] Installing build tools..."
apt update && apt install -y build-essential clang zlib1g-dev git python3

# 4. Verify ROCm
echo "[4/5] Verifying ROCm..."
if ! command -v hipcc &> /dev/null; then
    echo "ERROR: hipcc not found. Install ROCm first:"
    echo "  https://rocm.docs.amd.com/projects/install-on-linux/en/latest/"
    echo ""
    echo "Quick install (Ubuntu 22.04/24.04):"
    echo "  sudo apt install rocm-hip-runtime rocm-hip-sdk"
    echo "  # or:"
    echo "  wget https://repo.radeon.com/amdgpu-install/6.4.1/ubuntu/jammy/amdgpu-install_6.4.60401-1_all.deb"
    echo "  sudo apt install ./amdgpu-install_6.4.60401-1_all.deb"
    echo "  sudo amdgpu-install --usecase=hip,rocm"
    exit 1
fi
echo "      hipcc: $(hipcc --version 2>&1 | head -1)"

# 5. Clone and build
echo "[5/5] Cloning and building Akoya miner (ROCm backend)..."
cd /opt
if [ -d "akoya-miner" ]; then
    echo "      Repo exists, pulling latest..."
    cd akoya-miner
    git pull
    git submodule update --init --recursive
else
    git clone --recurse-submodules https://github.com/akoyapool/akoya-miner.git
    cd akoya-miner
fi

echo "      Building with BACKEND=rocm..."
BACKEND=rocm ./build.sh

echo ""
echo "=== Build Complete ==="
echo ""
echo "Binary: /opt/akoya-miner/out/akoya-miner"
echo ""
echo "Run:"
echo "  cd /opt/akoya-miner"
echo "  AKOYA_POOL_WALLET=prl1xxxxx AKOYA_POOL_WORKER=rig01 ./out/akoya-miner"
