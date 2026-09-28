import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp


PATHS = (
    "/api/dashboard?period=month",
    "/api/orders?page=1",
    "/api/threads?page=1",
    "/api/customers?page=1&q=&activity=all&sort=recent",
    "/api/sales?page=1",
)


async def run(base_url: str, requests: int, concurrency: int, credentials_file: Path) -> int:
    if urlsplit(base_url).scheme != "http" or urlsplit(base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Smoke checks must target a local HTTP service")
    if requests > 150:
        raise ValueError("Keep smoke checks below the API's per-minute rate limit")
    credentials = json.loads(credentials_file.read_text(encoding="utf-8"))
    if not isinstance(credentials, dict) or not credentials.get("username") or not credentials.get("password"):
        raise ValueError("Credentials file needs username and password")
    timeout = aiohttp.ClientTimeout(total=15)
    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    ) as session:
        async with session.post(
            f"{base_url}/api/auth/password",
            json=credentials,
            headers={"Origin": base_url, "X-Login-Request": "1"},
        ) as login:
            if login.status != 200:
                print(f"password login unavailable: HTTP {login.status}")
                return 2

        semaphore = asyncio.Semaphore(concurrency)

        async def request(index: int):
            started = time.perf_counter()
            async with semaphore, session.get(f"{base_url}{PATHS[index % len(PATHS)]}") as response:
                await response.read()
                return response.status, (time.perf_counter() - started) * 1000

        results = await asyncio.gather(*(request(index) for index in range(requests)))

    latencies = sorted(latency for _, latency in results)
    statuses = Counter(status for status, _ in results)
    errors = sum(count for status, count in statuses.items() if status != 200)

    def percentile(value: float) -> float:
        return latencies[min(len(latencies) - 1, round((len(latencies) - 1) * value))]

    print(
        f"requests={requests} concurrency={concurrency} statuses={dict(statuses)} errors={errors} "
        f"mean={statistics.fmean(latencies):.1f}ms p50={percentile(.5):.1f}ms "
        f"p95={percentile(.95):.1f}ms p99={percentile(.99):.1f}ms"
    )
    return int(errors > 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    parser.add_argument("--credentials-file", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.url.rstrip("/"), max(1, args.requests), max(1, args.concurrency), args.credentials_file)))
