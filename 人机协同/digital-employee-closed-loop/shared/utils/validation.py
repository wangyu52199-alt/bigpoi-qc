from __future__ import annotations

from typing import Any

from shared.schemas import ManualResultInput


def validate_manual_result(payload: dict[str, Any]) -> ManualResultInput:
    return ManualResultInput.model_validate(payload)
