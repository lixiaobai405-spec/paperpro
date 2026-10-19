"""Bounded CPU-only relation scorer: test mechanics, never hiring accuracy.

Actual held-out results are computed by the external benchmark CLI separately.
No model weights, applicant text or external data are persisted.
"""
from __future__ import annotations

import pytest

from app.diagnosis.relation_pairs import FEATURE_NAMES
from app.diagnosis.relation_ranker import (
    fit_relation_ranker, evaluate_relation_ranking,
    geometry_baseline_probability,
)


def _synthetic_numeric_pairs(n=12):
    rows=[]
    for i in range(n):
        # These are arithmetic unit-test vectors, not HR ground-truth cases.
        rows.extend([
            {"source_id":21+i,"role_ref":"workExperience.0.position",
             "employer_ref":"workExperience.0.companyName",
             "features":[1.,1.,0.,0.25,1.,1.],
             "label":1,"split":"train_candidate",
             "label_source":"independent_gt_work_record"},
            {"source_id":21+i,"role_ref":"workExperience.0.position",
             "employer_ref":"workExperience.1.companyName",
             "features":[1.,0.05,0.95,-0.4,0.,0.],
             "label":0,"split":"train_candidate",
             "label_source":"independent_gt_work_record"},
        ])
    return rows


def test_cpu_model_mechanism_is_reproducible_and_non_deployed():
    records=_synthetic_numeric_pairs()
    first=fit_relation_ranker(records,holdout_ids=(1,2,3))
    second=fit_relation_ranker(records,holdout_ids=(1,2,3))
    assert first==second
    assert len(first["weights"])==len(FEATURE_NAMES)
    assert first["training_source_count"]==12
    assert first["trained_only_on_synthetic_gt"] is True
    assert first["deployed"] is False
    result=evaluate_relation_ranking(first,records)
    assert result["pair_auc"]>=.95
    assert result["top1_accuracy"]>=.95
    assert result["top1_evaluated_roles"]==12
    assert result["score_is_hiring_probability"] is False


def test_training_rejects_holdout_and_invalid_labels():
    records=_synthetic_numeric_pairs()
    with pytest.raises(ValueError,match="保留测试集"):
        fit_relation_ranker(records,holdout_ids=(21,))

    invalid=[dict(x) for x in records]
    invalid[0]={**invalid[0],"split":"holdout_evaluation"}
    with pytest.raises(ValueError,match="训练候选池"):
        fit_relation_ranker(invalid,holdout_ids=(1,2,3))

    invalid=[dict(x) for x in records]
    invalid[0]={**invalid[0],"label_source":"PaperPro_score"}
    with pytest.raises(ValueError,match="独立"):
        fit_relation_ranker(invalid,holdout_ids=())

    invalid=[dict(x) for x in records]
    invalid[0]={**invalid[0],"features":[0.1]}
    with pytest.raises(ValueError,match="特征"):
        fit_relation_ranker(invalid,holdout_ids=())


def test_heldout_evaluation_does_not_train_or_rewrite_any_rows():
    training=_synthetic_numeric_pairs()
    model=fit_relation_ranker(training,holdout_ids=(1,))
    held=[{**entry,"source_id":1,"split":"holdout_evaluation"} for entry in training[:2]]
    before=[dict(e) for e in held]
    stats=evaluate_relation_ranking(model,held)
    assert stats["top1_evaluated_roles"]==1
    assert stats["top1_accuracy"]==1.0
    assert held==before
    assert model["deployed"] is False


def test_experimental_gate_never_promotes_an_oracle_gt_relation_model(monkeypatch):
    from scripts import experiment_relation_ranker as script

    original=_synthetic_numeric_pairs()
    holdout=[
        {**r,"source_id":1+(i//2),"split":"holdout_evaluation"}
        for i,r in enumerate(original)
    ]
    def fake_collect(*,split):
        rows=original if split=="train_candidate" else holdout
        return rows,{"split":split,"pdf_count":len({r["source_id"] for r in rows})}
    monkeypatch.setattr(script,"collect_pairs",fake_collect)
    report=script.run()
    assert report["promotion_gate"]["automatic_promotion_allowed"] is False
    assert report["promotion_gate"]["heldout_top1_incremental_gain"]==0
    assert report["model_saved"] is False
    assert report["deployed"] is False
    assert report["frozen_holdout"]["fitted_ranker"]["top1_accuracy"]==1.0


def test_position_only_baseline_does_not_depend_on_model_parameters():
    a=_synthetic_numeric_pairs(1)
    good=geometry_baseline_probability(a[0]["features"])
    bad=geometry_baseline_probability(a[1]["features"])
    assert good>bad
    assert 0<=bad<=1 and 0<=good<=1
