"""V3 F10 incremental acceptance: export a whole, scope-labelled diagnosis report.

A client-posted report is a snapshot for the current browser; this endpoint
does NOT assert server-side task ownership or historical persistence.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.diagnosis.schema import CareerEntry, CandidateResume, Target
from app.diagnosis.engine import run_diagnosis
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def _report(*, enabled=None):
    resume = CandidateResume(
        name="合成示例",
        title="后端开发工程师",
        source_sha256="synthetic-fingerprint",
        skills=["Python", "SQL"],
        summary="参与订单服务开发和系统接口调试",
        experience=[CareerEntry(
            heading="2022.01-2025.01 示例机构 | 后端工程师",
            company="示例机构", role="后端工程师",
            start_date="2022.01", end_date="2025.01",
            bullets=["使用 Python 和 SQL 开发订单 API"],
        )],
    )
    target = Target(role="后端开发工程师", job_description="熟悉 Python、SQL；2年开发经验")
    return run_diagnosis(resume, target, enabled_sections=enabled, as_of="2026-10-28")


def _export(report, file_format="txt"):
    return client.post("/api/diagnosis/report/export", json={
        "report": report, "format": file_format,
    })


def test_complete_report_txt_contains_snapshot_metadata_and_all_five_scoped_sections():
    report = _report()
    response = _export(report)
    assert response.status_code == 200, response.text[:500]
    content = response.content.decode("utf-8-sig")
    assert "PaperPro 五维诊断报告" in content
    assert "2026-10-28" in content
    assert report["meta"]["generated_at"] in content
    assert report["meta"]["rules_version"] in content
    assert report["meta"]["reviewed_draft_sha256"] in content
    assert "后端开发工程师" in content
    assert "Python" in content
    assert "原文证据" in content
    assert "匹配" in content
    assert response.headers["x-report-coverage"] == "5/5"
    assert "录用概率" in content
    assert response.headers["cache-control"] == "no-store"


def test_disabled_modules_are_never_exported_as_complete():
    report = _report(enabled=["match", "verification"])
    response = _export(report)
    assert response.status_code == 200, response.text[:500]
    content = response.content.decode("utf-8-sig")
    assert response.headers["x-report-coverage"] == "2/5"
    assert "部分报告" in content
    assert "工作经验研判：已关闭" in content
    assert "学习能力与发展潜力：已关闭" in content
    assert "岗位匹配度量化：已完成" in content
    assert "全部已完成" not in content


def test_failed_modules_keep_error_state_and_other_results(monkeypatch):
    from app.diagnosis import engine

    def broken(*args, **kwargs):
        raise RuntimeError("SIMULATED FAILURE, SHOULD NOT LEAK")
    monkeypatch.setitem(engine.RUNNERS, "potential", broken)
    report = _report()
    response = _export(report)
    assert response.status_code == 200
    content = response.content.decode("utf-8-sig")
    assert "学习能力与发展潜力：失败" in content
    assert "部分报告" in content
    assert "SIMULATED FAILURE" not in content
    assert response.headers["x-report-coverage"] == "4/5"


def test_pdf_report_is_real_and_keeps_status_when_a_section_is_disabled(monkeypatch):
    monkeypatch.setenv("PAPERPRO_PDF_ENGINE", "reportlab")
    report = _report(enabled=["match", "verification"])
    response = _export(report, "pdf")
    assert response.status_code == 200, response.text[:500]
    assert response.content.startswith(b"%PDF")
    assert response.headers["x-report-coverage"] == "2/5"
    import pymupdf
    document = pymupdf.open(stream=response.content, filetype="pdf")
    assert document.page_count >= 1
    pdf_text = "\n".join(page.get_text() for page in document)
    assert "PaperPro" in pdf_text
    assert "Python" in pdf_text


def test_missing_snapshot_or_no_valid_section_rejects_export_without_fake_success():
    report = _report()
    report["meta"]["reviewed_draft_sha256"] = ""
    assert _export(report).status_code == 422
    no_valid = _report(enabled=[])
    result = _export(no_valid)
    assert result.status_code == 422


def test_all_disabled_modules_do_not_emit_valid_suggestions():
    report = _report(enabled=[])
    assert report["meta"]["report_status"] == "unavailable"
    assert report["meta"]["completed_modules"] == []
    assert report["suggestions"] == []
    assert report["interview_questions"] == []


def test_all_failed_modules_preserve_error_status_without_suggesting_modifications(monkeypatch):
    from app.diagnosis import engine

    def failure(*args, **kwargs):
        raise RuntimeError("SIMULATED PRIVATE FAILURE")
    for key in engine.RUNNERS:
        monkeypatch.setitem(engine.RUNNERS, key, failure)
    report = _report()
    assert report["meta"]["report_status"] == "unavailable"
    assert all(row["status"] == "error" for row in report["dimensions"].values())
    assert report["suggestions"] == []
    assert report["interview_questions"] == []
    assert _export(report).status_code == 422


def test_partial_report_is_explicitly_marked_as_partial():
    report = _report(enabled=["match"])
    assert report["meta"]["report_status"] == "partial"
    assert report["meta"]["completed_modules"] == ["match"]
    assert report["dimensions"]["verification"]["status"] == "disabled"


def test_api_rejects_starting_diagnosis_with_all_modules_closed():
    response = client.post("/api/diagnosis/report", json={
        "resume": CandidateResume(name="合成用户").model_dump(),
        "target": {"role": "后端工程师"},
        "enabled_sections": [],
    })
    assert response.status_code == 422


def test_invalid_format_and_oversized_payload_reject_without_echoing_secrets():
    report = _report()
    assert _export(report, "docx").status_code == 422
    report["extra"] = "SECRET_PRIVATE_SOURCE_" * 15000
    response = _export(report)
    assert response.status_code in {413, 422}
    assert "SECRET_PRIVATE_SOURCE_" not in response.text
