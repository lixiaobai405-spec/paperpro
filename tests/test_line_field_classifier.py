"""Contract: independently supervised native-PDF line recognition.

All fixture records are synthetic. No background/unannotated text is ever
marked as a negative class. Unknown and ambiguous GT alignments abstain.
The model can propose source lines only; never a job fact or hiring score.
"""
from __future__ import annotations

import copy
from hashlib import sha256

import pytest
import pymupdf

from app.diagnosis.line_field_classifier import (
    FIELD_CLASSES, build_verified_line_labels,
    fit_line_field_model, propose_line_fields,
)
from tests.test_work_relation_geometry import _pdf
from scripts.benchmark_external_resume_corpus import IDS


def _annotation():
    return {
        "workExperience":[{
            "position":"平台运营","companyName":"虚构技术有限公司",
        }],
    }


def test_no_background_labels_and_unique_source_anchors():
    pdf=_pdf()
    bundle=build_verified_line_labels(
        pdf,_annotation(),source_id=25,forbidden_ids=IDS,
    )
    assert bundle["source_id"]==25
    assert set(bundle["class_counts"])==set(FIELD_CLASSES)
    assert bundle["class_counts"]["work_role"]==1
    assert bundle["class_counts"]["employer"]==1
    assert bundle["negative_background_labels_created"]==0
    assert all(item["label"] in FIELD_CLASSES for item in bundle["rows"])
    assert all("source_line" not in item and "annotation_text" not in item
               for item in bundle["rows"])
    assert len(bundle["rows"])==2


def test_no_leakage_from_fixed_or_new_holdout_into_fit():
    raw=_pdf()
    with pytest.raises(ValueError,match="保留"):
        build_verified_line_labels(
            raw,_annotation(),source_id=IDS[0],forbidden_ids=IDS,
        )
    bundle=build_verified_line_labels(raw,_annotation(),source_id=25,
                                     forbidden_ids=IDS)
    with pytest.raises(ValueError,match="训练"):
        fit_line_field_model(
            [bundle], allowed_train_ids=(21,22,23,24),
        )
    other=copy.deepcopy(bundle)
    other["source_id"]=41
    with pytest.raises(ValueError,match="训练"):
        fit_line_field_model(
            [bundle,other],allowed_train_ids=tuple(range(21,41)),
        )


def test_ambiguous_multi_class_source_line_never_becomes_one_sided_negative():
    pdf=_pdf()
    mixed={
        "workExperience":[{
            "position":"虚构技术有限公司",
            "companyName":"虚构技术有限公司",
        }],
    }
    bundle=build_verified_line_labels(
        pdf,mixed,source_id=24,forbidden_ids=IDS,
    )
    assert bundle["rows"]==[]
    assert bundle["ambiguous_gt_line_count"]>=1


def test_small_cpu_fitter_and_inference_repeatable_without_gt(tmp_path):
    import numpy as np
    bundles=[]
    for i in range(21,27):
        b=build_verified_line_labels(
            _pdf(extra_row=(i%2==1)), _annotation(),
            source_id=i,forbidden_ids=IDS,
        )
        bundles.append(b)
    model=fit_line_field_model(bundles,allowed_train_ids=tuple(range(21,27)))
    assert model["deployed"] is False
    assert model["calibrated"] is False
    assert model["train_sources"]==6
    assert model["trained_on_unknown_lines"] is False
    assert model["trained_on_hiring_outcomes"] is False

    raw=_pdf()
    before=sha256(raw).hexdigest()
    found=propose_line_fields(raw,model,per_field=6)
    assert found==propose_line_fields(raw,model,per_field=6)
    assert sha256(raw).hexdigest()==before
    assert {r["field"] for r in found}.issubset({"work_role","employer"})
    assert all(r["status"]=="unverified"
               and r["automatic_resume_mutation"] is False
               and r["ranking_score_is_probability"] is False
               and r["confidence"]["calibrated"] is False
               and r["ready_for_training"] is False
               for r in found)
    assert list(tmp_path.iterdir())==[]


def test_unseen_pdf_prediction_never_requests_annotations():
    repeated=[
        build_verified_line_labels(
            _pdf(),_annotation(),source_id=source,forbidden_ids=IDS
        )
        for source in (21,22,23)
    ]
    model=fit_line_field_model(
        repeated,allowed_train_ids=(21,22,23),
    )
    assert "annotation" not in propose_line_fields.__code__.co_varnames
    assert "gt" not in propose_line_fields.__code__.co_varnames
    proposed=propose_line_fields(_pdf(),model,per_field=3)
    assert len([item for item in proposed if item["field"]=="employer"])<=3
    assert len([item for item in proposed if item["field"]=="work_role"])<=3
