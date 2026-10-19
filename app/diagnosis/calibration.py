"""Independent, reproducible score validation.

IMPORTANT: synthetic construction tests prove ordering properties only; real
criterion validity requires *independent* HR labels and held-out outcomes.
No optimizer may silently replace the production job-family weights.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import random
import statistics

from app.models import Entry
from .schema import CandidateResume, CareerEntry, Target
from .scoring import load_rules, score_match


def _average_rank(values: list[float]) -> list[float]:
    rank=[0.0]*len(values)
    positions=sorted(range(len(values)),key=lambda i:values[i])
    start=0
    while start<len(positions):
        stop=start+1
        while stop<len(positions) and values[positions[stop]]==values[positions[start]]:
            stop+=1
        for pos in positions[start:stop]:
            rank[pos]=(start+stop+1)/2
        start=stop
    return rank


def rank_correlation(predicted: list[float], actual: list[float]) -> float | None:
    if len(predicted)!=len(actual) or len(actual)<2:
        return None
    x=_average_rank(predicted);y=_average_rank(actual)
    mx=statistics.mean(x);my=statistics.mean(y)
    dx=sum((v-mx)**2 for v in x);dy=sum((v-my)**2 for v in y)
    if dx==0 or dy==0:
        return None
    return round(sum((a-mx)*(b-my) for a,b in zip(x,y))/math.sqrt(dx*dy),4)


def _metrics(predicted: list[int], expert: list[float]) -> dict:
    if len(predicted)!=len(expert) or not predicted:
        raise ValueError("预测分数与独立标注数量不一致")
    pairs=0;concordant=0;ties=0
    for i in range(len(predicted)):
        for j in range(i+1,len(predicted)):
            if expert[i]==expert[j]:
                continue
            pairs+=1
            if predicted[i]==predicted[j]:
                ties+=1
            elif (expert[i]-expert[j])*(predicted[i]-predicted[j])>0:
                concordant+=1
    return {
        "count":len(predicted),
        "mean_absolute_error":round(statistics.mean(abs(a-b) for a,b in zip(predicted,expert)),3),
        "spearman":rank_correlation(predicted,expert),
        "pairwise_concordance":round(concordant/pairs,4) if pairs else None,
        "tie_fraction":round(ties/pairs,4) if pairs else None,
        "score_span":max(predicted)-min(predicted),
    }


def evaluate_human_labels(cases: list[dict]) -> dict:
    """Requires independently rated real examples (not synthetic rubric labels).

    Each case:
      {case_id, resume, target, reviewer_scores:[scoreA,scoreB], split:'train'|'test'}
    Scores are human panel estimates of document fit, NOT hiring outcomes.
    Real outcomes need a separate study with observed selection decisions.
    """
    if len(cases)<20:
        raise ValueError("独立标注至少需要 20 份，且须有跨岗位分层")
    seen=set();groups={}
    for case in cases:
        cid=case.get("case_id")
        if not isinstance(cid,str) or not cid or cid in seen:
            raise ValueError("标注样本 ID 为空或重复")
        seen.add(cid)
        if case.get("split") not in {"train","test"}:
            raise ValueError("必须明确训练集/保留测试集")
        marks=case.get("reviewer_scores",[])
        if len(marks)<2 or any(type(m) not in {int,float} or not 0<=m<=100 for m in marks):
            raise ValueError("每份样本至少由 2 名独立标注员给出 0..100 分")
        resume=CandidateResume.model_validate(case["resume"])
        target=Target.model_validate(case["target"])
        # A name/email edit must not turn the same candidate and JD into a
        # new independent observation or allow train→holdout leakage.
        job_evidence=resume.model_dump(exclude={
            "name", "email", "phone", "location", "links",
            "source_sha256", "source_text",
        })
        fp=sha256(json.dumps({"resume":job_evidence,
                              "target":target.model_dump()},
                             sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if fp in groups:
            raise ValueError("发现重复履历/岗位证据，不能冒充独立标注样本")
        groups[fp]=case["split"]
    outputs={}
    for split in ("train","test"):
        chosen=[case for case in cases if case["split"]==split]
        if len(chosen)<5:
            raise ValueError("训练集与保留测试集都至少需要 5 份样本")
        predicted=[score_match(CandidateResume.model_validate(c["resume"]),
                               Target.model_validate(c["target"]))["score"] for c in chosen]
        expert=[statistics.mean(c["reviewer_scores"]) for c in chosen]
        outputs[split]=_metrics(predicted,expert)
        outputs[split]["mean_reviewer_disagreement"]=round(
            statistics.mean(max(c["reviewer_scores"])-min(c["reviewer_scores"]) for c in chosen),3)
    return {
        "criterion_validated":False,
        "kind":"independent_HR_rating_alignment_not_hiring_outcome",
        "train":outputs["train"],"held_out":outputs["test"],
        "warning":"独立 HR 主观评分的一致性不等于对实际招聘通过率/工作表现的预测准确性。",
    }


def candidate_scenarios() -> list[dict]:
    """48 constructed ordered cases across four job families, no private data."""
    families=[
        ("后端开发工程师",["Python","SQL","Git","Docker"],"开发后端 API 系统"),
        ("数据分析师",["Python","SQL","Excel","数据分析"],"搭建数据分析模型和报表"),
        ("产品经理",["SQL","Excel","数据分析"],"负责产品需求和用户研究"),
        ("UX 设计师",["Figma","设计"],"设计用户交互与原型"),
    ]
    scenarios=[]
    for family_index,(role,skills,project) in enumerate(families):
        tgt=Target(role=role,job_description=("招聘要求：熟悉 "+", ".join(skills)+", 2年相关工作经验"))
        for level in range(6):
            for variant in range(2):
                c=CandidateResume(name="合成候选人", title=role if level>=1 else "其他岗位")
                if level>=2:
                    count=min(len(skills),1+level-2)
                    c.skills=skills[:count]
                if level>=3:
                    c.projects=[Entry(heading="课程实践",
                        bullets=[("项目："+project if variant==0 else project)])]
                if level>=4:
                    c.experience=[CareerEntry(company="合成企业",role=role,
                        start_date="2021.01",end_date="2025.05",heading="2021.01-2025.05 "+role,
                        bullets=["负责 "+project+"，使用 "+ " ".join(skills)])]
                if level>=5:
                    c.summary="具备相关岗位的系统和项目经历，能够描述具体职责。"
                    c.certificates=["课程证书（示例）"]
                scenarios.append({
                    "family":role,"expected_rank":level,
                    "variant":variant,"resume":c,"target":tgt,
                })
    return scenarios


def synthetic_benchmark() -> dict:
    cases=candidate_scenarios()
    scored=[(c,score_match(c["resume"],c["target"])["score"]) for c in cases]
    comparisons=0;inversions=0;ties=0
    by_family={}
    for item,score in scored:
        by_family.setdefault(item["family"],[]).append((item["expected_rank"],score))
    for values in by_family.values():
        for i,(rank1,score1) in enumerate(values):
            for rank2,score2 in values[i+1:]:
                if rank1==rank2:
                    continue
                comparisons+=1
                if rank1<rank2 and score1>score2 or rank2<rank1 and score2>score1:
                    inversions+=1
                if score1==score2:
                    ties+=1
    return {
        "scenarios":len(cases),"role_families":len(by_family),
        "ordered_pairs":comparisons,"inversions":inversions,"ties":ties,
        "strict_discrimination":round((comparisons-inversions-ties)/comparisons,4),
        "non_inversion_rate":round((comparisons-inversions)/comparisons,4),
        "score_span":max(s for _,s in scored)-min(s for _,s in scored),
        "criterion_validated":False,
        "scope":"hand-constructed monotonic scenario levels; not held-out real HR decisions",
        "per_family":{
            name:[{"level":level,"score":score} for level,score in values]
            for name,values in by_family.items()
        },
    }


def propose_weights(cases: list[dict], *, family: str, seed: int = 7, trials: int = 120) -> dict:
    """A deterministic proposal, never changes rules.json automatically.

    Fit only training cases for one job family; report entirely held-out error.
    Heavily regularize changes from the versioned job-analysis prior.
    """
    from .scoring import _profile
    validated=evaluate_human_labels(cases)
    rules=load_rules()
    if family not in rules["profiles"]:
        raise ValueError("未知岗位类型")
    prior=rules["profiles"][family]["weights"]
    train=[]
    held=[]
    for case in cases:
        role,_=_profile(Target.model_validate(case["target"]).role,rules)
        if role!=family:
            continue
        sample=(CandidateResume.model_validate(case["resume"]),
                Target.model_validate(case["target"]),
                statistics.mean(case["reviewer_scores"]))
        (train if case["split"]=="train" else held).append(sample)
    if len(train)<8 or len(held)<5:
        raise ValueError("单岗位族群需要至少 8 个训练样本和 5 个保留样本")
    keys=list(prior)
    def scores(data,weights):
        return [score_match(r,t,weight_override=weights)["score"] for r,t,_ in data]
    def mae(data,weights):
        return statistics.mean(abs(s-expert) for s,(_,_,expert) in zip(scores(data,weights),data))
    best=prior
    best_loss=mae(train,prior)
    rng=random.Random(seed)
    for _ in range(trials):
        candidate={k:max(0.015, prior[k]*rng.uniform(0.70,1.30)) for k in keys}
        norm=sum(candidate.values())
        candidate={k:v/norm for k,v in candidate.items()}
        penalty=14*sum(abs(candidate[k]-prior[k]) for k in keys)
        loss=mae(train,candidate)+penalty
        if loss < best_loss:
            best=candidate
            best_loss=loss
    train_old=mae(train,prior);train_new=mae(train,best)
    held_old=mae(held,prior);held_new=mae(held,best)
    changed=any(abs(best[k]-prior[k])>1e-6 for k in keys)
    recommend=changed and held_new+2<=held_old
    return {
        "family":family,"candidate_weights":{k:round(v,6) for k,v in best.items()},
        "prior_weights":prior,
        "training_mae_before":round(train_old,3),"training_mae_after":round(train_new,3),
        "held_out_mae_before":round(held_old,3),"held_out_mae_after":round(held_new,3),
        "recommended_for_expert_review":recommend,
        "applied_automatically":False,
        "criterion_validated":False,
        "note":"Tune to independent HR ratings only; this is not predictive validity for hiring or job performance.",
    }


def ahp_weight_proposal(pairwise: list[list[float]], factors: list[str]) -> dict:
    """Saaty/AHP pairwise-judgement elicitation, not automatically deployed.

    A valid AHP matrix must be positive, reciprocal and sufficiently consistent.
    Matrix size 7 matches the seven current job-fit attributes.
    """
    n=len(factors)
    if n<3 or n>9 or len(pairwise)!=n or any(len(row)!=n for row in pairwise):
        raise ValueError("AHP 矩阵必须为完整的方阵")
    for i in range(n):
        for j in range(n):
            a=pairwise[i][j];b=pairwise[j][i]
            if type(a) not in {int,float} or not math.isfinite(a) or a<=0:
                raise ValueError("AHP 偏好判断必须为正数")
            if abs(a*b-1)>1e-3:
                raise ValueError("AHP 两两比较必须互为倒数")
    raw=[math.exp(statistics.mean(math.log(v) for v in row)) for row in pairwise]
    scale=sum(raw)
    weights=[r/scale for r in raw]
    eigen=sum(sum(pairwise[i][j]*weights[j] for j in range(n))/weights[i] for i in range(n))/n
    ri={3:.58,4:.90,5:1.12,6:1.24,7:1.32,8:1.41,9:1.45}[n]
    ci=max(0,(eigen-n)/(n-1))
    cr=ci/ri
    return {
        "weights":{factor:round(weights[i],6) for i,factor in enumerate(factors)},
        "consistency_ratio":round(cr,5),
        "acceptable":cr<=0.10,
        "applied_automatically":False,
        "evidence_type":"expert_pairwise_judgement_not_empirical_predictive_validity",
    }


def swing_weight_proposal(
    ratings: dict[str,dict[str,float]],
    *,
    expected_factors: list[str],
) -> dict:
    """Range-sensitive MCDA weights from explicit importance × attainable swing."""
    if set(ratings)!=set(expected_factors):
        raise ValueError("Swing 评估维度与岗位规则不一致")
    values={}
    for factor in expected_factors:
        r=ratings[factor]
        importance=r.get("importance");swing=r.get("swing")
        if type(importance) not in {int,float} or type(swing) not in {int,float}:
            raise ValueError("Swing 必须给出量化重要性与可变范围")
        if not all(math.isfinite(x) and 0<=x<=100 for x in (importance,swing)):
            raise ValueError("Swing 数值应在 0..100")
        values[factor]=importance*swing
    norm=sum(values.values())
    if norm<=0:
        raise ValueError("Swing 权重总强度为零")
    return {
        "weights":{k:round(v/norm,6) for k,v in values.items()},
        "applied_automatically":False,
        "basis":"range-sensitive swing weights elicitation",
    }


def perturbation_benchmark(*, seed: int = 17, trials: int = 50) -> dict:
    scenarios=candidate_scenarios()
    groups={}
    for c in scenarios:
        groups.setdefault(c["family"],[]).append(c)
    from .scoring import _profile
    rules=load_rules();rng=random.Random(seed)
    inversions=0;pairs=0;grade_changes=0;observations=0
    for role,cases in groups.items():
        family_name,_=_profile(role,rules)
        weights=rules["profiles"][family_name]["weights"]
        baseline=[score_match(c["resume"],c["target"]) for c in cases]
        baseline_grades=[x["grade"] for x in baseline]
        for _ in range(trials):
            varied={k:v*rng.uniform(.8,1.2) for k,v in weights.items()}
            norm=sum(varied.values())
            varied={k:v/norm for k,v in varied.items()}
            scored=[score_match(c["resume"],c["target"],weight_override=varied) for c in cases]
            observations+=len(cases)
            grade_changes+=sum(x["grade"]!=g for x,g in zip(scored,baseline_grades))
            for i in range(len(cases)):
                for j in range(i+1,len(cases)):
                    a=cases[i]["expected_rank"];b=cases[j]["expected_rank"]
                    if a==b:
                        continue
                    pairs+=1
                    if (a-b)*(scored[i]["score"]-scored[j]["score"])<0:
                        inversions+=1
    return {
        "trials_per_family":trials,
        "total_scored":observations,
        "inversions":inversions,
        "compared_pairs":pairs,
        "pairwise_inversion_rate":round(inversions/pairs,5),
        "grade_change_rate":round(grade_changes/observations,4),
        "perturbation":"±20% independently on all seven job weights, renormalized",
        "criterion_validated":False,
    }
