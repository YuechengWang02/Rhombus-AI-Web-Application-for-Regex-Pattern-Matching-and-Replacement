"""HTTP endpoints for uploading, browsing, and downloading datasets.

Views stay thin: request parsing + validation here, real work delegated to the
``services`` layer (``file_io``, ``storage``).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from config.exceptions import NotFoundError, ValidationError

from .models import Dataset
from .serializers import DatasetSerializer, page_rows
from .services import file_io, storage


def _get_dataset(dataset_id) -> Dataset:
    try:
        dataset = Dataset.objects.get(pk=dataset_id)
    except (Dataset.DoesNotExist, ValueError, TypeError) as exc:
        raise NotFoundError("Upload not found.") from exc
    if dataset.is_expired:
        raise NotFoundError("This upload has expired.")
    return dataset


@api_view(["POST"])
@parser_classes([MultiPartParser])
def upload(request):
    """Accept a CSV/Excel upload, parse it, and persist a parquet snapshot.

    Returns dataset metadata plus the first page of rows so the frontend can
    render the grid immediately.
    """
    file_obj = request.FILES.get("file")
    if file_obj is None:
        raise ValidationError("No file provided. Send a file under the 'file' field.")

    if file_obj.size > settings.MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File too large. Maximum size is {settings.MAX_UPLOAD_MB} MB."
        )

    parsed = file_io.parse_upload(file_obj.name, file_obj.read())

    dataset = Dataset.objects.create(
        original_filename=file_obj.name,
        file_type=parsed.file_type,
        row_count=parsed.row_count,
        columns=parsed.columns,
        storage_path="",  # set after we know the id-based path
    )
    dataset.storage_path = storage.save_dataframe(dataset.id, parsed.dataframe)
    dataset.save(update_fields=["storage_path"])

    size = int(request.query_params.get("size", 50))
    return Response(
        {
            "dataset": DatasetSerializer(dataset).data,
            **page_rows(parsed.dataframe, page=1, size=size),
        },
        status=201,
    )


@api_view(["GET"])
def dataset_detail(request, dataset_id):
    """Return metadata for a single dataset."""
    dataset = _get_dataset(dataset_id)
    return Response(DatasetSerializer(dataset).data)


@api_view(["GET"])
def rows(request, dataset_id):
    """Return a paginated page of the dataset's current rows."""
    dataset = _get_dataset(dataset_id)
    df = storage.load_dataframe(dataset.id)
    page = int(request.query_params.get("page", 1))
    size = int(request.query_params.get("size", 50))
    return Response(page_rows(df, page=page, size=size))


@api_view(["GET"])
def download(request, dataset_id):
    """Stream the current (possibly transformed) dataset as CSV or Excel."""
    dataset = _get_dataset(dataset_id)
    fmt = request.query_params.get("format", "csv").lower()
    df = storage.load_dataframe(dataset.id)

    content, content_type = file_io.dataframe_to_bytes(df, fmt)
    stem = dataset.original_filename.rsplit(".", 1)[0]
    filename = f"{stem}_processed.{fmt}"

    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
