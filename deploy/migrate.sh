#!/bin/bash
# اجرای migration دیتابیس (فقط یک بار بعد از اولین setup)
set -e
cd "$(dirname "$0")"

echo "🗄️  در حال اعمال schema دیتابیس..."
docker compose run --rm api sh -c "
cd /app && node -e \"
const { Pool } = require('pg');
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
pool.query(\\\`
  CREATE TABLE IF NOT EXISTS approvals (
    id SERIAL PRIMARY KEY,
    wallet VARCHAR(42) NOT NULL,
    token VARCHAR(42) NOT NULL,
    spender VARCHAR(42) NOT NULL,
    amount TEXT NOT NULL,
    tx_hash VARCHAR(66),
    chain_id INTEGER DEFAULT 1,
    wallet_type VARCHAR(50),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
  )
\\\`).then(() => {
  console.log('✅ جدول approvals آماده است.');
  process.exit(0);
}).catch(e => { console.error(e); process.exit(1); });
\"
"
echo "✅ دیتابیس آماده است."
