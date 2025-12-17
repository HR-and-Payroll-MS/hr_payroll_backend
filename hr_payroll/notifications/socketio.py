"""Socket.IO server for the React frontend.

The frontend uses `socket.io-client` with:
- server URL: ws://<host>:8000
- `path`: /ws/notifications/
- `query.token`: JWT access token

So we mount Socket.IO at the non-default path `/ws/notifications/`.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs

import socketio
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError

logger = logging.getLogger(__name__)

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


@database_sync_to_async
def _get_user_id_from_access_token(token: str) -> int:
    jwt_auth = JWTAuthentication()
    validated = jwt_auth.get_validated_token(token)
    user = jwt_auth.get_user(validated)
    return int(user.id)


def _extract_token(environ: dict, auth: object | None) -> str | None:
    # Prefer querystring token since the frontend uses `query: { token }`.
    #
    # python-socketio passes different shapes depending on async mode:
    # - ASGI: `environ` is the ASGI scope with `query_string: bytes`
    # - WSGI: `environ` is a WSGI environ with `QUERY_STRING: str`
    # - Some servers include `asgi.scope` inside `environ`
    scope = environ
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
    if token:
        return token

    # Allow `auth: { token }` as fallback.
    if isinstance(auth, dict):
        auth_token = auth.get("token")
        if isinstance(auth_token, str) and auth_token:
            return auth_token

    return None


@sio.event
async def connect(sid, environ, auth=None):
    # `auth` may be omitted depending on the client/transport.
    token = _extract_token(environ, auth)
    if not token:
        reason = "unauthorized"
        raise ConnectionRefusedError(reason)

    try:
        user_id = await _get_user_id_from_access_token(token)
    except TokenError as exc:
        message = str(exc)
        # Frontend expects this exact string to trigger refresh.
        if "expired" in message.lower():
            reason = "jwt_expired"
            raise ConnectionRefusedError(reason) from exc
        reason = "unauthorized"
        raise ConnectionRefusedError(reason) from exc

    await sio.save_session(sid, {"user_id": user_id})
    await sio.enter_room(sid, f"user_{user_id}")


@sio.event
async def disconnect(sid):
    # Rooms/session are cleaned up automatically.
    _ = sid


@sio.event
async def ping_notification(sid, data):
    """Test event from the frontend.

    Frontend emits `ping_notification` and expects the server to:
    - log receipt
    - emit a `notification` event back to the sender
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


def emit_notification_to_user(user_id: int, payload: dict) -> None:
    """Emit a realtime notification to a specific user.

    Safe to call from sync Django code (signals, views). If nobody is connected,
    this is effectively a no-op.
    """

    async_to_sync(sio.emit)(
        "notification",
        payload,
        room=f"user_{int(user_id)}",
    )
