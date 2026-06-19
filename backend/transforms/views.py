"""Endpoints for the LLM + regex replacement workflow.

The workflow is deliberately three-staged so nothing is mutated until the user
confirms:

    generate  -> NL description to a regex (no data touched)
    preview   -> before/after for the chosen column (no commit)
    apply     -> commit the replacement + record history
    undo      -> revert the most recent transformation
"""

from __future__ import annotations

from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from config.exceptions import NotFoundError, ValidationError
from datasets.models import Dataset
from datasets.serializers import page_rows
from datasets.services import storage

from .models import Transformation
from .serializers import (
    CreativeTransformRequest,
    GenerateRegexRequest,
    ReplacementRequest,
    TransformationSerializer,
)
from .services import creative, diffing, llm, regex_engine

# Creative transform kind -> (name of LLM inferer on `llm`, default spec). The
# inferer is resolved via getattr at call time so it stays easily patchable.
_CREATIVE = {
    "dates": ("infer_date_spec", creative.DEFAULT_DATE_SPEC),
    "phones": ("infer_phone_spec", creative.DEFAULT_PHONE_SPEC),
}


def _get_dataset(dataset_id) -> Dataset:
    try:
        dataset = Dataset.objects.get(pk=dataset_id)
    except (Dataset.DoesNotExist, ValueError, TypeError) as exc:
        raise NotFoundError("Upload not found.") from exc
    if dataset.is_expired:
        raise NotFoundError("This upload has expired.")
    return dataset


def _require_text_column(dataset: Dataset, column: str) -> None:
    names = [c["name"] for c in dataset.columns]
    if column not in names:
        raise ValidationError(f"Column '{column}' does not exist in this dataset.")
    if column not in dataset.text_columns:
        raise ValidationError(
            f"Column '{column}' is not a text column and cannot be pattern-replaced."
        )


@api_view(["POST"])
def generate_regex(request):
    """Convert a natural-language description into a regex (no mutation).

    If a dataset_id + column are supplied, real values from that column are sent
    to the LLM as grounding context and used to produce sample matches.
    """
    body = GenerateRegexRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data

    samples = list(data.get("sample_values") or [])
    if not samples and data.get("dataset_id") and data.get("column"):
        dataset = _get_dataset(data["dataset_id"])
        _require_text_column(dataset, data["column"])
        series = storage.load_dataframe(dataset.id)[data["column"]].dropna()
        samples = [str(v) for v in series.head(10).tolist()]

    result = llm.generate_regex(data["description"], samples)

    # Validate compilability + produce concrete evidence of what it matches.
    regex_engine.compile_pattern(result.regex, result.flags)
    sample_matches = regex_engine.find_sample_matches(samples, result.regex, result.flags)

    return Response(
        {
            "regex": result.regex,
            "flags": result.flags,
            "explanation": result.explanation,
            "confidence": result.confidence,
            "sample_matches": sample_matches,
        }
    )


@api_view(["POST"])
def preview(request, dataset_id):
    """Compute before/after for a replacement without committing it."""
    dataset = _get_dataset(dataset_id)
    body = ReplacementRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    _require_text_column(dataset, data["column"])

    df = storage.load_dataframe(dataset.id)
    column = data["column"]
    result = regex_engine.apply_replacement(
        df[column], data["regex"], data["replacement"], data.get("flags")
    )

    diffs = diffing.build_diffs(df[column], result.new_series)
    return Response(
        {
            "column": column,
            "match_count": result.match_count,
            "changed_count": result.changed_count,
            **_page_diffs(request, diffs),
        }
    )


@api_view(["POST"])
def apply(request, dataset_id):
    """Commit a replacement: overwrite stored data + record a Transformation."""
    dataset = _get_dataset(dataset_id)
    body = ReplacementRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    _require_text_column(dataset, data["column"])

    df = storage.load_dataframe(dataset.id)
    column = data["column"]
    result = regex_engine.apply_replacement(
        df[column], data["regex"], data["replacement"], data.get("flags")
    )

    with transaction.atomic():
        record = Transformation.objects.create(
            dataset=dataset,
            column=column,
            nl_description=data.get("description", ""),
            regex_pattern=data["regex"],
            flags=data.get("flags", "") or "",
            replacement=data["replacement"],
            match_count=result.match_count,
        )
        # Snapshot pre-apply state for undo, then commit the new data.
        storage.save_backup(dataset.id, record.id, df)
        df[column] = result.new_series
        storage.save_dataframe(dataset.id, df)

    page = int(request.query_params.get("page", 1))
    size = int(request.query_params.get("size", 50))
    return Response(
        {
            "transformation": TransformationSerializer(record).data,
            "match_count": result.match_count,
            "changed_count": result.changed_count,
            **page_rows(df, page=page, size=size),
        },
        status=201,
    )


@api_view(["GET"])
def transformations(request, dataset_id):
    """List the transformation history for a dataset."""
    dataset = _get_dataset(dataset_id)
    qs = dataset.transformations.all()
    return Response(TransformationSerializer(qs, many=True).data)


@api_view(["POST"])
def undo(request, dataset_id, transform_id):
    """Revert the most recent (not-yet-undone) transformation."""
    dataset = _get_dataset(dataset_id)
    try:
        record = dataset.transformations.get(pk=transform_id, is_undone=False)
    except Transformation.DoesNotExist as exc:
        raise NotFoundError("Transformation not found or already undone.") from exc

    latest = dataset.transformations.filter(is_undone=False).last()
    if latest is None or record.id != latest.id:
        raise ValidationError("Only the most recent transformation can be undone.")

    with transaction.atomic():
        df = storage.restore_backup(dataset.id, record.id)
        record.is_undone = True
        record.save(update_fields=["is_undone"])

    page = int(request.query_params.get("page", 1))
    size = int(request.query_params.get("size", 50))
    return Response(
        {
            "undone": str(record.id),
            **page_rows(df, page=page, size=size),
        }
    )


def _page_diffs(request, diffs: list[dict]) -> dict:
    """Slice a list of diffs into a page using the request's page/size params."""
    page = max(int(request.query_params.get("page", 1)), 1)
    size = int(request.query_params.get("size", 50))
    start = (page - 1) * size
    return {
        "diffs": diffs[start : start + size],
        "page": page,
        "size": size,
        "total_changed": len(diffs),
    }


def _resolve_creative_spec(kind, data, dataset):
    """Return the spec to apply for a creative transform.

    Uses caller-supplied ``params`` if present (skipping the LLM); otherwise asks
    the LLM to infer the spec from the description + column samples.
    """
    infer_name, default_spec = _CREATIVE[kind]
    params = data.get("params") or {}
    if params:
        spec = {**default_spec, **params}
        spec["source"] = "user"
        return spec

    series = storage.load_dataframe(dataset.id)[data["column"]].dropna()
    samples = [str(v) for v in series.head(10).tolist()]
    infer = getattr(llm, infer_name)
    spec = infer(data.get("description", ""), samples)
    spec["source"] = "llm"
    return spec


@api_view(["POST"])
def creative_preview(request, dataset_id, kind):
    """Preview a date/phone transform (no commit)."""
    if kind not in _CREATIVE:
        raise ValidationError(f"Unknown transform kind: '{kind}'.")
    dataset = _get_dataset(dataset_id)
    body = CreativeTransformRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    _require_text_column(dataset, data["column"])

    spec = _resolve_creative_spec(kind, data, dataset)
    df = storage.load_dataframe(dataset.id)
    result = creative.apply(kind, df[data["column"]], spec)

    diffs = diffing.build_diffs(df[data["column"]], result.new_series)
    return Response(
        {
            "kind": kind,
            "column": data["column"],
            "spec": spec,
            "info": result.info,
            "changed_count": result.changed_count,
            **_page_diffs(request, diffs),
        }
    )


@api_view(["POST"])
def creative_apply(request, dataset_id, kind):
    """Commit a date/phone transform + record a Transformation (undoable)."""
    if kind not in _CREATIVE:
        raise ValidationError(f"Unknown transform kind: '{kind}'.")
    dataset = _get_dataset(dataset_id)
    body = CreativeTransformRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    _require_text_column(dataset, data["column"])

    spec = _resolve_creative_spec(kind, data, dataset)
    df = storage.load_dataframe(dataset.id)
    column = data["column"]
    result = creative.apply(kind, df[column], spec)

    with transaction.atomic():
        record = Transformation.objects.create(
            dataset=dataset,
            kind=kind,
            column=column,
            nl_description=data.get("description", ""),
            params=spec,
            match_count=result.changed_count,
        )
        storage.save_backup(dataset.id, record.id, df)
        df[column] = result.new_series
        storage.save_dataframe(dataset.id, df)

    page = int(request.query_params.get("page", 1))
    size = int(request.query_params.get("size", 50))
    return Response(
        {
            "transformation": TransformationSerializer(record).data,
            "info": result.info,
            "changed_count": result.changed_count,
            **page_rows(df, page=page, size=size),
        },
        status=201,
    )
