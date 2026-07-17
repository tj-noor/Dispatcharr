#!/usr/bin/env python3
"""Exercise XC live catalogs beyond one worker's PostgreSQL pool size.

Credentials are read from the environment so they never appear in argv or the
report.  Run against an isolated container before production deployment.
"""

import argparse
import concurrent.futures
import os
import statistics
import sys
import time

import requests


def catalog_url(base_url):
    return base_url.rstrip("/") + "/player_api.php"


def request_params(action="get_live_streams"):
    return {
        "username": os.environ["XC_USERNAME"],
        "password": os.environ["XC_PASSWORD"],
        "action": action,
    }


def complete_request(url, timeout):
    started = time.monotonic()
    response = requests.get(
        url, params=request_params(), timeout=timeout, stream=True
    )
    response.raise_for_status()
    size = sum(len(chunk) for chunk in response.iter_content(64 * 1024))
    response.close()
    return time.monotonic() - started, size


def cancelled_request(url, timeout):
    started = time.monotonic()
    response = requests.get(
        url, params=request_params(), timeout=timeout, stream=True
    )
    response.raise_for_status()
    next(response.iter_content(1), b"")
    response.close()
    return time.monotonic() - started


def probe_database_endpoint(url, timeout):
    started = time.monotonic()
    response = requests.get(
        url,
        params=request_params("get_live_categories"),
        timeout=timeout,
    )
    elapsed = time.monotonic() - started
    response.raise_for_status()
    response.json()
    return elapsed


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--sequential", type=int, default=50)
    parser.add_argument("--cancelled", type=int, default=32)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    for name in ("XC_USERNAME", "XC_PASSWORD"):
        if not os.environ.get(name):
            parser.error(f"{name} must be set in the environment")

    url = catalog_url(args.base_url)
    sequential_times = []
    sizes = []
    for _ in range(args.sequential):
        elapsed, size = complete_request(url, args.timeout)
        sequential_times.append(elapsed)
        sizes.append(size)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as executor:
        cancelled_times = list(
            executor.map(
                lambda _index: cancelled_request(url, args.timeout),
                range(args.cancelled),
            )
        )

    probe_time = probe_database_endpoint(url, args.timeout)
    print(
        "catalog_pool_harness "
        f"sequential={len(sequential_times)} cancelled={len(cancelled_times)} "
        f"payload_bytes={statistics.median(sizes):.0f} "
        f"sequential_p50_ms={statistics.median(sequential_times) * 1000:.0f} "
        f"sequential_p95_ms={percentile(sequential_times, 0.95) * 1000:.0f} "
        f"cancelled_p95_ms={percentile(cancelled_times, 0.95) * 1000:.0f} "
        f"db_probe_ms={probe_time * 1000:.0f}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"catalog_pool_harness FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
