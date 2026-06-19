"""Request/response serializers for the transforms app."""

from __future__ import annotations

from rest_framework import serializers

from .models import Transformation


class GenerateRegexRequest(serializers.Serializer):
    """Body for POST /api/regex/generate/."""

    description = serializers.CharField(max_length=2000)
    # Optional columns to pull grounding samples from, plus the dataset.
    dataset_id = serializers.UUIDField(required=False)
    columns = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    sample_values = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        max_length=20,
    )


class ReplacementRequest(serializers.Serializer):
    """Body for preview/apply: target columns + regex + replacement.

    ``columns`` is optional — an empty/omitted list means "all text columns".
    """

    columns = serializers.ListField(child=serializers.CharField(), required=False)
    regex = serializers.CharField(max_length=2000)
    flags = serializers.CharField(required=False, allow_blank=True, max_length=8)
    replacement = serializers.CharField(required=False, allow_blank=True, default="")
    # Carried through to history when applying (optional).
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=2000
    )


class CreativeTransformRequest(serializers.Serializer):
    """Body for the date/phone transforms.

    Either provide a natural-language ``description`` (the LLM infers the spec)
    and/or an explicit ``params`` object to override/skip inference. ``columns``
    is optional — an empty/omitted list means "all text columns".
    """

    columns = serializers.ListField(child=serializers.CharField(), required=False)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=2000
    )
    params = serializers.DictField(required=False)


class TransformationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transformation
        fields = [
            "id",
            "kind",
            "columns",
            "nl_description",
            "regex_pattern",
            "flags",
            "replacement",
            "params",
            "match_count",
            "is_undone",
            "created_at",
        ]
