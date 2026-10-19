"""Contract: positive-only GT becomes PARTIALLY observed BIO, never fake O labels."""
from __future__ import annotations

from hashlib import sha256

import pytest

from tests.test_span_supervision import _single_line_doc
from app.diagnosis.partial_bio import build_partial_bio, BIO_TAGS, summarize_partial_bio


def _truth():
    return {"workExperience":[
        {"companyName":"合成科技有限公司","position":"平台运营"}
    ]}


def test_two_fields_can_share_a_line_and_unknown_chars_remain_unlabeled():
    data=_single_line_doc()
    source=build_partial_bio(
        data,_truth(),source_id=21,
        allowed_train_ids=(21,22),forbidden_ids=(1,2,41)
    )
    assert source["source_id"]==21
    assert source["source_sha256"]==sha256(data).hexdigest()
    assert source["training_source_kind"]=="independent_GT_unique_char_spans"
    assert source["complete_background_annotation"] is False
    assert source["observed_O_count"]==0
    assert source["negative_background_labels_created"]==0
    assert "O" in BIO_TAGS
    assert source["positive_span_count"]==2
    assert source["known_characters"]>0
    assert source["unknown_characters"]>0
    assert source["fully_labeled_lines"]==0
    line=next(line for line in source["lines"] if "合成科技" in line["source_line"])
    assert len(line["source_line"])==len(line["tags"])==len(line["observed_mask"])
    for start,end,kind in (
        (line["source_line"].index("合成科技有限公司"),
         line["source_line"].index("合成科技有限公司")+len("合成科技有限公司"),"EMPLOYER"),
        (line["source_line"].index("平台运营"),
         line["source_line"].index("平台运营")+len("平台运营"),"WORK_ROLE")
    ):
        assert line["tags"][start]==f"B-{kind}"
        assert all(line["tags"][i]==f"I-{kind}" for i in range(start+1,end))
        assert all(line["observed_mask"][i] for i in range(start,end))
    date_indices=[i for i,c in enumerate(line["source_line"]) if c.isdigit()]
    assert date_indices
    assert all(line["tags"][i] is None and not line["observed_mask"][i] for i in date_indices)
    assert all(t is None or t in BIO_TAGS for t in line["tags"])


def test_missing_and_repeated_gt_do_not_become_negative_O():
    doc=_single_line_doc()
    truth={"workExperience":[{"position":"不存在的职业"}]}
    a=build_partial_bio(doc,truth,source_id=22,allowed_train_ids=(22,),forbidden_ids=(1,))
    assert a["positive_span_count"]==0
    assert a["observed_O_count"]==0
    assert a["known_characters"]==0
    assert all(not any(x["observed_mask"]) for x in a["lines"])


def test_no_leakage_before_any_annotation_use():
    pdf=_single_line_doc()
    with pytest.raises(ValueError,match="保留"):
        build_partial_bio(pdf,_truth(),source_id=41,
                          allowed_train_ids=(21,22),forbidden_ids=(41,))
    with pytest.raises(ValueError,match="训练来源"):
        build_partial_bio(pdf,_truth(),source_id=17,
                          allowed_train_ids=(21,22),forbidden_ids=())


def test_multiple_source_statistics_preserve_unknown_rate_without_text():
    samples=[
        build_partial_bio(_single_line_doc(),_truth(),source_id=i,
                          allowed_train_ids=(21,22),forbidden_ids=(1,2))
        for i in (21,22)
    ]
    report=summarize_partial_bio(samples)
    assert report["sources"]==2
    assert report["observed_O_count"]==0
    assert report["negative_background_labels_created"]==0
    assert report["known_positive_spans"]==4
    assert report["unknown_characters"]>0
    assert 0<report["supervised_character_fraction"]<1
    assert report["standard_supervised_BIO_ready"] is False
    assert "source_line" not in str(report)
    assert "合成科技有限公司" not in str(report)
    assert "平台运营" not in str(report)



def test_overlapping_independent_gt_values_abstain_without_background_labels():
    from app.diagnosis.partial_bio import build_partial_bio
    import pymupdf

    doc=pymupdf.open()
    page=doc.new_page()
    page.insert_font(fontname="Synthetic",fontfile="C:/Windows/Fonts/simhei.ttf")
    page.insert_text((50,90),"平台运营有限公司",fontname="Synthetic",fontsize=12)
    raw=doc.tobytes()
    doc.close()
    gt={"workExperience":[{
        "position":"平台运营",
        "companyName":"平台运营有限公司",
    }]}
    result=build_partial_bio(raw,gt,source_id=21,
                             allowed_train_ids=(21,),forbidden_ids=(1,41))
    assert result["positive_span_count"]==0
    assert result["known_characters"]==0
    assert result["observed_O_count"]==0
    assert result["negative_background_labels_created"]==0


def test_aggregate_never_exposes_raw_source_and_refuses_duplicate_records():
    import copy
    original=build_partial_bio(
        _single_line_doc(),_truth(),source_id=21,
        allowed_train_ids=(21,),forbidden_ids=(1,)
    )
    with pytest.raises(ValueError,match="重复"):
        summarize_partial_bio([original,copy.deepcopy(original)])
    safe=summarize_partial_bio([original])
    assert "source_line" not in repr(safe)
    assert "annotation_text" not in repr(safe)
    assert "合成科技" not in repr(safe)
    assert safe["negative_background_labels_created"]==0
    assert safe["observed_O_count"]==0


def test_real_cli_benchmark_prints_only_aggregate_and_keeps_holdouts_closed():
    import json
    import subprocess
    import sys

    completed=subprocess.run(
        [sys.executable,"-m","scripts.benchmark_partial_bio"],
        timeout=105,check=False,text=True,capture_output=True,
        encoding="utf-8",errors="replace",
    )
    assert completed.returncode==0,completed.stderr[-900:]
    results=json.loads(completed.stdout)
    assert results["source_count"]==15
    assert results["statistics"]["known_positive_spans"]>=50
    assert results["statistics"]["standard_supervised_BIO_ready"] is False
    assert results["development_pool_read"] is False
    assert results["fresh_holdout_read"] is False
    assert results["legacy_fixed_holdout_read"] is False
    assert results["actual_training_performed"] is False
    assert "source_line" not in completed.stdout
    assert "annotation_text" not in completed.stdout
    assert "手机号" not in completed.stdout
