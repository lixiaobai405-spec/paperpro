"""Frozen split / GT-blind ordering / safe rejection of span proposer."""
from __future__ import annotations

import inspect
import json

from scripts import experiment_span_proposer as experiment
from scripts.benchmark_external_resume_corpus import IDS
from tests.test_span_supervision import _single_line_doc


def _comparison(
    role_exact=4, company_exact=9,
    role_old=10,company_old=10,
    new_review=18,old_review=33
):
    def row(exact,coverage,review):
        return {
            "full_field_exact_hits":exact,
            "source_line_containment_hits":coverage,
            "review_items":review,
        }
    return {
        "methods":{
            "span_proposer":{
                "work_role":row(role_exact,role_exact,8),
                "employer":row(company_exact,company_exact,new_review-8),
            },
            "old_equal_budget":{
                "work_role":row(0,role_old,12),
                "employer":row(0,company_old,11),
            },
            "old_full":{
                "work_role":row(0,role_old,old_review//2),
                "employer":row(0,company_old,old_review-old_review//2),
            },
        }
    }


def test_predeclared_dev_gate_refuses_inferior_spans():
    result=experiment._gate(_comparison())
    assert result["pass"] is False
    assert result["frozen_test_access_allowed"] is False
    assert result["exact_span_vs_old_line_coverage_deltas"]=={
        "work_role":-6,"employer":-1
    }
    allowed=experiment._gate(
        _comparison(role_exact=10,company_exact=11,new_review=25)
    )
    assert allowed["pass"] is True


def test_gt_loaded_only_after_both_proposal_algorithms(monkeypatch):
    pdf=_single_line_doc()
    gt={"workExperience":[{
        "companyName":"合成科技有限公司","position":"平台运营"
    }]}
    history=[]
    def fetch(_client,filename):
        if filename.endswith(".pdf"):
            history.append("PDF")
            return pdf
        history.append("GT")
        assert history==["PDF","span_GT_blind","old_GT_blind","GT"]
        return json.dumps(gt,ensure_ascii=False).encode("utf-8")
    def learned(raw,_model,*,per_field):
        assert raw==pdf
        history.append("span_GT_blind")
        return [
            {"field":"work_role","source_line":"平台运营",
             "proposed_text":"平台运营","status":"unverified",
             "ranking_score_is_probability":False,
             "automatic_resume_mutation":False},
            {"field":"employer","source_line":"合成科技有限公司",
             "proposed_text":"合成科技有限公司",
             "status":"unverified",
             "ranking_score_is_probability":False,
             "automatic_resume_mutation":False},
        ]
    def baseline(raw,*,max_candidates_per_field):
        assert raw==pdf
        history.append("old_GT_blind")
        return [
            {"field":"work_role","source_line":"平台运营"},
            {"field":"employer","source_line":"合成科技有限公司"},
        ]
    monkeypatch.setattr(experiment,"_disjoint_public_blob",fetch)
    monkeypatch.setattr(experiment,"propose_pdf_char_spans",learned)
    monkeypatch.setattr(experiment,"propose_pdf_field_lines",baseline)
    monkeypatch.setattr(experiment,"DEV_IDS",(36,))
    data=experiment.evaluate(
        None,{},split="development",source_ids=(36,)
    )
    assert history==["PDF","span_GT_blind","old_GT_blind","GT"]
    assert data["fixed_GT_denominators"]=={
        "work_role":1,"employer":1
    }
    assert data["no_background_negatives"] is True
    assert data["produced_any_job_record"] is False


def test_failed_gate_never_opens_fresh_41_60_files(monkeypatch):
    seen=[]
    monkeypatch.setattr(
        experiment,"_train",
        lambda client:({"deployed":False},{"pdfs":15},set())
    )
    def mock_evaluate(_client,_model,*,split,source_ids,
                      forbidden_hashes):
        seen.append(split)
        assert split=="development"
        return _comparison()
    monkeypatch.setattr(experiment,"evaluate",mock_evaluate)
    result=experiment.run(split="new_unseen_test")
    assert result["new_test_read"] is False
    assert result["development_gate"]["pass"] is False
    assert result["new_holdout"] is None
    assert seen==["development"]


def test_fixed_splits_are_separate_and_the_span_model_does_not_require_gt():
    assert len(experiment.TRAIN_IDS)==15
    assert len(experiment.DEV_IDS)==5
    assert len(experiment.NEW_TEST_IDS)==20
    groups=[set(experiment.TRAIN_IDS),set(experiment.DEV_IDS),
            set(experiment.NEW_TEST_IDS),set(IDS)]
    assert all(groups[i].isdisjoint(groups[j])
               for i in range(len(groups))
               for j in range(i+1,len(groups)))
    assert "annotation" not in inspect.signature(
        experiment.propose_pdf_char_spans
    ).parameters
    assert "gt" not in inspect.signature(
        experiment.propose_pdf_char_spans
    ).parameters
