"""Regression-first adversarial checks for V3 report provenance and partial output."""
from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.diagnosis.engine import run_diagnosis
from app.diagnosis.report_export import render_diagnosis_report
from app.diagnosis.schema import CandidateResume, CareerEntry, Target
from app.main import app
from app.models import Entry

client = TestClient(app, raise_server_exceptions=False)


def payload(*, name="Alpha", role="后端开发工程师", enabled=None):
    return {
        "resume": CandidateResume(
            name=name, summary="参与 Python SQL 系统开发",
            skills=["Python", "SQL"],
            experience=[CareerEntry(
                heading="2022.01 - 2025.01 示例公司｜开发",
                company="示例公司", role="开发",
                start_date="2022.01", end_date="2025.01",
                bullets=["使用 Python SQL 开发业务接口"],
            )],
            projects=[Entry(heading="接口系统", bullets=["使用 Python 做接口联调"])],
        ).model_dump(),
        "target": {"role": role, "job_description": "要求 Python SQL，有工作经验"},
        "enabled_sections": enabled,
        "as_of": "2026-10-28",
    }


def issue(**kwargs):
    response = client.post("/api/diagnosis/report", json=payload(**kwargs))
    assert response.status_code == 200, response.text[:200]
    return response.json()


def exported(report):
    return client.post("/api/diagnosis/report/export", json={"report":report,"format":"txt"})


def test_issued_snapshot_exports_without_new_credentials_or_user_blockers():
    actual = issue()
    assert exported(actual).status_code == 200
    assert isinstance(actual["meta"].get("export_signature"), str)
    assert len(actual["meta"]["export_signature"]) >= 32


def test_browser_normalizes_integral_json_numbers_without_invalidating_report():
    issued = issue()

    def browser_json(value):
        if isinstance(value, dict):
            return {key: browser_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [browser_json(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    normalized = browser_json(issued)
    assert exported(normalized).status_code == 200


@pytest.mark.parametrize("mutator", [
    lambda r: r["dimensions"]["match"].update(score=(r["dimensions"]["match"]["score"] + 1) % 101),
    lambda r: r["target"].update(role="伪造目标职位"),
    lambda r: r["meta"].update(reviewed_draft_sha256="forged-fingerprint"),
    lambda r: r["meta"].update(rules_version="FAKE-HR-RULE"),
    lambda r: r["dimensions"]["verification"].update(issues=[{"id":"fake","original":"FABRICATED"}]),
    lambda r: r["meta"].pop("export_signature", None),
])
def test_modified_snapshot_is_not_accepted_as_issued_report(mutator):
    document = issue()
    mutator(document)
    assert exported(document).status_code == 422


def test_two_genuine_reports_cannot_be_mixed_into_a_third_report():
    first = issue(name="Alpha", role="Backend Developer")
    second = issue(name="Beta", role="Graphic Designer")
    mixed = deepcopy(first)
    mixed["target"] = second["target"]
    mixed["dimensions"] = second["dimensions"]
    result = exported(mixed)
    assert result.status_code == 422
    assert "Alpha" not in result.text
    assert "Beta" not in result.text


def test_export_will_not_label_empty_ok_sections_as_completed():
    forged = issue()
    forged["dimensions"] = {key:{"status":"ok"} for key in forged["dimensions"]}
    with pytest.raises(ValueError):
        render_diagnosis_report(forged)


def test_nested_malformed_requirements_return_validation_error_not_http_500():
    forged = issue()
    forged["dimensions"]["match"]["requirements"] = 10
    with pytest.raises(ValueError):
        render_diagnosis_report(forged)


def test_export_keeps_all_evidence_and_all_issues_without_silent_truncation():
    report = issue()
    refs = [
        {"path":f"skills.{index}", "original":f"SOURCE_TOKEN_{index:02d}"}
        for index in range(5)
    ]
    report["dimensions"]["match"]["requirements"][0]["evidence_refs"] = refs
    report["dimensions"]["verification"]["issues"] = [
        {
            "id":f"issue-{index}", "type":"需核查表述", "severity":"中",
            "location":"skills.0", "original":f"ISSUE_TOKEN_{index:02d}",
            "reason":"请核对这一处",
        }
        for index in range(35)
    ]
    body, _ = render_diagnosis_report(report)
    assert "SOURCE_TOKEN_00" in body
    assert "SOURCE_TOKEN_04" in body
    assert "ISSUE_TOKEN_29" in body
    assert "ISSUE_TOKEN_34" in body


def test_long_single_evidence_is_marked_truncated_instead_of_silently_changed():
    report = issue()
    long_value = "SOURCE_TEXT_" * 65
    report["dimensions"]["match"]["requirements"][0]["evidence_refs"] = [
        {"path": "projects.0.bullets.0", "original": long_value}
    ]
    body, _ = render_diagnosis_report(report)
    assert "SOURCE_TEXT_" in body
    assert "字段过长，已明确截断" in body


def test_only_verified_dimension_does_not_emit_unrelated_job_match_advice():
    report = issue(enabled=["verification"])
    assert report["meta"]["report_status"] == "partial"
    assert not any(item["id"] in {"advice-01","advice-02","advice-03","advice-04",
                                   "advice-05","advice-08","advice-09"}
                   for item in report["suggestions"])


def test_match_only_does_not_offer_experience_potential_or_motivation_advice():
    report = issue(enabled=["match"])
    assert report["meta"]["completed_modules"] == ["match"]
    assert all(item["id"] in {"advice-01","advice-02","advice-05"}
               for item in report["suggestions"])
    assert exported(report).status_code == 200


def test_full_report_retains_current_business_suggestions_without_regression():
    report = issue()
    assert len(report["suggestions"]) >= 8
    assert exported(report).status_code == 200
