"""Short-lived, revisioned cache for fully materialized XC live catalogs."""

import hashlib
import json
import time

from django.conf import settings
from django.core.cache import cache


CATALOG_REVISION_KEY = "output:xc-live:revision"


def get_catalog_revision():
    """Return the shared catalog revision, or ``None`` if Redis is unavailable."""
    try:
        cache.add(CATALOG_REVISION_KEY, 1, timeout=None)
        return int(cache.get(CATALOG_REVISION_KEY) or 1)
    except Exception:
        return None


def bump_catalog_revision():
    """Invalidate every XC catalog without scanning or deleting response keys."""
    try:
        cache.add(CATALOG_REVISION_KEY, 1, timeout=None)
        return cache.incr(CATALOG_REVISION_KEY)
    except Exception:
        try:
            revision = time.time_ns()
            cache.set(CATALOG_REVISION_KEY, revision, timeout=None)
            return revision
        except Exception:
            return None


def catalog_cache_key(request, user, category_id=None):
    """Key by response origin and every user property that changes visibility."""
    revision = get_catalog_revision()
    if revision is None:
        return None

    profile_ids = list(
        user.channel_profiles.order_by("pk").values_list("pk", flat=True)
    )
    identity = {
        "revision": revision,
        "origin": f"{request.scheme}://{request.get_host()}",
        "user_id": user.pk,
        "user_level": user.user_level,
        "hide_adult": bool(
            (user.custom_properties or {}).get("hide_adult_content", False)
        ),
        "profile_ids": profile_ids,
        "category_id": str(category_id) if category_id is not None else None,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"output:xc-live:{revision}:{digest}"


def get_cached_catalog(key):
    if key is None:
        return None
    try:
        payload = cache.get(key)
        if isinstance(payload, str):
            return payload.encode("utf-8")
        return payload
    except Exception:
        return None


def cache_catalog(key, payload):
    if key is None:
        return
    timeout = int(getattr(settings, "XC_LIVE_CATALOG_CACHE_TIMEOUT", 15))
    if timeout <= 0:
        return
    try:
        cache.set(key, payload, timeout=timeout)
    except Exception:
        # Catalog generation is the correctness path; cache availability is not.
        pass
