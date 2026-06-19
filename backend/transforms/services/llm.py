"""LLM integration: convert a natural-language description into a regex.

The provider (Anthropic Claude) is isolated behind :func:`generate_regex` so it
can be swapped without touching the views or regex logic. The model is asked to
return strict JSON, which we parse and validate; the returned pattern is always
re-compiled by the caller (``regex_engine``) before use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from django.conf import settings

from config.exceptions import LLMError, UnprocessableError

SYSTEM_PROMPT = """\
You convert natural-language data-cleaning requests into a single regular \
expression compatible with Python's `re`/`regex` modules.

Rules:
- Output ONLY a JSON object, no prose, no code fences.
- The JSON has keys: "regex" (string), "flags" (string of letters from i,m,s,x; \
may be empty), "explanation" (one plain-English sentence), "confidence" (0..1).
- The "regex" must be a valid pattern. Do not anchor with ^/$ unless the request \
clearly implies whole-cell matching.
- Prefer precise, well-known patterns (emails, phone numbers, dates, URLs, \
whitespace, digits) over overly broad ones.
- Never include the replacement value in the regex.

Examples:
Request: "find email addresses"
{"regex": "\\\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,7}\\\\b", "flags": "", "explanation": "Matches standard email addresses.", "confidence": 0.95}

Request: "match phone numbers like 123-456-7890"
{"regex": "\\\\b\\\\d{3}[-.\\\\s]?\\\\d{3}[-.\\\\s]?\\\\d{4}\\\\b", "flags": "", "explanation": "Matches 10-digit phone numbers with optional separators.", "confidence": 0.9}

Request: "collapse multiple spaces"
{"regex": "\\\\s{2,}", "flags": "", "explanation": "Matches runs of two or more whitespace characters.", "confidence": 0.92}
"""


@dataclass
class RegexResult:
    regex: str
    flags: str
    explanation: str
    confidence: float


def _build_user_message(description: str, samples: list[str] | None) -> str:
    parts = [f'Request: "{description.strip()}"']
    if samples:
        cleaned = [str(s) for s in samples if s is not None][:10]
        if cleaned:
            parts.append("Sample values from the target column:")
            parts.extend(f"- {value}" for value in cleaned)
    return "\n".join(parts)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of the model's text response."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model output.")
    return json.loads(text[start : end + 1])


def _parse_result(payload: dict) -> RegexResult:
    pattern = payload.get("regex")
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("Model output missing a 'regex' string.")
    flags = payload.get("flags") or ""
    explanation = payload.get("explanation") or ""
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return RegexResult(
        regex=pattern,
        flags="".join(ch for ch in str(flags).lower() if ch in "imsx"),
        explanation=str(explanation),
        confidence=max(0.0, min(confidence, 1.0)),
    )


DATE_SPEC_PROMPT = """\
You configure a date-standardization step for a spreadsheet column.

Given a natural-language instruction and sample values, output ONLY a JSON \
object (no prose, no code fences) with keys:
- "dayfirst" (boolean): true if dates are day-first (e.g. DD/MM/YYYY).
- "target_format" (string): a Python strftime format for the desired output \
(default "%Y-%m-%d").
- "explanation" (string): one plain-English sentence.

Infer day-first vs month-first from the samples when ambiguous (e.g. values \
greater than 12 in the first position imply day-first).
"""

PHONE_SPEC_PROMPT = """\
You configure a phone-number normalization step for a spreadsheet column.

Given a natural-language instruction and sample values, output ONLY a JSON \
object (no prose, no code fences) with keys:
- "target_format" (string): one of "e164" (+15551234567), "dashes" \
(555-123-4567), or "parens" ((555) 123-4567). Default "e164".
- "default_country_code" (string): digits only, e.g. "1" for US/Canada. Use \
"1" if unspecified.
- "explanation" (string): one plain-English sentence.
"""


def _complete_json(client, system_prompt: str, user_message: str) -> dict:
    """Run one completion that must return a JSON object; retry once."""
    message_text = user_message
    last_error: Exception | None = None
    for _ in range(2):
        try:
            message = client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=400,
                system=system_prompt,
                messages=[{"role": "user", "content": message_text}],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Failed to reach the language model: {exc}") from exc
        text = "".join(
            b.text for b in message.content if getattr(b, "type", "") == "text"
        )
        try:
            return _extract_json(text)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            message_text = f"{user_message}\n\nReturn ONLY the JSON object, nothing else."
    raise LLMError(f"The language model returned an unusable response. ({last_error})")


def infer_date_spec(description: str, samples: list[str] | None = None) -> dict:
    """Infer a date-standardization spec (dayfirst/target_format) via the LLM."""
    payload = _complete_json(
        _client(), DATE_SPEC_PROMPT, _build_user_message(description or "standardize dates", samples)
    )
    return {
        "dayfirst": bool(payload.get("dayfirst", False)),
        "target_format": str(payload.get("target_format") or "%Y-%m-%d"),
        "explanation": str(payload.get("explanation") or ""),
    }


def infer_phone_spec(description: str, samples: list[str] | None = None) -> dict:
    """Infer a phone-normalization spec (target_format/country) via the LLM."""
    payload = _complete_json(
        _client(),
        PHONE_SPEC_PROMPT,
        _build_user_message(description or "normalize phone numbers", samples),
    )
    fmt = str(payload.get("target_format") or "e164").lower()
    if fmt not in {"e164", "dashes", "parens"}:
        fmt = "e164"
    cc = "".join(ch for ch in str(payload.get("default_country_code") or "1") if ch.isdigit())
    return {
        "target_format": fmt,
        "default_country_code": cc or "1",
        "explanation": str(payload.get("explanation") or ""),
    }


def _client():
    """Build the Anthropic client, or raise a clear config error."""
    if not settings.ANTHROPIC_API_KEY:
        raise LLMError(
            "LLM is not configured. Set ANTHROPIC_API_KEY in the environment."
        )
    # Imported lazily so the app boots even if the SDK/key is absent.
    import anthropic

    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def generate_regex(description: str, samples: list[str] | None = None) -> RegexResult:
    """Convert *description* into a :class:`RegexResult` using Claude.

    Retries once if the model returns malformed JSON. Raises ``UnprocessableError``
    if the description is empty, or ``LLMError`` on provider/parse failure.
    """
    if not description or not description.strip():
        raise UnprocessableError("Please describe the pattern you want to match.")

    client = _client()
    user_message = _build_user_message(description, samples)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            message = client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=400,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:  # noqa: BLE001 - provider/network errors
            raise LLMError(f"Failed to reach the language model: {exc}") from exc

        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        try:
            return _parse_result(_extract_json(text))
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            # On the retry, nudge the model to return strict JSON only.
            user_message = (
                f"{user_message}\n\nReturn ONLY the JSON object described, nothing else."
            )

    raise LLMError(
        f"The language model did not return a usable regex. ({last_error})"
    )
