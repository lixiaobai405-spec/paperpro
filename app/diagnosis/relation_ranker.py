"""Small CPU-only research baseline for independently annotated PDF relation pairs.

All supervision originates from separate GT company/role work-entry identities,
never from PaperPro's own resume score or inferred work facts. This is an
offline *ranking experiment*, not a production model or hiring probability.

Fixed recipe: six bounded geometry features, logistic linear scorer, L2
regularization, deterministic full-batch gradient descent. No downloads,
GPU, external AI, model serialization or deployment.
"""
from __future__ import annotations

from collections import defaultdict
import math

from .relation_pairs import FEATURE_NAMES


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp=math.exp(-min(value,35))
        return 1/(1+exp)
    exp=math.exp(max(value,-35))
    return exp/(1+exp)


def _valid_feature_vector(raw) -> tuple[float,...]:
    if not isinstance(raw,(tuple,list)) or len(raw)!=len(FEATURE_NAMES):
        raise ValueError("关系特征数量必须与固定接口一致")
    if any(type(x) not in (float,int) or not math.isfinite(x)
           or not -1<=x<=1 for x in raw):
        raise ValueError("关系特征必须是 [-1,1] 的有限数")
    return tuple(float(x) for x in raw)


def fit_relation_ranker(
    rows: list[dict], *, holdout_ids: tuple[int,...]
) -> dict:
    """Fit a fixed CPU geometry baseline ONLY on disjoint synthetic GT rows."""
    if len(rows)<8:
        raise ValueError("训练候选记录不足")
    allow_holdout=set(holdout_ids)
    samples=[]
    ids=set()
    positives=negatives=0
    for record in rows:
        source_id=record.get("source_id")
        if source_id in allow_holdout:
            raise ValueError("保留测试集不得用于参数拟合")
        if (record.get("split")!="train_candidate"
            or record.get("label_source")!="independent_gt_work_record"):
            raise ValueError("仅允许独立标注的训练候选池")
        label=record.get("label")
        if type(label)!=int or label not in (0,1):
            raise ValueError("标签必须为独立 GT 的 0 或 1")
        features=_valid_feature_vector(record.get("features"))
        samples.append((features,label))
        ids.add(source_id)
        positives+=label
        negatives+=1-label
    if not positives or not negatives or len(ids)<2:
        raise ValueError("至少需要正负两类及两个独立 PDF 来源")

    weights=[0.0]*len(FEATURE_NAMES)
    bias=0.0
    lr=0.45
    l2=0.015
    # No random seed or shuffle: bitwise reproducible with stable row order.
    for _ in range(600):
        gradient=[0.0]*len(weights)
        b_gradient=0.0
        for features,label in samples:
            predicted=_sigmoid(bias+sum(w*x for w,x in zip(weights,features)))
            error=predicted-label
            b_gradient+=error
            for k,value in enumerate(features):
                gradient[k]+=error*value
        n=len(samples)
        bias-=lr*b_gradient/n
        for k in range(len(weights)):
            weights[k]-=lr*(gradient[k]/n+l2*weights[k])
    return {
        "features":list(FEATURE_NAMES),
        "weights":[round(x,9) for x in weights],
        "bias":round(bias,9),
        "training_pairs":len(samples),
        "training_source_count":len(ids),
        "positive":positives,"hard_negative":negatives,
        "objective":"synthetic_independent_gt_pair_ranking",
        "trained_only_on_synthetic_gt":True,
        "deployed":False,
        "score_is_hiring_probability":False,
        "calibrated_to_real_job_outcomes":False,
    }


def geometry_baseline_probability(features: list[float]) -> float:
    """Predeclared no-fit geometry comparator (not calibrated probability)."""
    same,y_align,y_gap,dx,right,overlap=_valid_feature_vector(features)
    if not same:
        return 0.0
    return max(0.0,min(1.0,(
        .05+.48*y_align+.20*overlap+.15*right
        -.20*y_gap-.06*abs(dx)
    )))


def _model_score(model: dict, features) -> float:
    if model.get("features")!=list(FEATURE_NAMES) or model.get("deployed") is not False:
        raise ValueError("仅允许本地研究基线的固定特征顺序")
    values=_valid_feature_vector(features)
    return _sigmoid(float(model["bias"])+sum(
        float(w)*x for w,x in zip(model["weights"],values)
    ))


def evaluate_relation_ranking(
    model: dict | None, rows: list[dict],
) -> dict:
    """AUC and nontrivial top-1 role→employer selection.

    Candidate companies and role anchors here are oracle GT alignments:
    metrics condition on BOTH endpoints being uniquely found in PDF text.
    They cannot be presented as end-to-end resume parsing accuracy.
    """
    score=(
        (lambda features:_model_score(model,features))
        if model is not None else geometry_baseline_probability
    )
    scored=[]
    for row in rows:
        if row.get("label_source")!="independent_gt_work_record":
            raise ValueError("不能混用非独立字段标签")
        p=score(row["features"])
        scored.append((row,p))

    positive=[p for item,p in scored if item["label"]==1]
    negative=[p for item,p in scored if item["label"]==0]
    correct=ties=0
    for pos in positive:
        for neg in negative:
            correct+=int(pos>neg)
            ties+=int(pos==neg)
    pairs=len(positive)*len(negative)
    auc=round((correct+ties*.5)/pairs,4) if pairs else None

    grouping=defaultdict(list)
    for item,value in scored:
        grouping[(item["source_id"],item["role_ref"])].append(
            (item,value)
        )
    top1=0;eligible=0;uncertain=0
    for cases in grouping.values():
        if len(cases)<2 or sum(item["label"] for item,_ in cases)!=1:
            continue
        eligible+=1
        peak=max(value for _,value in cases)
        winners=[item for item,value in cases if abs(value-peak)<1e-9]
        if len(winners)!=1:
            uncertain+=1
        elif winners[0]["label"]==1:
            top1+=1

    return {
        "pair_count":len(rows),
        "positive":len(positive),"negative":len(negative),
        "pair_auc":auc,
        "top1_evaluated_roles":eligible,
        "top1_correct":top1,
        "top1_tied_abstentions":uncertain,
        "top1_accuracy":round(top1/eligible,4) if eligible else None,
        "model_fitted":model is not None,
        "deployed":False,
        "score_is_hiring_probability":False,
        "real_applicant_validation":False,
        "oracle_unique_anchor_condition":True,
    }
