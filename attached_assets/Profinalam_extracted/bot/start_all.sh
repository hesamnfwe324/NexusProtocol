#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# NexusProtocol — Supervisor Startup
# اجرای همزمان:
#   1. admin_panel.py   → دریافت دستورات تلگرام (polling)
#   2. main_orchestrator.py → اجرای drain + ارسال اعلان (بدون polling)
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "🚀 NexusProtocol Starting..."
mkdir -p logs

# 1️⃣  پنل ادمین در background
echo "📱 Starting Admin Panel..."
python -u admin_panel.py >> logs/admin_panel.log 2>&1 &
ADMIN_PID=$!
echo "   Admin PID: $ADMIN_PID"

# صبر می‌کنیم ربات ادمین بالا بیاد
sleep 3

# 2️⃣  ربات اجراکننده در foreground
echo "⚡ Starting Main Orchestrator..."
exec python -u main_orchestrator.py

# اگر main_orchestrator بمیرد، admin هم kill می‌شود
trap "kill $ADMIN_PID 2>/dev/null; exit" SIGTERM SIGINT
