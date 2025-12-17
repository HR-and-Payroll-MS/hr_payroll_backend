from django.urls import path

from . import consumers

websocket_urlpatterns = [
    # Legacy/raw WebSocket consumer (kept for existing Django template JS).
    path("ws/notifications/raw/", consumers.NotificationConsumer.as_asgi()),
]
