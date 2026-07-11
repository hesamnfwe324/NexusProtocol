#!/bin/bash
set -e

# 🚀 BLOCKCHAIN ORCHESTRATOR - PROFESSIONAL UBUNTU DEPLOYMENT
echo "--------------------------------------------------------"
echo "🚀 INITIALIZING DEPLOYMENT SCRIPT..."
echo "--------------------------------------------------------"

# 1. Directory Setup
cd "$(dirname "$0")"
mkdir -p logs

# 2. Check for Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Run: sudo apt update && sudo apt install python3-pip python3-venv"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Detected Python $PY_VERSION"

# 3. Virtual Environment (Isolation)
if [ ! -d "venv" ]; then
    echo "📦 Creating Virtual Environment (venv)..."
    python3 -m venv venv || { echo "❌ Failed to create venv. Run: sudo apt install python3-venv"; exit 1; }
fi
source venv/bin/activate

# 4. Dependency Management
echo "📦 Installing/Updating Dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# 5. Security Check
if [ ! -f ".env" ]; then
    echo "⚠️  CRITICAL: .env file missing! Create one based on .env.example"
    exit 1
fi

# 6. Runtime
echo "--------------------------------------------------------"
echo "✅ DEPLOYMENT READY"
echo "🚀 STARTING BOT..."
echo "--------------------------------------------------------"

export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 main_orchestrator.py
