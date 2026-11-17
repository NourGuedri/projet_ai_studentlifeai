"""
ASGI entry point: plain HTTP (Django) and WebSocket (video-call signaling, Django Channels).

Run with `python manage.py runserver` (daphne's runserver) or `daphne config.asgi:application`.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Must run before importing anything that touches models (it calls django.setup()).
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator, OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402

from meetings.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    # The Origin header must match ALLOWED_HOSTS and, more strictly, the frontend origins allowed by CORS.
    # Authentication itself is done by the consumer with a short-lived signed ticket.
    "websocket": AllowedHostsOriginValidator(
        OriginValidator(URLRouter(websocket_urlpatterns), settings.CORS_ALLOWED_ORIGINS),
    ),
})
