from __future__ import annotations

from typing import Any

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def check_db() -> dict[str, Any]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - health must degrade, not crash
        return {"ok": False, "error": str(exc)}
    else:
        return {"ok": True}


def check_redis() -> dict[str, Any]:
    url = getattr(settings, "REDIS_URL", None)
    if not url:
        return {"ok": False, "error": "REDIS_URL not configured"}
    try:
        client = redis.Redis.from_url(
            url,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )
        client.ping()
    except Exception as exc:  # noqa: BLE001 - health must degrade, not crash
        return {"ok": False, "error": str(exc)}
    else:
        return {"ok": True}


def health(request):
    db = check_db()
    redis_info = check_redis()
    components = {"db": db, "redis": redis_info}

    all_ok = all(v.get("ok", False) for v in components.values())
    some_ok = any(v.get("ok", False) for v in components.values())

    status = "ok" if all_ok else ("degraded" if some_ok else "down")
    http_status = 200 if all_ok else 503

    return JsonResponse(
        {"status": status, "components": components},
        status=http_status,
    )
