"""Root URL configuration.

All application endpoints live under ``/api/``. A lightweight ``/api/health/``
check is provided for deployment probes.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("datasets.urls")),
    path("api/", include("transforms.urls")),
]
