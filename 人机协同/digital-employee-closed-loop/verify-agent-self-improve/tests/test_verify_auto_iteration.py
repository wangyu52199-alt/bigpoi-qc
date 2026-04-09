from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[0]
sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location("verify_iter_engine", MODULE_ROOT / "src" / "iter_engine.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
run_verify_auto_iteration = module.run_verify_auto_iteration


def _load_example(name: str) -> dict:
    return json.loads((MODULE_ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_verify_auto_iteration_dry_run(tmp_path: Path) -> None:
    improvement = _load_example("improvement_record.json")
    second = _load_example("second_routing_result_for_iter.json")

    target_skill_path = tmp_path / "verify_skill"
    result = run_verify_auto_iteration(
        improvement_payload=improvement,
        second_routing_payload=second,
        target_skill_path=target_skill_path,
        config_path=MODULE_ROOT / "config" / "auto_iteration_config.yaml",
        dry_run=True,
    )

    assert result.applied is False
    assert len(result.operations) == 3
    assert not (target_skill_path / "config" / "verify_rules.yaml").exists()


def test_verify_auto_iteration_apply(tmp_path: Path) -> None:
    improvement = _load_example("improvement_record.json")
    second = _load_example("second_routing_result_for_iter.json")

    target_skill_path = tmp_path / "verify_skill"
    result = run_verify_auto_iteration(
        improvement_payload=improvement,
        second_routing_payload=second,
        target_skill_path=target_skill_path,
        config_path=MODULE_ROOT / "config" / "auto_iteration_config.yaml",
        dry_run=False,
    )

    assert result.applied is True
    assert (target_skill_path / "config" / "verify_rules.yaml").exists()
    assert (target_skill_path / "regression" / "current_fix_target.jsonl").exists()
    assert (target_skill_path / "changelog" / "auto_iteration.md").exists()
