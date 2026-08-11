"""Central HTTP/JSON UTF-8 utilities for HWK Stock.

All Android-side services should decode JSON responses through this module
instead of using ``response.json()`` or ``response.text`` directly.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import requests


class JsonResponseError(ValueError):
    """Raised when an HTTP response does not contain a valid JSON object."""


def _repair_thai_mojibake(text: str) -> str:
    """Best-effort repair for UTF-8 Thai bytes decoded as TIS-620/Windows-874.

    Correct Unicode text is returned unchanged. Repair is applied only when
    typical mojibake markers are present and the conversion succeeds.
    """
    value = str(text or "")
    if not value:
        return value

    # UTF-8 Thai incorrectly decoded as TIS-620 commonly starts with these
    # syllable-like fragments and may contain C1 control characters.
    suspicious = (
        "เธ" in value
        or "เน" in value
        or any("\x80" <= ch <= "\x9f" for ch in value)
        or "à¸" in value
        or "à¹" in value
    )
    if not suspicious:
        return value

    candidates = []
    for encoding in ("tis-620", "latin-1", "cp1252"):
        try:
            candidates.append(value.encode(encoding).decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

    # Prefer a repaired string that contains Thai characters and fewer common
    # mojibake fragments/control characters than the original.
    def quality(candidate: str) -> tuple[int, int, int]:
        bad_count = (
            candidate.count("à¸")
            + candidate.count("à¹")
            + sum("\x80" <= ch <= "\x9f" for ch in candidate)
        )
        thai_count = sum("\u0e00" <= ch <= "\u0e7f" for ch in candidate)
        # Fewer mojibake/control markers is the strongest signal. Thai content
        # is the second signal; shorter text is used only as a tie-breaker.
        return (-bad_count, thai_count, -len(candidate))

    if candidates:
        best = max(candidates, key=quality)
        if quality(best) > quality(value):
            return best
    return value


def normalize_text(value: Any) -> str:
    """Return readable Unicode text, including best-effort Thai repair."""
    return _repair_thai_mojibake(str(value or ""))


def normalize_json_strings(value: Any) -> Any:
    """Recursively normalize every string inside decoded JSON data."""
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {
            normalize_text(key) if isinstance(key, str) else key:
            normalize_json_strings(item)
            for key, item in value.items()
        }
    return value


def decode_response_text(response: requests.Response) -> str:
    """Decode response bytes deterministically, preferring UTF-8."""
    raw = response.content or b""
    if not raw:
        return ""

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return normalize_text(raw.decode(encoding))
        except UnicodeDecodeError:
            pass

    # Legacy fallback only. Never rely on Requests' guessed response.encoding.
    for encoding in ("tis-620", "cp874", "cp1252", "latin-1"):
        try:
            return normalize_text(raw.decode(encoding))
        except UnicodeDecodeError:
            pass

    return normalize_text(raw.decode("utf-8", errors="replace"))


def decode_json_response(
    response: requests.Response,
    *,
    require_object: bool = True,
) -> Any:
    """Decode an HTTP JSON response through the central UTF-8 policy."""
    text = decode_response_text(response).strip()
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        sample = text[:500] + ("..." if len(text) > 500 else "")
        raise JsonResponseError(
            "Server ไม่ได้ส่งข้อมูล JSON ที่ถูกต้อง"
            + (f"\nResponse: {sample}" if sample else "")
        ) from exc

    data = normalize_json_strings(data)
    if require_object and not isinstance(data, dict):
        raise JsonResponseError("ข้อมูลหลักจาก Server ต้องเป็น JSON Object")
    return data


def build_server_error(data: Dict[str, Any], fallback: str = "Server Error") -> str:
    """Combine server message and error fields without losing diagnostics."""
    message = normalize_text(data.get("message")).strip()
    error = normalize_text(data.get("error")).strip()
    if message and error and message != error:
        return f"{message}\n{error}"
    return error or message or fallback
