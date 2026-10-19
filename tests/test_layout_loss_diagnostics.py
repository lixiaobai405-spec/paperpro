"""Protect the offline layout-failure attribution and the research-only policy.

No third-party PDF contents, independent GT, or model weights are loaded by
these tests. A mature layout experiment has no authority to rewrite a resume.
"""
from __future__ import annotations

import copy
import inspect

import pytest

from app.diagnosis.layout_workblocks import propose_workblocks_from_layout
from scripts import diagnose_mature_layout_loss as probe
from tests.test_layout_workblocks import _layout, _box


def test_failure_attribution_rejects_any_non_development_sources_without_io():
    for forbidden in ((41,), (1,), (21,), tuple(range(21,36))+(41,)):
        with pytest.raises(ValueError,match="固定"):
            probe.run(ids=forbidden)


def test_exploratory_typographic_boundary_preserves_source_and_is_not_job_fact():
    fixture=_layout()
    fixture["pages"][0]["boxes"].insert(
        9,_box("额外样式标题",36,235,kind="section-header")
    )
    snapshot=copy.deepcopy(fixture)
    conservative=propose_workblocks_from_layout(fixture)
    exploratory=propose_workblocks_from_layout(
        fixture,unknown_heading_policy="keep"
    )
    assert fixture==snapshot
    assert conservative["experimental_unknown_heading_policy"]=="close"
    assert exploratory["experimental_unknown_heading_policy"]=="keep"
    assert conservative["candidate_count"]==1
    assert exploratory["candidate_count"]==2
    for result in (conservative,exploratory):
        assert result["automatic_resume_mutation"] is False
        assert result["deployed"] is False
        assert result["requires_human_confirmation"] is True
        assert all(x["status"]=="unverified" and not x["auto_promote"]
                   for x in result["workblocks"])
        assert all("company" not in x and "role" not in x
                   for x in result["workblocks"])
        assert all("虚构校园项目甲" not in x["source_text"]
                   for x in result["workblocks"])


def test_optional_external_engine_never_leaks_into_product_inference_arguments():
    signature=inspect.signature(propose_workblocks_from_layout)
    assert "independent_GT" not in signature.parameters
    assert "annotations" not in signature.parameters
    assert "gt" not in signature.parameters
    assert "unknown_heading_policy" in signature.parameters
    assert signature.parameters["unknown_heading_policy"].default=="close"
