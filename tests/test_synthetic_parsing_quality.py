"""Synthetic media quality acceptance: does not substitute for 20 real resumes."""
from __future__ import annotations

from app.parser import parse_resume
from app.diagnosis.adapter import from_text
from app.diagnosis.synthetic_parse_bench import synthetic_parse_report
from app.diagnosis.synthetic_ocr_bench import synthetic_ocr_report


def test_twenty_distinct_synthetic_docx_and_pdf_full_schema():
    result = synthetic_parse_report()
    assert result["sample_count"] == 20
    assert result["formats"] == {"docx": 10, "pdf": 10}
    assert result["expected_field_cells"] == 260
    assert result["field_completeness"] >= 0.90, result["failures"]
    assert result["field_pass_count"] == 260, result["failures"]
    assert result["real_user_accuracy_verified"] is False


def test_ocr_text_normalizations_are_whitelisted_not_fabricated_facts():
    text = (
        "模拟候选者00\nsynthetic00@example. invalid\n"
        "求职意向：后端开发工程师\n工作经历\n"
        "2022年01月－2025年06月示例科技00丨后端开发工程师\n"
        "－使用Python和SQL开发业务API\n"
    )
    result=from_text(text)
    assert result.email == "synthetic00@example.invalid"
    assert len(result.experience) == 1
    entry=result.experience[0]
    assert entry.start_date == "2022.01"
    assert entry.end_date == "2025.06"
    assert entry.company == "示例科技00"
    assert entry.role == "后端开发工程师"
    assert "2022年01月" in result.source_text

    english = (
        "Avery Example\nalex@example.invalid\n"
        "Target Role: Backend Developer\n"
        "WorkExperience\n"
        "2022.01 - 2025.06 Example Labs | Backend Developer\n"
        "- Built Python SQL APIs.\n"
    )
    converted=from_text(english)
    assert converted.experience
    assert converted.experience[0].company == "Example Labs"


def test_offline_benchmark_command_exposes_metrics_without_file_artifacts():
    import json
    import subprocess
    import sys
    process = subprocess.run(
        [sys.executable, "-m", "scripts.benchmark_resume_parsing"],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=90,
    )
    assert process.returncode == 0, process.stderr
    data = json.loads(process.stdout)
    assert data["passed"] is True
    assert data["document_gate_passed"] is True
    assert data["document_benchmark"]["sample_count"] == 20
    assert data["real_resume_validation_completed"] is False
    assert data["real_photo_accuracy_validated"] is False
    assert "api_key" not in process.stdout.lower()


def test_four_clear_synthetic_photo_ocr_samples():
    report=synthetic_ocr_report()
    assert report["sample_count"] == 4
    assert report["expected_field_cells"] == 52
    assert report["field_accuracy_proxy"] >= 0.85, report["failures"]
    assert all(case["parsed_method"]=="image-ocr" and case["source_checksum_equal"]
               for case in report["cases"])
    assert report["real_mobile_camera_accuracy_verified"] is False
