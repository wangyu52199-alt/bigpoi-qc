from __future__ import annotations

from typing import Any


def bucket_samples(samples: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "historical_high_frequency": [],
        "current_fix_target": [],
        "boundary_cases": [],
    }
    for sample in samples:
        target_bucket = sample.get("bucket")
        if target_bucket in buckets:
            buckets[target_bucket].append(sample)
    return buckets
