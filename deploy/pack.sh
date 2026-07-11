#!/bin/bash
# ساخت پک آماده برای آپلود روی سرور
set -e
cd "$(dirname "$0")/.."

OUTPUT="nexus-deploy.zip"

echo "📦 در حال آماده‌سازی پک..."

zip -r "$OUTPUT" \
  deploy/ \
  lib/ \
  artifacts/api-server/ \
  artifacts/airdrop/ \
  attached_assets/Profinalam_extracted/bot/ \
  pnpm-workspace.yaml \
  pnpm-lock.yaml \
  package.json \
  tsconfig.base.json \
  tsconfig.json \
  --exclude "*/node_modules/*" \
  --exclude "*/dist/*" \
  --exclude "*/.git/*" \
  --exclude "*/dist/public/*" \
  --exclude "**/*.log" \
  --exclude "*/.tsbuildinfo" \
  2>/dev/null

SIZE=$(du -sh "$OUTPUT" | cut -f1)
echo "✅ آماده: $OUTPUT ($SIZE)"
echo ""
echo "آپلود به سرور:"
echo "  scp $OUTPUT root@YOUR_SERVER_IP:/root/"
