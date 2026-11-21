from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.EmailMessageViewSet, basename="email")

urlpatterns = [
    path("gmail/status/", views.GmailStatusView.as_view(), name="gmail-status"),
    path("gmail/connect/", views.GmailConnectView.as_view(), name="gmail-connect"),
    path("gmail/callback/", views.GmailCallbackView.as_view(), name="gmail-callback"),
    path("gmail/sync/", views.GmailSyncView.as_view(), name="gmail-sync"),
    path("gmail/disconnect/", views.GmailDisconnectView.as_view(), name="gmail-disconnect"),
    path("", include(router.urls)),
]
