"""Endpoints for the LLM + regex replacement workflow.

The workflow is deliberately three-staged so nothing is mutated until the user
confirms:

    generate  -> NL description to a regex (no data touched)
    preview   -> before/after across the target columns (no commit)
    apply     -> commit the replacement + record history
    undo      -> revert the most recent transformation

Operations apply to **one or more** text columns. An empty/omitted ``columns``
list means "all text columns" — safe for redaction since columns that don't
match the pattern simply produce zero changes.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
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


def _resolve_columns(dataset: Dataset, requested) -> list[str]:
    """Return the text columns to operate on.

    A non-empty ``requested`` list is validated (each must exist and be a text
    column). An empty/omitted list resolves to *all* text columns.
    """
    text_cols = dataset.text_columns
    all_names = [c["name"] for c in dataset.columns]
    if requested:
        for col in requested:
            if col not in all_names:
                raise ValidationError(f"Column '{col}' does not exist in this dataset.")
            if col not in text_cols:
                raise ValidationError(
                    f"Column '{col}' is not a text column and cannot be transformed."
                )
        return list(requested)
    if not text_cols:
        raise ValidationError("This file has no text columns to apply to.")
    return text_cols


# An op takes a column Series and returns (new_series, match_count, changed_count).
ColumnOp = Callable[[pd.Series], tuple[pd.Series, int, int]]


def _run_over_columns(df: pd.DataFrame, columns: list[str], op: ColumnOp):
    """Apply ``op`` to each column; collect new series, totals, and tagged diffs."""
    assignments: dict[str, pd.Series] = {}
    total_match = 0
    total_changed = 0
    diffs: list[dict] = []
    for col in columns:
        new_series, matches, changed = op(df[col])
        assignments[col] = new_series
        total_match += matches
        total_changed += changed
        for d in diffing.build_diffs(df[col], new_series):
            d["column"] = col
            diffs.append(d)
    diffs.sort(key=lambda d: (d["row"], d["column"]))
    return assignments, total_match, total_changed, diffs


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


def _grounding_samples(dataset: Dataset, columns: list[str], per_col=5, cap=15) -> list[str]:
    """Collect a handful of real cell values across columns for LLM grounding."""
    df = storage.load_dataframe(dataset.id)
    samples: list[str] = []
    for col in columns:
        if col in df.columns:
            samples.extend(str(v) for v in df[col].dropna().head(per_col).tolist())
            if len(samples) >= cap:
                break
    return samples[:cap]


@api_view(["POST"])
def generate_regex(request):
    """Convert a natural-language description into a regex (no mutation).

    If a dataset_id is supplied, real values from the target columns are sent to
    the LLM as grounding context and used to produce sample matches.
    """
    body = GenerateRegexRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data

    samples = list(data.get("sample_values") or [])
    if not samples and data.get("dataset_id"):
        dataset = _get_dataset(data["dataset_id"])
        columns = _resolve_columns(dataset, data.get("columns"))
        samples = _grounding_samples(dataset, columns)

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


def _regex_op(data) -> ColumnOp:
    def op(series: pd.Series):
        r = regex_engine.apply_replacement(
            series, data["regex"], data["replacement"], data.get("flags")
        )
        return r.new_series, r.match_count, r.changed_count

    return op


@api_view(["POST"])
def preview(request, dataset_id):
    """Compute before/after for a replacement across the target columns (no commit)."""
    dataset = _get_dataset(dataset_id)
    body = ReplacementRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    columns = _resolve_columns(dataset, data.get("columns"))

    df = storage.load_dataframe(dataset.id)
    _, total_match, total_changed, diffs = _run_over_columns(df, columns, _regex_op(data))

    return Response(
        {
            "columns": columns,
            "match_count": total_match,
            "changed_count": total_changed,
            **_page_diffs(request, diffs),
        }
    )


@api_view(["POST"])
def apply(request, dataset_id):
    """Commit a replacement across the target columns + record a Transformation."""
    dataset = _get_dataset(dataset_id)
    body = ReplacementRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    columns = _resolve_columns(dataset, data.get("columns"))

    df = storage.load_dataframe(dataset.id)
    assignments, total_match, total_changed, _ = _run_over_columns(
        df, columns, _regex_op(data)
    )

    with transaction.atomic():
        record = Transformation.objects.create(
            dataset=dataset,
            columns=columns,
            nl_description=data.get("description", ""),
            regex_pattern=data["regex"],
            flags=data.get("flags", "") or "",
            replacement=data["replacement"],
            match_count=total_match,
        )
        # Snapshot pre-apply state for undo, then commit every changed column.
        storage.save_backup(dataset.id, record.id, df)
        for col, series in assignments.items():
            df[col] = series
        storage.save_dataframe(dataset.id, df)

    page = int(request.query_params.get("page", 1))
    size = int(request.query_params.get("size", 50))
    return Response(
        {
            "transformation": TransformationSerializer(record).data,
            "match_count": total_match,
            "changed_count": total_changed,
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


def _resolve_creative_spec(kind, columns, dataset, data):
    """Return the spec to apply for a creative transform.

    Uses caller-supplied ``params`` if present (skipping the LLM); otherwise asks
    the LLM to infer the spec from the description + samples across the columns.
    """
    infer_name, default_spec = _CREATIVE[kind]
    params = data.get("params") or {}
    if params:
        spec = {**default_spec, **params}
        spec["source"] = "user"
        return spec

    samples = _grounding_samples(dataset, columns)
    infer = getattr(llm, infer_name)
    spec = infer(data.get("description", ""), samples)
    spec["source"] = "llm"
    return spec


def _creative_op(kind, spec) -> ColumnOp:
    def op(series: pd.Series):
        res = creative.apply(kind, series, spec)
        # Creative transforms report changed cells (no separate "match" count).
        return res.new_series, res.changed_count, res.changed_count

    return op


@api_view(["POST"])
def creative_preview(request, dataset_id, kind):
    """Preview a date/phone transform across the target columns (no commit)."""
    if kind not in _CREATIVE:
        raise ValidationError(f"Unknown transform kind: '{kind}'.")
    dataset = _get_dataset(dataset_id)
    body = CreativeTransformRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    columns = _resolve_columns(dataset, data.get("columns"))

    spec = _resolve_creative_spec(kind, columns, dataset, data)
    df = storage.load_dataframe(dataset.id)
    _, _, total_changed, diffs = _run_over_columns(df, columns, _creative_op(kind, spec))

    return Response(
        {
            "kind": kind,
            "columns": columns,
            "spec": spec,
            "info": {"applied_to": columns},
            "changed_count": total_changed,
            **_page_diffs(request, diffs),
        }
    )


@api_view(["POST"])
def creative_apply(request, dataset_id, kind):
    """Commit a date/phone transform across the target columns (undoable)."""
    if kind not in _CREATIVE:
        raise ValidationError(f"Unknown transform kind: '{kind}'.")
    dataset = _get_dataset(dataset_id)
    body = CreativeTransformRequest(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    columns = _resolve_columns(dataset, data.get("columns"))

    spec = _resolve_creative_spec(kind, columns, dataset, data)
    df = storage.load_dataframe(dataset.id)
    assignments, _, total_changed, _ = _run_over_columns(
        df, columns, _creative_op(kind, spec)
    )

    with transaction.atomic():
        record = Transformation.objects.create(
            dataset=dataset,
            kind=kind,
            columns=columns,
            nl_description=data.get("description", ""),
            params=spec,
            match_count=total_changed,
        )
        storage.save_backup(dataset.id, record.id, df)
        for col, series in assignments.items():
            df[col] = series
        storage.save_dataframe(dataset.id, df)

    page = int(request.query_params.get("page", 1))
    size = int(request.query_params.get("size", 50))
    return Response(
        {
            "transformation": TransformationSerializer(record).data,
            "info": {"applied_to": columns},
            "changed_count": total_changed,
            **page_rows(df, page=page, size=size),
        },
        status=201,
    )
