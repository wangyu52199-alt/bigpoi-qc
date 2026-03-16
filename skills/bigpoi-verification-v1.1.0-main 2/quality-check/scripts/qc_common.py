#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import string
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UTC_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
UTC_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
TRACKED_FIELDS = ("name", "address", "coordinates", "category", "city", "city_adcode")
ISSUE_SEVERITIES = ("critical", "major", "minor")

_PUNCTUATION_TABLE = str.maketrans("", "", string.whitespace + string.punctuation + "，。；：、（）【】《》“”‘’·")


def ensure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).strftime(UTC_ISO_FORMAT)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime(UTC_STAMP_FORMAT)


def is_iso_time(value: str) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def read_json_file(path: str | Path) -> Any:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    raw = file_path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        raise ValueError(f"JSON file is empty: {file_path}")
    return json.loads(raw)


def write_json_file(data: Any, path: str | Path) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def normalize_input(poi: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(poi)
    if "id" not in normalized and normalized.get("poi_id"):
        normalized["id"] = str(normalized["poi_id"])
    if "coordinates" not in normalized and normalized.get("x_coord") is not None and normalized.get("y_coord") is not None:
        normalized["coordinates"] = {
            "longitude": float(normalized["x_coord"]),
            "latitude": float(normalized["y_coord"]),
            "coordinate_system": "GCJ02",
        }
    return normalized


def normalize_scalar_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def normalize_coordinate_value(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, Any] = {}
    if value.get("longitude") is not None:
        normalized["longitude"] = float(value["longitude"])
    if value.get("latitude") is not None:
        normalized["latitude"] = float(value["latitude"])
    if "longitude" not in normalized or "latitude" not in normalized:
        return None
    return normalized


def values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, dict) or isinstance(right, dict):
        return json.dumps(left or {}, ensure_ascii=False, sort_keys=True) == json.dumps(right or {}, ensure_ascii=False, sort_keys=True)
    return normalize_scalar_value(left) == normalize_scalar_value(right)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().translate(_PUNCTUATION_TABLE)


def haversine_distance_meters(left: dict[str, Any] | None, right: dict[str, Any] | None) -> float | None:
    left_coord = normalize_coordinate_value(left)
    right_coord = normalize_coordinate_value(right)
    if left_coord is None or right_coord is None:
        return None

    lon1 = math.radians(left_coord["longitude"])
    lat1 = math.radians(left_coord["latitude"])
    lon2 = math.radians(right_coord["longitude"])
    lat2 = math.radians(right_coord["latitude"])
    delta_lon = lon2 - lon1
    delta_lat = lat2 - lat1

    a = math.sin(delta_lat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return 6371000.0 * c


def floats_close(left: Any, right: Any, tolerance: float = 1e-4) -> bool:
    if left is None or right is None:
        return False
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def format_change_value(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if value is None:
        return ""
    return str(value)


def source_distribution(evidence: list[dict[str, Any]]) -> dict[str, int]:
    distribution = {
        "official": 0,
        "map_vendor": 0,
        "internet": 0,
        "user_contributed": 0,
        "other": 0,
    }
    for item in evidence:
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        source_type = str(source.get("source_type") or "").strip()
        if source_type in distribution:
            distribution[source_type] += 1
    return distribution


def build_issue(
    severity: str,
    code: str,
    message: str,
    file_role: str,
    field_path: str | None = None,
    suggestion: str | None = None,
) -> dict[str, Any]:
    if severity not in ISSUE_SEVERITIES:
        raise ValueError(f"unsupported issue severity: {severity}")
    issue = {
        "severity": severity,
        "code": code,
        "message": message,
        "file_role": file_role,
    }
    if field_path:
        issue["field_path"] = field_path
    if suggestion:
        issue["suggestion"] = suggestion
    return issue


def get_input_field_value(input_data: dict[str, Any], field: str) -> Any:
    if field == "coordinates":
        return normalize_coordinate_value(input_data.get("coordinates"))
    if field == "category":
        return normalize_scalar_value(input_data.get("poi_type"))
    return normalize_scalar_value(input_data.get(field))


def get_final_field_value(final_values: dict[str, Any], field: str) -> Any:
    if field == "coordinates":
        return normalize_coordinate_value(final_values.get("coordinates"))
    return normalize_scalar_value(final_values.get(field))
