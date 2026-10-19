"""Offline, privacy-preserving CLI validation contract for HR-labeled data."""
from __future__ import annotations

import json

import pytest

from app.diagnosis.calibration import candidate_scenarios, score_match
from scripts.evaluate_hr_dataset import evaluate_file


def _fixture_cases():
    cases = []
    for i, scenario in enumerate(candidate_scenarios()[:32]):
        resume = scenario["resume"].model_copy(deep=True)
        resume.name = f"Synthetic Person {i}"
        resume.additional.append(f"unique synthetic scenario {i}")
        baseline = score_match(resume, scenario["target"])["score"]
        cases.append({
            "case_id": f"synthetic_{i}",
            "split": "train" if i % 4 != 0 else "test",
            "resume": resume.model_dump(),
            "target": scenario["target"].model_dump(),
            "reviewer_scores": [max(0, baseline - 2), min(100, baseline + 2)],
        })
    return cases


def test_cli_prints_only_aggregate_metrics_no_raw_resume_or_names(tmp_path):
    file = tmp_path / "private_labels.json"
    file.write_text(json.dumps({"cases": _fixture_cases()}, ensure_ascii=False), encoding="utf-8")
    summary = evaluate_file(file)
    assert summary["dataset"]["case_count"] == 32
    assert summary["dataset"]["split_train"] == 24
    assert summary["dataset"]["split_test"] == 8
    assert summary["kind"] == "independent_HR_rating_alignment_not_hiring_outcome"
    assert summary["criterion_validated"] is False
    assert summary["held_out"]["mean_absolute_error"] <= 3
    data = json.dumps(summary, ensure_ascii=False)
    assert "Synthetic Person" not in data
    assert "unique synthetic scenario" not in data
    assert "reviewer_scores" not in data
    assert "resume" not in data
    assert "source_text" not in data


def test_actual_cli_subprocess_has_no_private_records_in_stdout(tmp_path):
    import subprocess
    import sys

    source = tmp_path / "private_labels.json"
    source.write_text(
        json.dumps({"cases": _fixture_cases()}, ensure_ascii=False),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.evaluate_hr_dataset", "--input", str(source)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    metrics = json.loads(proc.stdout)
    assert metrics["dataset"]["case_count"] == 32
    assert "Synthetic Person" not in proc.stdout
    assert "unique synthetic scenario" not in proc.stdout


def test_cli_rejects_too_small_dataset(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"cases": _fixture_cases()[:5]}), encoding="utf-8")
    with pytest.raises(ValueError):
        evaluate_file(path)


def test_cli_rejects_corrupted_data_and_huge_files(tmp_path):
    file = tmp_path / "corrupt.json"
    file.write_text('{"cases": ["invalid"]', encoding="utf-8")
    with pytest.raises(ValueError):
        evaluate_file(file)
    file.write_bytes(b"X" * (20 * 1024 * 1024 + 1))
    with pytest.raises(ValueError):
        evaluate_file(file)


def test_cli_never_writes_weight_files_or_personal_record_files(tmp_path):
    from app.diagnosis.scoring import RULES_PATH
    before = RULES_PATH.read_bytes()
    file = tmp_path / "private_labels.json"
    file.write_text(json.dumps({"cases": _fixture_cases()}), encoding="utf-8")
    evaluate_file(file)
    assert RULES_PATH.read_bytes() == before
    assert set(p.name for p in tmp_path.iterdir()) == {"private_labels.json"}
