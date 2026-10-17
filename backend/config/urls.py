from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from common.media import serve_media

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/profile/", include("profiles.urls")),
    path("api/learning/", include("learning.urls")),
]
if settings.DEBUG:
    urlpatterns.append(re_path(r"^media/(?P<path>.*)$", serve_media))
