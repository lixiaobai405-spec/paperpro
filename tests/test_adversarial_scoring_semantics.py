"""Independent counterexamples for candidate scoring and inference integrity."""
from __future__ import annotations

from app.diagnosis.schema import CandidateResume, CareerEntry, Target
from app.diagnosis.scoring import score_match
from app.diagnosis.engine import run_diagnosis
from app.models import Entry, Education


def row(candidate, target, field):
    return next(x for x in score_match(candidate, target, as_of="2026-10-19")["requirements"] if x["id"] == field)


def test_civil_engineering_years_are_not_backend_development_experience():
    resume=CandidateResume(
        name="合成人选", title="土木工程师",
        experience=[CareerEntry(
            heading="2010.01-2025.12 建筑企业 | 土木工程师",
            company="建筑企业", role="土木工程师",
            start_date="2010.01", end_date="2025.12",
            bullets=["负责土木工程项目现场施工、结构管理"],
        )],
    )
    target=Target(role="后端开发工程师",job_description="要求3年后端开发经验，熟悉 Python SQL")
    item=row(resume,target,"experience")
    assert item["coefficient"]==0
    assert not item["evidence_refs"]


def test_recruitment_calendar_year_is_not_experience_requirement():
    resume=CandidateResume(
        name="合成人选", title="后端开发工程师",
        experience=[CareerEntry(
            heading="2023.01-2025.12 软件企业 | 后端开发工程师",
            company="软件企业",role="后端开发工程师",
            start_date="2023.01",end_date="2025.12",
            bullets=["负责 SQL API 开发"],
        )]
    )
    target=Target(role="后端开发工程师",
                  job_description="2026年社会招聘，要求3年相关工作经验，熟悉 SQL")
    item=row(resume,target,"experience")
    assert item["coefficient"]==1
    assert "36 月" in item["reason"]
    assert "312" not in item["reason"]


def test_generic_word_project_cannot_make_irrelevant_projects_backend_relevant():
    resume=CandidateResume(
        name="合成人选", title="平面设计师",
        projects=[
            Entry(heading="水彩绘画项目",bullets=["完成水彩绘画项目作品展示"]),
            Entry(heading="陶艺制作项目",bullets=["完成陶艺制作项目与展览"]),
        ],
    )
    target=Target(role="后端开发工程师",job_description="开发 Python SQL 系统 API 服务")
    item=row(resume,target,"projects")
    assert item["coefficient"]==0
    assert not item["evidence_refs"]


def test_postfixed_negation_not_positive_skill_or_potential_evidence():
    resume=CandidateResume(
        name="合成人选",
        skills=["Python：不会","SQL（未掌握）"],
        certificates=["未取得CFA证书"],
        summary="目前没有领导团队的实际经历。",
    )
    target=Target(role="后端开发工程师",job_description="熟悉 Python SQL")
    assert row(resume,target,"skills")["coefficient"]==0
    result=run_diagnosis(resume,target,as_of="2026-10-19")
    potential=result["dimensions"]["potential"]
    cert=next(s for s in potential["signals"] if s["signal"]=="证书")
    assert cert["status"]=="未体现"


def test_equal_level_or_unrelated_roles_cannot_claim_promotion_or_continuity():
    same=CandidateResume(name="合成人选",experience=[
        CareerEntry(role="工程师",company="A",heading="2020.01-2022.12 A | 工程师",
                    start_date="2020.01",end_date="2022.12"),
        CareerEntry(role="工程师",company="B",heading="2023.01-2025.12 B | 工程师",
                    start_date="2023.01",end_date="2025.12"),
    ])
    target=Target(role="后端开发工程师")
    exp=run_diagnosis(same,target,as_of="2026-10-19")["dimensions"]["experience"]
    assert "进阶" not in exp["career_progression"]
    unrelated=same.model_copy(deep=True)
    unrelated.experience[0].role="设计师"
    unrelated.experience[1].role="会计"
    other=run_diagnosis(unrelated,target,as_of="2026-10-19")["dimensions"]["experience"]
    assert "相近岗位" not in other["career_continuity"]


def test_english_data_developer_routes_to_data_family():
    resume=CandidateResume(name="合成人选",skills=["Python","SQL"])
    target=Target(role="Data Developer",job_description="Experience in SQL Python")
    assert score_match(resume,target)["job_family"]=="data"
