from django.urls import path

from . import consumers
from .socketio import socketio_app

websocket_urlpatterns = [
    # React frontend uses Socket.IO and connects to this path.
    path("ws/notifications/", socketio_app),
    # Legacy/raw WebSocket consumer (kept for existing Django template JS).
    path("ws/notifications/raw/", consumers.NotificationConsumer.as_asgi()),
]
