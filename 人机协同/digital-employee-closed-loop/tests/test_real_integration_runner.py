from __future__ import annotations

import json
from pathlib import Path


def test_integration_targets_config_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    target_cfg = root / "integrations" / "targets.yaml"
    assert target_cfg.exists()


def test_integration_output_generated() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "integration-output" / "last_integration_result.json"
    assert output.exists()

    data = json.loads(output.read_text(encoding="utf-8"))
    assert "first_routing_result" in data
    assert "per_target" in data
