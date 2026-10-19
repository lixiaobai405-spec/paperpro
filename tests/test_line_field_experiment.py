"""Predeclared dev gate: a failed classifier must not read new frozen GT."""
from __future__ import annotations

import pytest

from scripts import experiment_line_field_classifier as experiment
from scripts.benchmark_external_resume_corpus import IDS


def _report(learn_role=5,learn_company=7,candidate_lines=40,old_role=10,old_company=10,old_lines=20):
    def row(hits,lines):
        return {"GT_hits":hits,"candidate_lines":lines}
    return {
        "methods":{
            "learned_topk":{
                "work_role":row(learn_role,candidate_lines),
                "employer":row(learn_company,candidate_lines),
            },
            "legacy_equal_budget":{
                "work_role":row(old_role,21),
                "employer":row(old_company,12),
            },
            "legacy_full":{
                "work_role":row(old_role,old_lines),
                "employer":row(old_company,old_lines),
            },
        }
    }


def test_previous_bad_development_result_cannot_open_fresh_holdout():
    gate=experiment._development_gate(_report())
    assert gate["pass"] is False
    assert gate["GT_coverage_deltas"]=={"work_role":-5,"employer":-3}
    assert gate["frozen_new_test_allowed"] is False

    expensive=experiment._development_gate(
        _report(learn_role=12,learn_company=12,candidate_lines=40)
    )
    assert expensive["pass"] is False
    assert expensive["learned_review_lines"]>1.5*expensive["legacy_full_review_lines"]

    good=experiment._development_gate(
        _report(learn_role=11,learn_company=11,candidate_lines=16)
    )
    assert good["pass"] is True


def test_run_must_abort_before_fetching_untouched_holdout(monkeypatch):
    invoked=[]
    monkeypatch.setattr(
        experiment,"fit_frozen_training_pool",
        lambda client,training_ids:(
            {"class_names":["work_role","employer","school"],
             "hyperparameters":{}},
            {"pdfs":len(training_ids)},
        )
    )
    def dev_only(_client,_model,*,name,ids):
        invoked.append((name,ids))
        assert name=="development_validation"
        return _report()
    monkeypatch.setattr(experiment,"evaluate_split",dev_only)
    result=experiment.run(target_split="new_unseen_test",training="small")
    assert result["fresh_test_read"] is False
    assert result["predeclared_gate"]["pass"] is False
    assert invoked==[("development_validation",experiment.DEV_IDS)]


def test_predeclared_data_splits_are_exclusive_and_fixed():
    assert len(experiment.TRAIN_IDS)==15
    assert len(experiment.EXTRA_TRAIN_IDS)==20
    assert len(experiment.DEV_IDS)==5
    assert len(experiment.NEW_TEST_IDS)==20
    groups=[
        set(experiment.EXPANDED_TRAIN_IDS),
        set(experiment.DEV_IDS),
        set(experiment.NEW_TEST_IDS),
        set(IDS),
    ]
    assert all(groups[i].isdisjoint(groups[j])
               for i in range(len(groups)) for j in range(i+1,len(groups)))


def test_no_implicit_train_from_fixed_test_group():
    with pytest.raises(ValueError,match="预先固定"):
        experiment.fit_frozen_training_pool(
            None,training_ids=experiment.DEV_IDS
        )
