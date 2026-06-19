"""URL routes for the transforms app (mounted under /api/)."""

from django.urls import path

from . import views

urlpatterns = [
    path("regex/generate/", views.generate_regex, name="regex-generate"),
    path("uploads/<uuid:dataset_id>/preview/", views.preview, name="replace-preview"),
    path("uploads/<uuid:dataset_id>/apply/", views.apply, name="replace-apply"),
    path(
        "uploads/<uuid:dataset_id>/transform/<str:kind>/preview/",
        views.creative_preview,
        name="creative-preview",
    ),
    path(
        "uploads/<uuid:dataset_id>/transform/<str:kind>/apply/",
        views.creative_apply,
        name="creative-apply",
    ),
    path(
        "uploads/<uuid:dataset_id>/transforms/",
        views.transformations,
        name="transform-list",
    ),
    path(
        "uploads/<uuid:dataset_id>/transforms/<uuid:transform_id>/undo/",
        views.undo,
        name="transform-undo",
    ),
]
