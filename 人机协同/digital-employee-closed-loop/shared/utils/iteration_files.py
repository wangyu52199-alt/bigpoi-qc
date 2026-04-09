from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False))
        f.write("\n")


def append_markdown(path: Path, text: str) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        if path.exists() and path.stat().st_size > 0:
            f.write("\n")
        f.write(text.rstrip() + "\n")


def append_yaml_rule(path: Path, key: str, rule_obj: dict[str, Any]) -> None:
    ensure_parent(path)
    data: dict[str, Any]
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        data = loaded if isinstance(loaded, dict) else {}
    else:
        data = {}

    bucket = data.get(key)
    if not isinstance(bucket, list):
        bucket = []

    rule_id = str(rule_obj.get("id", ""))
    exists = any(isinstance(item, dict) and str(item.get("id", "")) == rule_id for item in bucket)
    if not exists:
        bucket.append(rule_obj)

    data[key] = bucket
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
