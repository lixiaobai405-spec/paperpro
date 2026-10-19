"""GT-blind field discovery evaluation contracts.

Holdout IDs are never permitted in development; GT is used after proposing
candidate lines, solely to compute source-coverage and review-load metrics.
"""
from __future__ import annotations

import json
import pytest

from scripts.benchmark_external_resume_corpus import IDS
from scripts import benchmark_native_candidate_lines as benchmark
from tests.test_work_relation_geometry import _pdf


def test_gt_annotations_are_read_only_after_gt_blind_proposal(monkeypatch):
    timeline=[]
    original=_pdf()
    gt={
        "workExperience":[{
            "position":"平台运营",
            "companyName":"虚构技术有限公司"
        }],
    }
    def fake_loader(_client,filename):
        if filename.endswith(".pdf"):
            timeline.append("pdf_loaded")
            return original
        timeline.append("gt_loaded")
        return json.dumps(gt,ensure_ascii=False).encode()
    def fake_candidate(blob):
        assert blob==original
        assert timeline==["pdf_loaded"]
        timeline.append("proposal_without_gt")
        return [{
            "field":"work_role","source_line":"平台运营",
            "status":"unverified","automatic_resume_mutation":False
        },{
            "field":"employer","source_line":"虚构技术有限公司",
            "status":"unverified","automatic_resume_mutation":False
        }]
    monkeypatch.setattr(benchmark,"_disjoint_public_blob",fake_loader)
    monkeypatch.setattr(benchmark,"propose_pdf_field_lines",fake_candidate)
    report=benchmark.run(split="train_candidate_feasibility",ids=(21,))
    assert timeline==[
        "pdf_loaded","proposal_without_gt","gt_loaded"
    ]
    assert report["fields"]["work_role"]["gt_items_with_candidate_line"]==1
    assert report["fields"]["employer"]["gt_items_with_candidate_line"]==1
    assert report["fields"]["work_role"]["gt_items_present_in_native_text"]==1
    assert report["fields"]["employer"]["native_text_upper_bound"]==1
    assert report["fields"]["work_role"]["candidate_coverage_given_native_text"]==1
    assert report["candidate_auto_adopted"] is False
    assert report["candidate_precision_validated"] is False
    assert report["true_negative_labels_inferred"]==0


def test_unannotated_line_is_unknown_not_a_false_positive_label():
    from scripts.benchmark_native_candidate_lines import _score_candidates

    proposals=[
        {"field":"work_role","source_line":"平台运营"},
        {"field":"work_role","source_line":"其他可能的职位"},
        {"field":"employer","source_line":"虚构技术有限公司"},
    ]
    labels={"workExperience":[{
        "position":"平台运营","companyName":"虚构技术有限公司"
    }]}
    measured=_score_candidates(proposals,labels)
    assert measured["work_role"]["candidate_lines_not_verified_by_gt"]==1
    assert "false_positive" not in str(measured).lower()
    assert measured["work_role"]["gt_items_with_candidate_line"]==1


def test_holdout_source_cannot_be_evaluated_as_train_candidate():
    with pytest.raises(ValueError,match="无法读取"):
        benchmark.run(split="train_candidate_feasibility",ids=(IDS[0],))
    with pytest.raises(ValueError,match="无法读取"):
        benchmark.run(split="holdout_evaluation",ids=(21,))
    with pytest.raises(ValueError,match="未知"):
        benchmark.run(split="wrong")


def test_candidate_source_line_is_not_a_structured_resume_field():
    from app.diagnosis.native_candidate_lines import propose_pdf_field_lines
    rows=propose_pdf_field_lines(_pdf())
    assert rows
    assert all(row["ready_for_training"] is False for row in rows)
    assert not any("suggested_company" in row or "suggested_role" in row
                   or "score" in row for row in rows)
