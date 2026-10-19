"""MCDA, psychometrics and validation-gate executable contract."""
from __future__ import annotations

import pytest
from app.diagnosis.calibration import (
    ahp_weight_proposal, swing_weight_proposal, synthetic_benchmark,
    perturbation_benchmark, evaluate_human_labels, candidate_scenarios,
    rank_correlation, propose_weights,
)
from app.diagnosis.scoring import load_rules, score_match


def test_48_scenario_synthetic_separation_and_accuracy_boundary():
    report=synthetic_benchmark()
    assert report["scenarios"]>=48
    assert report["role_families"]==4
    assert report["strict_discrimination"]>=0.90
    assert report["non_inversion_rate"]>=.99
    assert report["criterion_validated"] is False
    assert report["score_span"]>=70


def test_perturbation_ranking_is_stable_but_graded_thresholds_are_observed():
    result=perturbation_benchmark(seed=31,trials=18)
    assert result["total_scored"]==48*18
    assert result["pairwise_inversion_rate"]<.10
    assert 0<=result["grade_change_rate"]<=.4
    assert result["criterion_validated"] is False


def test_explicit_swing_range_changes_weights_not_just_subjective_importance():
    ids=[x["id"] for x in load_rules()["factors"]]
    base={id:{"importance":70,"swing":50} for id in ids}
    a=swing_weight_proposal(base,expected_factors=ids)
    assert abs(sum(a["weights"].values())-1)<.00002
    base["skills"]["swing"]=100
    b=swing_weight_proposal(base,expected_factors=ids)
    assert b["weights"]["skills"]>a["weights"]["skills"]
    assert b["applied_automatically"] is False


def test_ahp_reciprocity_and_consistency_before_expert_acceptance():
    ids=[x["id"] for x in load_rules()["factors"]]
    prior=list(load_rules()["profiles"]["software"]["weights"].values())
    matrix=[[a/b for b in prior] for a in prior]
    check=ahp_weight_proposal(matrix,ids)
    assert check["acceptable"]
    assert check["consistency_ratio"]<.01
    assert sum(check["weights"].values())==pytest.approx(1,abs=.00002)
    broken=[row[:] for row in matrix]
    broken[0][1]=9
    broken[1][0]=1/9
    result=ahp_weight_proposal(broken,ids)
    assert result["consistency_ratio"]>0
    with pytest.raises(ValueError):
        ahp_weight_proposal([[1,2],[1,1]],ids)


def test_rank_correlation_uses_tie_aware_spearman():
    assert rank_correlation([1,2,3],[2,4,6])==1
    assert rank_correlation([3,2,1],[2,4,6])==-1
    assert rank_correlation([2,2,2],[1,2,3]) is None


def labeled_data():
    # Programmatically generated labels are for exercising calibration code,
    # not independent expert reviews or predictive accuracy measurement.
    samples=[]
    for i,c in enumerate(candidate_scenarios()):
        score=score_match(c["resume"],c["target"])["score"]
        synthetic=c["resume"].model_copy(deep=True)
        # Deliberately distinct synthetic records for *interface testing only*;
        # their generated labels must never be used to claim HR validity.
        synthetic.additional=["合成记录场景 "+str(i)]
        samples.append({
            "case_id":f"SYNTHETIC-{i}",
            "resume":synthetic.model_dump(),
            "target":c["target"].model_dump(),
            "reviewer_scores":[min(100,score+1),max(0,score-1)],
            "split":"train" if c["expected_rank"]<4 else "test",
        })
    for i in range(2):
        c=dict(samples[10+i])
        c["case_id"]="SYNTHETIC-ADDITIONAL-SOFTWARE-"+str(i)
        c["split"]="test"
        c["resume"]=dict(c["resume"])
        c["resume"]["additional"]=["独立场景变体 "+str(i)]
        samples.append(c)
    return samples


def test_human_label_metric_interface_requires_two_reviewers_and_nonleaky_holdout():
    with pytest.raises(ValueError):
        evaluate_human_labels(labeled_data()[:5])
    cases=labeled_data()
    metrics=evaluate_human_labels(cases)
    assert metrics["held_out"]["count"]>=5
    assert metrics["held_out"]["mean_absolute_error"]<5
    assert metrics["criterion_validated"] is False
    assert metrics["kind"]=="independent_HR_rating_alignment_not_hiring_outcome"
    bad=[dict(c) for c in cases]
    bad[0]["reviewer_scores"]=[bad[0]["reviewer_scores"][0]]
    with pytest.raises(ValueError):
        evaluate_human_labels(bad)
    leak=[dict(c) for c in cases]
    leak[1]["resume"]=leak[0]["resume"]
    leak[1]["target"]=leak[0]["target"]
    leak[1]["split"]="test"
    with pytest.raises(ValueError):
        evaluate_human_labels(leak)
    repeated=[dict(c) for c in cases]
    repeated[1]["resume"]=repeated[0]["resume"]
    repeated[1]["target"]=repeated[0]["target"]
    with pytest.raises(ValueError):
        evaluate_human_labels(repeated)


def test_same_resume_with_name_changes_cannot_cross_train_holdout():
    base=labeled_data()[0]
    copies=[]
    for i in range(22):
        case=dict(base)
        case["case_id"]="RENAME-ONLY-"+str(i)
        case["resume"]={**base["resume"],"name":"Alias "+str(i)}
        case["split"]="train" if i<12 else "test"
        copies.append(case)
    with pytest.raises(ValueError):
        evaluate_human_labels(copies)


def test_weight_optimizer_is_a_proposal_only_and_never_rewrites_rules():
    rules=load_rules()
    candidate=propose_weights(labeled_data(),family="software",trials=22,seed=11)
    assert candidate["applied_automatically"] is False
    assert candidate["criterion_validated"] is False
    assert load_rules()==rules
    assert sum(candidate["candidate_weights"].values())==pytest.approx(1,abs=.00003)
