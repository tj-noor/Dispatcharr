#!/usr/bin/env python3
"""Exercise XC live catalogs beyond one worker's PostgreSQL pool size.

Credentials are read from the environment so they never appear in argv or the
report.  Run against an isolated container before production deployment.
"""

import argparse
import concurrent.futures
import os
import socket
import ssl
import statistics
import sys
import time
from urllib.parse import urlencode, urlsplit

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


def cancelled_request(url, timeout, cancel_delay):
    """Send a valid request and close the TCP connection before reading it."""
    started = time.monotonic()
    parsed = urlsplit(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    query = urlencode(request_params())
    request = (
        f"GET {path}?{query} HTTP/1.1\r\n"
        f"Host: {parsed.hostname}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")

    connection = socket.create_connection((parsed.hostname, port), timeout=timeout)
    if parsed.scheme == "https":
        context = ssl.create_default_context()
        connection = context.wrap_socket(
            connection, server_hostname=parsed.hostname
        )
    try:
        connection.sendall(request)
        time.sleep(cancel_delay)
    finally:
        connection.close()
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
    parser.add_argument("--cancel-delay", type=float, default=0.02)
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
                lambda _index: cancelled_request(
                    url, args.timeout, args.cancel_delay
                ),
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
