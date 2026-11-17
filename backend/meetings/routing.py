from django.urls import path

from .consumers import CallConsumer

websocket_urlpatterns = [
    path("ws/meetings/<int:meeting_id>/call/", CallConsumer.as_asgi()),
]
