"""Source-linked resume contradictions: assert precision before adding detectors.

A contradiction needs two explicit incompatible assertions about the same
candidate, the same skill, and the same time/scope. Absence is not denial.
"""
from __future__ import annotations

from app.diagnosis.schema import CandidateResume, CareerEntry, Target
from app.models import Entry
from app.diagnosis.engine import run_diagnosis


TARGET = Target(role="后端开发工程师", job_description="熟悉 Python SQL Docker Kubernetes")


def _issues(resume: CandidateResume, *, enabled=None):
    result = run_diagnosis(
        resume, TARGET, enabled_sections=enabled, as_of="2026-10-20"
    )
    return result, [
        item for item in result["dimensions"]["verification"]["issues"]
        if item.get("conflict_kind") == "explicit_skill_polarity"
    ]


def test_two_opposite_first_person_skill_claims_have_both_source_paths_and_actions():
    candidate = CandidateResume(
        name="合成候选人",
        summary="我熟悉 Python，并能完成后端接口开发。",
        skills=["Python：不会", "SQL"],
    )
    report, contradictions = _issues(candidate)
    assert len(contradictions) == 1
    issue = contradictions[0]
    assert issue["location"] == "summary"
    assert issue["related_location"] == "skills.0"
    assert "熟悉 Python" in issue["original"]
    assert "Python：不会" in issue["related_original"]
    assert issue["severity"] in {"中", "高"}
    assert {r["path"] for r in issue["evidence_refs"]} == {"summary", "skills.0"}
    advice = [s for s in report["suggestions"] if s.get("issue_id") == issue["id"]]
    assert len(advice) == 1
    assert advice[0]["assessment"] == "需要修正"
    assert advice[0]["location"] == issue["location"]
    assert advice[0]["related_location"] == issue["related_location"]
    assert "核对" in advice[0]["action"]
    questions = [q for q in report["interview_questions"] if q.get("issue_id") == issue["id"]]
    assert len(questions) == 1
    assert "Python" in questions[0]["question"]


def test_same_project_applied_vs_explicitly_never_used_is_internally_inconsistent():
    candidate = CandidateResume(
        projects=[Entry(
            heading="示例项目",
            bullets=["本人使用 SQL 进行查询优化。", "本项目没有使用 SQL。"],
        )]
    )
    _, conflicts = _issues(candidate)
    assert len(conflicts) == 1
    assert {conflicts[0]["location"], conflicts[0]["related_location"]} == {
        "projects.0.bullets.0", "projects.0.bullets.1"
    }


def test_opposite_current_claims_inside_one_field_are_still_locatable():
    resume = CandidateResume(summary="我不会 Python；我熟悉 Python。")
    _, issues = _issues(resume)
    assert len(issues) == 1
    assert issues[0]["location"] == "summary"
    assert issues[0]["related_location"] == "summary"
    assert issues[0]["original"] != issues[0]["related_original"]
    assert "熟悉" in issues[0]["original"]
    assert "不会" in issues[0]["related_original"]


def test_using_a_tool_does_not_imply_full_proficiency():
    resume = CandidateResume(
        projects=[Entry(heading="示例项目", bullets=[
            "本项目使用 Python 完成任务。",
            "本项目不熟悉 Python 的性能调优。",
        ])]
    )
    _, issues = _issues(resume)
    assert not issues


def test_listing_a_skill_does_not_claim_expert_level():
    resume = CandidateResume(
        skills=["Python"],
        summary="目前我还不熟悉 Python 的高级优化。",
    )
    _, issues = _issues(resume)
    assert not issues


def test_qualified_uncertainty_is_neither_proficiency_nor_a_global_denial():
    resume = CandidateResume(
        summary="我不熟悉 Python 的高级优化。",
        skills=["Python：不会"],
    )
    _, issues = _issues(resume)
    assert not issues


def test_clearly_expert_level_and_global_not_familiar_are_inconsistent():
    resume = CandidateResume(
        summary="我精通 Python。",
        self_evaluation="目前我不熟悉 Python。",
    )
    _, issues = _issues(resume)
    assert len(issues) == 1
    assert {issues[0]["location"], issues[0]["related_location"]} == {
        "summary", "self_evaluation"
    }


def test_english_explicit_conflict_and_distinct_languages_are_recognized():
    resume = CandidateResume(
        summary="I am proficient in SQL.",
        self_evaluation="I am not familiar with SQL.",
    )
    _, issues = _issues(resume)
    assert len(issues) == 1
    assert issues[0]["subject"] == "SQL"


def test_current_skill_and_historical_usage_are_not_same_scope():
    resume = CandidateResume(
        skills=["Python：不会"],
        projects=[Entry(heading="旧项目", bullets=["曾使用 Python 编写脚本"])],
    )
    _, issues = _issues(resume)
    assert not issues


def test_not_yet_used_does_not_contradict_later_usage():
    resume = CandidateResume(projects=[Entry(heading="某项目", bullets=[
        "项目初期尚未使用 SQL。",
        "项目后期使用 SQL。",
    ])])
    _, issues = _issues(resume)
    assert not issues


def test_negative_skill_statement_does_not_conflict_with_job_description():
    candidate = CandidateResume(summary="目前我不熟悉 Kubernetes", skills=["Python"])
    _, issues = _issues(candidate)
    assert not issues


def test_ability_and_missing_business_experience_are_not_mutually_exclusive():
    candidate = CandidateResume(
        summary="我还没有 Python 商业项目经验。",
        skills=["Python"],
    )
    _, conflicts = _issues(candidate)
    assert not conflicts


def test_past_to_present_growth_is_not_a_contradiction():
    candidate = CandidateResume(
        summary="我过去不熟悉 Python，但现在已经掌握 Python。",
        skills=["Python"],
    )
    _, conflicts = _issues(candidate)
    assert not conflicts


def test_team_skill_gap_does_not_become_a_personal_denial():
    candidate = CandidateResume(
        summary="团队不熟悉 Docker，我负责协调部署。",
        skills=["Docker"],
    )
    _, conflicts = _issues(candidate)
    assert not conflicts


def test_current_skill_list_is_not_inconsistent_with_an_old_learning_period():
    candidate = CandidateResume(
        skills=["Python"],
        experience=[CareerEntry(
            company="示例单位", role="开发",
            start_date="2022.01", end_date="2023.01",
            bullets=["入职时不会 Python，后来学习并掌握。"],
        )],
    )
    _, conflicts = _issues(candidate)
    assert not conflicts


def test_ambiguous_mentions_and_repeated_keywords_do_not_create_conflicts():
    candidate = CandidateResume(
        skills=["Python", "Python"],
        summary="了解 Python 的限制；招聘需求提到 Docker 与 Git。",
    )
    _, conflicts = _issues(candidate)
    assert not conflicts


def test_selected_todo_export_preserves_both_source_statements():
    from fastapi.testclient import TestClient
    from app.main import app

    candidate = CandidateResume(
        summary="我熟悉 Python",
        skills=["Python：不会"]
    )
    report, issues = _issues(candidate)
    item = next(
        s for s in report["suggestions"] if s.get("issue_id") == issues[0]["id"]
    )
    exported = TestClient(app).post("/api/diagnosis/export", json={
        "report": report,
        "selected_ids": [item["id"]],
        "kind": "todo",
        "format": "txt",
    })
    assert exported.status_code == 200
    decoded = exported.content.decode("utf-8-sig")
    assert "原文：我熟悉 Python" in decoded
    assert "对照位置：skills.0" in decoded
    assert "对照原文：Python：不会" in decoded
    assert "不能" in decoded or "核对" in decoded
    assert exported.headers["x-selected-count"] == "1"


def test_disabling_verification_must_not_generate_conflict_suggestions():
    candidate = CandidateResume(summary="我熟悉 Python", skills=["Python：不会"])
    report = run_diagnosis(
        candidate, TARGET, enabled_sections=["match"], as_of="2026-10-20"
    )
    assert report["dimensions"]["verification"]["status"] == "disabled"
    assert not any(
        s.get("conflict_kind") == "explicit_skill_polarity"
        for s in report["suggestions"]
    )
