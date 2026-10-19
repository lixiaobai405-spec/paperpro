"""Synthetic media quality acceptance: does not substitute for 20 real resumes."""
from __future__ import annotations

from app.parser import parse_resume
from app.diagnosis.adapter import from_text
from app.diagnosis.synthetic_parse_bench import synthetic_parse_report
from app.diagnosis.synthetic_ocr_bench import synthetic_ocr_report


def test_undelimited_company_then_job_title_in_dated_work_heading():
    # Independent source layout analysis: 18/23 missing roles occur next to
    # whitespace after the employer, without a pipe or colon. Mock entities
    # are deliberately fictional, not copied from external resume records.
    from app.diagnosis.adapter import from_text
    examples = [
        ("2020.03—2023.06 模拟科技  后端开发工程师",
         "模拟科技", "后端开发工程师"),
        ("2021.01 - 2024.12 合成科技集团 数据分析师",
         "合成科技集团", "数据分析师"),
        ("2022/01 – 2023/05 模拟院校 软件工程师",
         "模拟院校", "软件工程师"),
    ]
    for heading, company, role in examples:
        record = from_text("合成用户\n工作经历\n"+heading+"\n- 使用 Python 维护服务\n")
        assert len(record.experience) == 1
        entry = record.experience[0]
        assert entry.company == company, entry.model_dump()
        assert entry.role == role, entry.model_dump()
        assert entry.start_date and entry.end_date
        # The existing parser collapses purely presentational whitespace;
        # exact uploaded source remains accessible separately.
        assert entry.heading == ' '.join(heading.split())
        assert heading in record.source_text

    # The company name itself can contain a job-title noun; don't fabricate
    # a role when no separate trailing title exists.
    ambiguous = from_text(
        "合成用户\n工作经历\n"
        "2021.01 - 2022.02 模拟工程师事务所\n"
    ).experience[0]
    assert ambiguous.role == ""
    assert ambiguous.company == "模拟工程师事务所"


def test_employer_space_role_heading_without_pipe_or_colon():
    from app.diagnosis.adapter import from_text
    raw=(
        "合成候选人\n工作经历\n"
        "2022.07 - 2025.06 演示科技集团 数据库工程师\n"
        "负责 PostgreSQL 数据库的维护和备份。\n"
    )
    draft=from_text(raw)
    assert len(draft.experience)==1
    assert draft.experience[0].company=="演示科技集团"
    assert draft.experience[0].role=="数据库工程师"
    assert draft.experience[0].start_date=="2022.07"
    assert draft.experience[0].end_date=="2025.06"
    assert draft.source_text==raw

    # Do not split a standalone employer's name by guessing a job title.
    ambiguous=from_text(
        "模拟候选人\n工作经历\n2022.07-2025.06 星河工程师事务所\n"
    )
    assert ambiguous.experience[0].role==""
    assert "工程师事务所" in ambiguous.experience[0].company


def test_bilingual_section_header_and_role_first_colon_layout():
    # A public external synthetic PDF exposed this layout. Use invented facts
    # here; the actual external source and annotations are not copied to Git.
    text = (
        "演示求职者\nexample@example.invalid\n"
        "教育背景 / Education\n"
        "2018.09 - 2022.06 模拟大学 | 本科学士\n"
        "工作经历 / Experience\n"
        "2022.07 - 至今: 数据库工程师：演示科技集团\n"
        "负责数据库维护及 SQL 查询优化。\n"
        "自我评价 / About Me\n"
        "主要承担数据库维护与优化工作。\n"
    )
    from app.diagnosis.adapter import from_text
    result = from_text(text)
    assert result.education and "模拟大学" in result.education[0].heading
    assert len(result.experience) == 1
    job = result.experience[0]
    assert job.role == "数据库工程师"
    assert job.company == "演示科技集团"
    assert job.start_date == "2022.07"
    assert job.end_date == "至今"
    assert result.summary == "主要承担数据库维护与优化工作。"
    assert result.source_text == text


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
