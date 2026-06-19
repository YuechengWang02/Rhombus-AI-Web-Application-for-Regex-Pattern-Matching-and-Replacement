"""URL routes for the datasets app (mounted under /api/)."""

from django.urls import path

from . import views

urlpatterns = [
    path("uploads/", views.upload, name="upload"),
    path("uploads/<uuid:dataset_id>/", views.dataset_detail, name="dataset-detail"),
    path("uploads/<uuid:dataset_id>/rows/", views.rows, name="dataset-rows"),
    path("uploads/<uuid:dataset_id>/download/", views.download, name="dataset-download"),
]
