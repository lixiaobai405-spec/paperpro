"""Experimental GT-blind company/role CHAR-SPAN proposals, red-first contract."""
from __future__ import annotations

from hashlib import sha256
import inspect

import pytest

from app.diagnosis.span_proposer import (
    fit_positive_span_proposer,
    propose_pdf_char_spans,
)
from scripts.benchmark_external_resume_corpus import IDS
from tests.test_span_supervision import _single_line_doc
from tests.test_work_relation_geometry import _pdf


def _labeled_bundle(source_id: int):
    from app.diagnosis.span_supervision import align_gt_char_spans
    raw=_single_line_doc()
    gt={"workExperience":[{
        "companyName":"合成科技有限公司",
        "position":"平台运营",
    }]}
    aligned=align_gt_char_spans(raw,gt)
    return {
        "source_id":source_id,
        "positive_spans":aligned["positive_spans"],
        "unlabeled_character_negatives_created":0,
    }


def test_train_only_gt_positive_spans_and_never_fit_holdout():
    rows=[_labeled_bundle(i) for i in (21,22,23)]
    model=fit_positive_span_proposer(
        rows,allowed_source_ids=(21,22,23),
        forbidden_source_ids=IDS,
    )
    assert model["deployed"] is False
    assert model["calibrated"] is False
    assert model["trained_on_unknown_characters"] is False
    assert model["trained_on_independent_gt_only"] is True
    assert model["training_source_count"]==3
    assert set(model["field_suffixes"])=={"work_role","employer"}
    with pytest.raises(ValueError,match="保留|训练"):
        fit_positive_span_proposer(
            rows,allowed_source_ids=(21,22,23),
            forbidden_source_ids=(21,),
        )
    bad=[dict(rows[0])]
    bad[0]["positive_spans"]=[{
        **rows[0]["positive_spans"][0],"label_source":"self_score",
    }]
    with pytest.raises(ValueError,match="独立"):
        fit_positive_span_proposer(
            bad,allowed_source_ids=(21,),
            forbidden_source_ids=(),
        )


def test_literal_offsets_of_multi_field_proposals_and_no_gt_in_inference():
    from app.diagnosis.span_supervision import align_gt_char_spans
    raw=_single_line_doc()
    training=[_labeled_bundle(i) for i in (21,22,23)]
    model=fit_positive_span_proposer(
        training,allowed_source_ids=(21,22,23),
        forbidden_source_ids=IDS,
    )
    assert "annotation" not in inspect.signature(propose_pdf_char_spans).parameters
    assert "gt" not in inspect.signature(propose_pdf_char_spans).parameters
    before=sha256(raw).hexdigest()
    hits=propose_pdf_char_spans(raw,model,per_field=10)
    assert hits==propose_pdf_char_spans(raw,model,per_field=10)
    assert sha256(raw).hexdigest()==before
    assert hits
    assert all(row["proposed_text"]==
               row["source_line"][row["start_char"]:row["end_char"]]
               for row in hits)
    assert all(row["status"]=="unverified"
               and row["automatic_resume_mutation"] is False
               and row["ranking_score_is_probability"] is False
               and row["confidence"]["calibrated"] is False
               and row["ready_for_training"] is False for row in hits)
    assert all(row["field"] in ("work_role","employer") for row in hits)
    assert len([r for r in hits if r["field"]=="work_role"])<=10
    assert len([r for r in hits if r["field"]=="employer"])<=10
    assert any(r["proposed_text"]=="合成科技有限公司"
               for r in hits if r["field"]=="employer")
    assert any(r["proposed_text"]=="平台运营"
               for r in hits if r["field"]=="work_role")


def test_unseen_hobby_phone_and_header_never_mutate_resume():
    model=fit_positive_span_proposer(
        [_labeled_bundle(i) for i in (21,22,23)],
        allowed_source_ids=(21,22,23),forbidden_source_ids=IDS
    )
    bad_pdf=_pdf(role="13800138000",organization="陶艺兴趣小组")
    hits=propose_pdf_char_spans(bad_pdf,model,per_field=8)
    assert not any("13800138000" in item["proposed_text"] for item in hits)
    assert not any(item["proposed_text"]=="工作经历" for item in hits)
    assert all("resume" not in item and "experience" not in item for item in hits)
    assert not any(item["ranking_score_is_probability"] for item in hits)


def test_invalid_proposal_budget_and_weights_fail_closed():
    model=fit_positive_span_proposer(
        [_labeled_bundle(i) for i in (21,22,23)],
        allowed_source_ids=(21,22,23),forbidden_source_ids=IDS
    )
    with pytest.raises(ValueError):
        propose_pdf_char_spans(_single_line_doc(),model,per_field=0)
    with pytest.raises(ValueError):
        propose_pdf_char_spans(b"%PDF-1.7\nfake",{"deployed":True},per_field=8)
