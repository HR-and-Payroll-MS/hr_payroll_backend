"""Global Socket.IO server for the frontend.

This is intentionally domain-agnostic: notifications, leave requests, attendance
live dashboards, chat, announcements, etc. should all share the same Socket.IO
server instance.

Current frontend convention:
- URL base: ws://<host>:8000
- Socket.IO path: /ws/notifications/
- Auth: `query.token` (JWT access token)

Even though the path contains "notifications", the server is global and can emit
any events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

import socketio
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError

logger = logging.getLogger(__name__)


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


@dataclass(frozen=True)
class UserRealtimeContext:
    user_id: int
    group_names: tuple[str, ...]
    employee_id: int | None
    department_id: int | None


def _normalize_room_suffix(value: str) -> str:
    return "_".join(value.strip().lower().split())


def room_for_user(user_id: int) -> str:
    return f"user_{int(user_id)}"


def room_for_group(group_name: str) -> str:
    return f"group_{_normalize_room_suffix(group_name)}"


def room_for_department(department_id: int) -> str:
    return f"department_{int(department_id)}"


def room_for_employee(employee_id: int) -> str:
    return f"employee_{int(employee_id)}"


@database_sync_to_async
def _get_user_context_from_access_token(token: str) -> UserRealtimeContext:
    jwt_auth = JWTAuthentication()
    validated = jwt_auth.get_validated_token(token)
    user = jwt_auth.get_user(validated)

    groups_qs = getattr(user, "groups", None)
    if groups_qs is None:
        group_names: tuple[str, ...] = ()
    else:
        group_names = tuple(groups_qs.order_by("name").values_list("name", flat=True))

    employee = getattr(user, "employee", None)
    employee_id = getattr(employee, "id", None)
    department_id = getattr(employee, "department_id", None)

    return UserRealtimeContext(
        user_id=int(user.id),
        group_names=group_names,
        employee_id=int(employee_id) if employee_id else None,
        department_id=int(department_id) if department_id else None,
    )


def _extract_token(environ: dict[str, Any], auth: Any | None) -> str | None:
    """Extract JWT token from Socket.IO environ/auth.

    Handles python-socketio environ shapes across ASGI/WSGI servers.
    """

    scope: Any = environ
    if isinstance(environ, dict) and "asgi.scope" in environ:
        inner = environ.get("asgi.scope")
        if isinstance(inner, dict):
            scope = inner

    query_string: str | bytes = ""
    if isinstance(scope, dict) and "query_string" in scope:
        query_string = scope.get("query_string", b"")
    elif isinstance(scope, dict) and "QUERY_STRING" in scope:
        query_string = scope.get("QUERY_STRING", "")

    if isinstance(query_string, (bytes, bytearray)):
        query_string = query_string.decode(errors="ignore")

    token = parse_qs(str(query_string)).get("token", [None])[0]
    if isinstance(token, str) and token:
        return token

    # Allow `auth: { token }` as fallback.
    if isinstance(auth, dict):
        auth_token = auth.get("token")
        if isinstance(auth_token, str) and auth_token:
            return auth_token

    return None


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: Any | None = None):
    token = _extract_token(environ, auth)
    if not token:
        msg = "unauthorized"
        raise ConnectionRefusedError(msg)

    try:
        ctx = await _get_user_context_from_access_token(token)
    except TokenError as exc:
        message = str(exc)
        if "expired" in message.lower():
            msg = "jwt_expired"
            raise ConnectionRefusedError(msg) from exc
        msg = "unauthorized"
        raise ConnectionRefusedError(msg) from exc
    except AuthenticationFailed as exc:  # user not found / inactive, etc.
        msg = "unauthorized"
        raise ConnectionRefusedError(msg) from exc
    except Exception as exc:
        logger.exception("Socket.IO connect error")
        msg = "server_error"
        raise ConnectionRefusedError(msg) from exc

    await sio.save_session(
        sid,
        {
            "user_id": ctx.user_id,
            "group_names": list(ctx.group_names),
            "employee_id": ctx.employee_id,
            "department_id": ctx.department_id,
        },
    )

    # Always join the per-user room.
    await sio.enter_room(sid, room_for_user(ctx.user_id))

    # Optional rooms for future cross-domain features.
    if ctx.employee_id is not None:
        await sio.enter_room(sid, room_for_employee(ctx.employee_id))
    if ctx.department_id is not None:
        await sio.enter_room(sid, room_for_department(ctx.department_id))
    for group_name in ctx.group_names:
        await sio.enter_room(sid, room_for_group(group_name))


@sio.event
async def disconnect(sid: str):
    _ = sid


@sio.event
async def ping_notification(sid: str, data: Any):
    """Temporary test hook used by the current frontend page.

    Kept for backward compatibility while we generalize realtime.
    """

    session = await sio.get_session(sid)
    user_id = session.get("user_id") if isinstance(session, dict) else None
    logger.info("Ping received from user: %s %s", user_id, data)

    payload = {
        "id": 999,
        "title": "Socket Test",
        "message": "Ping received from NotificationCenterPage",
        "meta": data,
    }

    await sio.emit("notification", payload, to=sid)


def emit_event_to_room(room: str, event: str, payload: dict[str, Any]) -> None:
    """Emit an event to a room from sync Django code."""

    async_to_sync(sio.emit)(event, payload, room=room)


def emit_event_to_user(user_id: int, event: str, payload: dict[str, Any]) -> None:
    emit_event_to_room(room_for_user(user_id), event, payload)


def emit_event_to_group(group_name: str, event: str, payload: dict[str, Any]) -> None:
    emit_event_to_room(room_for_group(group_name), event, payload)


def emit_event_to_department(
    department_id: int,
    event: str,
    payload: dict[str, Any],
) -> None:
    emit_event_to_room(room_for_department(department_id), event, payload)


def emit_event_to_employee(
    employee_id: int,
    event: str,
    payload: dict[str, Any],
) -> None:
    emit_event_to_room(room_for_employee(employee_id), event, payload)
