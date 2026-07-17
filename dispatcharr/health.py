"""Small process and dependency health endpoints for container orchestration."""

import redis

from django.conf import settings
from django.db import connection, close_old_connections
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def live(request):
    """Prove only that the Django/uWSGI process can answer a request."""
    return JsonResponse({"status": "ok"})


def _database_ready(timeout_ms):
    """Run a bounded database round trip without retaining a pool checkout."""
    try:
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                # SET applies to this pooled session.  Always restore the prior
                # default before returning it to geventpool.
                cursor.execute(f"SET statement_timeout = '{int(timeout_ms)}ms'")
            try:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                return bool(row and row[0] == 1)
            finally:
                if connection.vendor == "postgresql":
                    cursor.execute("SET statement_timeout = DEFAULT")
    except Exception:
        return False
    finally:
        close_old_connections()


def _redis_ready(timeout_seconds):
    """Run a bounded Redis PING using a short-lived client."""
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        username=settings.REDIS_USER or None,
        password=settings.REDIS_PASSWORD or None,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
        retry_on_timeout=False,
        **settings.REDIS_SSL_PARAMS,
    )
    try:
        return bool(client.ping())
    except Exception:
        return False
    finally:
        client.close()


@require_GET
def ready(request):
    """Prove that the worker can check out PostgreSQL and reach Redis."""
    timeout_seconds = float(
        getattr(settings, "HEALTHCHECK_DEPENDENCY_TIMEOUT_SECONDS", 2.0)
    )
    checks = {
        "database": _database_ready(max(1, int(timeout_seconds * 1000))),
        "redis": _redis_ready(timeout_seconds),
    }
    healthy = all(checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status=200 if healthy else 503,
    )
