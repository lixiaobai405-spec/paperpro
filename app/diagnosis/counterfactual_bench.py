"""Counterfactual synthetic benchmark, independent of production score weights.

This suite tests *pre-registered behavioural invariants*, not agreement with
labels produced by the scorer. It cannot establish hiring predictive validity.
Every resume is synthetic and constructed in memory; no network or disk writes.
"""
from __future__ import annotations

from dataclasses import dataclass
import random

from app.models import Entry
from .schema import CandidateResume, CareerEntry, Target
from .scoring import score_match, load_rules


@dataclass(frozen=True)
class Pair:
    scenario_id: str
    job_family: str
    property_name: str
    expected: str                 # "equal" or "higher"
    original: CandidateResume
    changed: CandidateResume
    target: Target


# Role assumptions are deliberately authored independently of rules.json weights.
JOBS = [
    {
        "family":"software", "role":"后端开发工程师",
        "skills":["Python","SQL","Git","Docker"],
        "duty":"维护后端 API 服务", "project":"使用 Python 开发后端 API",
    },
    {
        "family":"data", "role":"数据分析师",
        "skills":["Python","SQL","Excel","数据分析"],
        "duty":"负责数据分析与数据模型", "project":"建立 SQL 数据分析报表",
    },
    {
        "family":"product", "role":"产品经理",
        "skills":["SQL","Excel","数据分析"],
        "duty":"负责产品需求与用户研究", "project":"梳理产品需求并推动上线",
    },
    {
        "family":"design", "role":"交互设计师",
        "skills":["Figma","设计"],
        "duty":"负责设计交互与视觉原型", "project":"使用 Figma 设计交互原型",
    },
]


def _job_target(spec: dict, *, seed: int) -> Target:
    rng = random.Random(seed)
    skills = spec["skills"][:]
    rng.shuffle(skills)
    years = 1 + (seed % 4)
    description_styles = [
        f"2026年招聘。本岗位需熟悉 {', '.join(skills)}，要求{years}年相关工作经验；具体工作：{spec['duty']}。",
        f"岗位职责：{spec['duty']}。条件：{', '.join(skills)}；至少{years}年岗位经验。",
        f"需要具备 {', '.join(skills)} 的技能证据，并有{years}年相关岗位工作经验；主要负责{spec['duty']}。",
        f"招聘说明：任职者参与{spec['duty']}项目；技能要求 {', '.join(skills)}；需{years}年以上相关工作经验。",
    ]
    jd = description_styles[(seed // 2) % len(description_styles)]
    return Target(role=spec["role"], company="纯虚构企业", job_description=jd)


def _baseline(spec: dict, seed: int) -> CandidateResume:
    return CandidateResume(
        name=f"合成候选人{seed}", title=spec["role"],
        skills=[spec["skills"][0]], summary="",
    )


def build_pairs(*, per_family: int = 20, seed: int = 1021) -> list[Pair]:
    if not 1 <= per_family <= 200:
        raise ValueError("per_family must be 1..200")
    pairs: list[Pair] = []
    for job in JOBS:
        for repetition in range(per_family):
            suffix = seed + repetition * 29
            goal = _job_target(job, seed=suffix)
            base = _baseline(job, suffix)
            role = job["role"]
            # Rotate which two skills supply the positive/negative treatment,
            # so 20 cases are not merely candidate-name changes.
            rotated = job["skills"][repetition % len(job["skills"]):] + job["skills"][:repetition % len(job["skills"])]
            first_skill, second_skill = rotated[:2]
            base.skills = [first_skill]
            def add(kind: str, expected: str, changed: CandidateResume, original=None):
                pairs.append(Pair(
                    scenario_id=f"{job['family']}-{repetition:03d}-{kind}",
                    job_family=job["family"], property_name=kind,
                    expected=expected, original=original or base,
                    changed=changed, target=goal,
                ))

            # This is an ex-ante policy judgement: explicit evidence of a
            # genuinely relevant skill should not reduce job-specific coverage.
            improved = base.model_copy(deep=True)
            improved.skills.append(second_skill)
            add("add_relevant_skill", "higher", improved)

            # A negated or absent claim provides no positive qualification.
            negated = base.model_copy(deep=True)
            negated.skills.append([
                f"{second_skill}：不会", f"不熟悉{second_skill}",
                f"{second_skill}（未掌握）", f"未掌握{second_skill}",
            ][repetition % 4])
            add("negated_skill_bait", "equal", negated)

            # A job-irrelevant job (however long) must not count as relevant
            # tenure or boost fit by its mere presence.
            unrelated = base.model_copy(deep=True)
            unrelated.experience.append(CareerEntry(
                heading="2010.01–2025.12 虚构展馆 | 收银员",
                company="虚构展馆", role="展馆收银员",
                start_date=f"{2010 + repetition % 5}.01", end_date="2025.12",
                bullets=["负责现金交接与日常核对"],
            ))
            add("unrelated_long_tenure", "equal", unrelated)

            # Names, locations and unrelated hobbies are not competency evidence.
            irrelevant = base.model_copy(deep=True)
            irrelevant.name="另一种匿名昵称"
            irrelevant.email="fake-name@example.invalid"
            irrelevant.location="其他城市"
            irrelevant.additional=["手工陶艺", "篮球", "姓名已经匿名处理"]
            irrelevant.skills.append("瑜伽")
            add("identity_hobby_invariance", "equal", irrelevant)

            # Repeating precisely the same project sentence must not turn a
            # single achievement into multiple distinct pieces of evidence.
            one_project = base.model_copy(deep=True)
            one_project.projects=[Entry(
                heading="课程实践", bullets=[job["project"]],
            )]
            spam_project = one_project.model_copy(deep=True)
            spam_project.projects[0].bullets *= (2 + repetition % 5)
            add("repeated_project_claim", "equal", spam_project, one_project)

            # Two references to the same dated work interval cannot double
            # experience credit or the value of its identical project claim.
            one_role = base.model_copy(deep=True)
            one_role.experience=[CareerEntry(
                heading=f"2022.01–2023.12 合成单位 | {role}",
                company="合成单位",role=role,
                start_date=f"{2020 + repetition % 4}.01", end_date=f"{2021 + repetition % 4}.12",
                bullets=[job["duty"]],
            )]
            redundant = one_role.model_copy(deep=True)
            redundant.experience.append(one_role.experience[0].model_copy(deep=True))
            add("duplicate_job_period", "equal", redundant, one_role)

            # A real applied example is stronger than a list claim, even if
            # both mention identical skill tokens.
            listed = base.model_copy(deep=True)
            listed.skills = job["skills"][:]
            applied = listed.model_copy(deep=True)
            applied.projects=[Entry(
                heading="真实经历占位：合成演示",
                bullets=[f"{job['project']}；使用 {', '.join(job['skills'])}"],
            )]
            add("applied_vs_listed_skill", "higher", applied, listed)
    return pairs


def evaluate_pairs(*, per_family: int = 20, seed: int = 1021) -> dict:
    cases=build_pairs(per_family=per_family,seed=seed)
    labels: dict[str, dict] = {}
    examples: list[dict] = []
    for pair in cases:
        a=score_match(pair.original,pair.target)["score"]
        b=score_match(pair.changed,pair.target)["score"]
        expected=pair.expected
        ok=(a==b) if expected=="equal" else (b>a)
        group=labels.setdefault(pair.property_name,{
            "total":0,"passed":0,"failed":0,"min_delta":100,"max_delta":-100,
        })
        group["total"]+=1
        group["passed"]+=int(ok)
        group["failed"]+=int(not ok)
        group["min_delta"]=min(group["min_delta"],b-a)
        group["max_delta"]=max(group["max_delta"],b-a)
        if not ok and len(examples)<10:
            examples.append({
                "scenario":pair.scenario_id,
                "property":pair.property_name,
                "expected":expected,
                "score_before":a, "score_after":b,
            })
    failed=sum(g["failed"] for g in labels.values())
    return {
        "rules_version":load_rules()["version"],
        "kind":"pre_registered_counterfactual_properties",
        "synthetic_cases":len(cases)*2,
        "synthetic_pairs":len(cases),
        "role_families":len(JOBS),
        "pairwise_pass_rate":round((len(cases)-failed)/len(cases),4),
        "failed_pairs":failed,
        "properties":labels,
        "counterexamples":examples,
        "criterion_validated":False,
        "caveat":"These are independently authored synthetic invariance/monotonicity expectations. They do not measure employer decisions or hiring accuracy.",
    }
