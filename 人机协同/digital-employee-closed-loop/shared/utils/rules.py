from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class RuleConfigError(ValueError):
    pass


def load_rule_config(path: str | Path) -> list[dict[str, Any]]:
    rule_path = Path(path)
    if not rule_path.exists():
        raise RuleConfigError(f"Rule file not found: {rule_path}")

    data = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "rules" not in data:
        raise RuleConfigError("Rule file must be a dict with 'rules' key")

    rules = data["rules"]
    if not isinstance(rules, list):
        raise RuleConfigError("'rules' must be a list")

    validated: list[dict[str, Any]] = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise RuleConfigError(f"Rule at index {idx} must be a dict")
        for required in ("id", "priority", "target"):
            if required not in rule:
                raise RuleConfigError(f"Rule {idx} missing required field: {required}")
        validated.append(rule)

    return sorted(validated, key=lambda r: int(r.get("priority", 0)), reverse=True)
