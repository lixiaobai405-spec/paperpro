"""WorkBlock benchmark: GT after extraction, split protected, no invented facts."""
from __future__ import annotations

import json

import pytest

from scripts import benchmark_workblock_regions as benchmark
from tests.test_workblock_regions import _make_pdf


def test_fixed_source_ids_reject_holdouts_before_any_data_request():
    with pytest.raises(ValueError,match="禁止改变"):
        benchmark.run(ids=(41,))
    with pytest.raises(ValueError,match="禁止改变"):
        benchmark.run(ids=(1,))
    with pytest.raises(ValueError,match="禁止改变"):
        benchmark.run(ids=(21,))


def test_independent_gt_is_not_read_until_both_extractors_finish(monkeypatch):
    import copy
    timeline=[]
    pdf=_make_pdf()
    truth={"workExperience":[{
        "companyName":"合成技术有限公司",
        "position":"平台开发工程师",
        "employmentPeriod":{"startDate":"2021.07","endDate":"2023.02"},
    }]}
    original=benchmark.propose_pdf_workblocks
    def proposed(raw):
        timeline.append("native_workblock")
        return original(raw)
    monkeypatch.setattr(benchmark,"propose_pdf_workblocks",proposed)
    original_extract=benchmark.extract_file
    def old_read(filename,raw):
        timeline.append("legacy_pdf")
        return original_extract(filename,raw)
    monkeypatch.setattr(benchmark,"extract_file",old_read)
    def loader(_client,filename):
        if filename.endswith(".pdf"):
            timeline.append("pdf")
            return pdf
        assert timeline==["pdf","native_workblock","legacy_pdf"]
        timeline.append("independent_GT")
        return json.dumps(truth,ensure_ascii=False).encode()
    monkeypatch.setattr(benchmark,"_disjoint_public_blob",loader)
    monkeypatch.setattr(benchmark,"TRAIN_IDS",(21,))
    result=benchmark.run(ids=(21,))
    assert timeline==["pdf","native_workblock","legacy_pdf","independent_GT"]
    assert result["aggregate"]["expected_pairs"]==1
    assert result["aggregate"]["gt_pair_in_same_block"]==1
    assert result["aggregate"]["gt_pair_and_period_in_same_block"]==1
    assert result["candidate_resume_mutated"] is False
    assert result["deployed"] is False
    assert result["heldout_41_60_read"] is False
    assert result["legacy_20_PDF_holdout_read"] is False
    assert result["promotion_gate"]["pass"] is False
    assert result["promotion_gate"]["production_integration_allowed"] is False
    assert result["promotion_gate"]["frozen_holdout_access_allowed"] is False
    assert "source_text" not in repr(result)
    assert "合成技术有限公司" not in repr(result)
    assert "平台开发工程师" not in repr(result)


def test_raw_source_region_containment_is_not_a_structured_employment_fact():
    raw=_make_pdf()
    blocks=benchmark.propose_pdf_workblocks(raw)["workblocks"]
    assert blocks
    for block in blocks:
        assert "company" not in block
        assert "role" not in block
        assert "job_confirmed" not in block
        assert block["auto_promote"] is False
        assert block["confidence"]["calibrated"] is False
        assert block["status"]=="unverified"


def test_workblock_benchmark_denominator_is_independent_field_pair_count():
    extracted=benchmark._gt_work_items({
        "workExperience":[
            {"companyName":"合成技术有限公司",
             "position":"平台开发工程师",
             "employmentPeriod":{"startDate":"2021.07","endDate":"2023.02"}},
            {"companyName":"缺失职位的公司","position":""},
            {"companyName":"","position":"缺失公司的职位"},
        ]
    })
    assert len(extracted)==1
    b={
        "source_text":"2021.07-2023.02 合成技术有限公司 平台开发工程师",
        "dates":{"start":"2021.07","end":"2023.02"}
    }
    assert benchmark._gt_covered(b,extracted[0])==(True,True,True,True)
    other={**b,"dates":{"start":"2021.07","end":"2024.01"}}
    assert benchmark._gt_covered(other,extracted[0])==(True,True,True,False)
