"""Isolated mature layout benchmark: split guards and independent GT ordering."""
from __future__ import annotations

import json

import pytest

from scripts import benchmark_layout_workblocks as benchmark


def test_fixed_source_split_rejects_holdout_without_loading_pdf():
    for forbidden in ((41,), (1,), (21,), (21,22,23)):
        with pytest.raises(ValueError,match="固定训练开发池"):
            benchmark.run(ids=forbidden)


def test_gt_is_read_after_layout_and_never_merged_into_resume(monkeypatch):
    timeline=[]
    monkeypatch.setattr(benchmark,"TRAIN_IDS",(21,22))
    monkeypatch.setattr(benchmark,"DENOMINATOR",2)
    raw=b"%PDF-1.4\nsynthetic-only"
    gt={"workExperience":[{
        "companyName":"合成科技有限公司",
        "position":"数据分析师",
        "employmentPeriod":{
            "startDate":"2021.07","endDate":"2023.02"
        },
    }]}
    def fake_loader(_client,filename):
        if filename.endswith(".pdf"):
            timeline.append("PDF")
            return raw
        assert timeline[-1]=="LAYOUT"
        timeline.append("GT")
        return json.dumps(gt,ensure_ascii=False).encode()
    def fake_layout(pdf):
        assert pdf==raw
        assert timeline[-1]=="PDF"
        timeline.append("LAYOUT")
        return ({
            "source_sections":{"experience":1},
            "layout_pages":[{"parallel_section_lanes":False}],
            "workblocks":[{
                "source_text":"2021.07-2023.02 合成科技有限公司 数据分析师",
                "dates":{"start":"2021.07","end":"2023.02"},
                "status":"unverified","auto_promote":False,
            }],
            "automatic_resume_mutation":False,
        },3)
    monkeypatch.setattr(benchmark,"_disjoint_public_blob",fake_loader)
    monkeypatch.setattr(benchmark,"_mature_region_proposals",fake_layout)
    stats=benchmark.run(ids=(21,22))
    assert timeline==["PDF","LAYOUT","GT"]*2
    assert stats["counts"]["gt_pairs"]==2
    assert stats["counts"]["pair_covered"]==2
    assert stats["production_integration_allowed"] is False
    assert stats["GT_loaded_only_after_prediction"] is True
    assert stats["fresh_holdout_read"] is False
    assert stats["historical_challenge_read"] is False
    assert stats["model_training_performed"] is False
    assert "source_text" not in str({
        k:v for k,v in stats.items() if k!="safe_per_file"
    })


def test_layout_engine_refuses_unavailable_dependency_without_adding_it():
    import importlib.util
    from pathlib import Path

    # The repository itself must not acquire the optional AGPL engine.
    assert importlib.util.find_spec("pymupdf4llm") is None
    original=Path("pyproject.toml").read_text(encoding="utf-8")
    assert "pymupdf4llm" not in original
    with pytest.raises(RuntimeError,match="隔离运行"):
        benchmark._mature_region_proposals(b"%PDF-1.4\n")
