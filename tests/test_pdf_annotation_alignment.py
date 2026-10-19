"""Native PDF span alignment: independent external labels, no score-generated GT.

The fixed 20 external challenge files are protected holdouts, never training.
Only unique source-line locations are considered alignment candidates; absence
or duplicate text is NOT a negative class label.
"""
from __future__ import annotations

import pymupdf
import pytest

from tests.test_work_relation_geometry import _pdf
from scripts.benchmark_external_resume_corpus import IDS
from app.diagnosis.annotation_alignment import (
    align_independent_annotations, prohibit_holdout_training,
)


def test_gt_role_and_employer_align_to_native_text_on_same_page():
    content = _pdf()
    gt = {
        "workExperience":[{
            "position":"平台运营",
            "companyName":"虚构技术有限公司",
        }],
        "education":[],
    }
    result = align_independent_annotations(content, gt)
    assert result["field_counts"]["work_role"]["expected"]==1
    assert result["field_counts"]["work_role"]["unique_native_line"]==1
    assert result["field_counts"]["employer"]["expected"]==1
    assert result["field_counts"]["employer"]["unique_native_line"]==1
    labels=result["unique_anchors"]
    role=next(a for a in labels if a["field"]=="work_role")
    employer=next(a for a in labels if a["field"]=="employer")
    assert role["page_index"]==0
    assert employer["page_index"]==role["page_index"]
    assert role["line_bbox"]!=employer["line_bbox"]
    assert all(0<=v<=1 for v in role["line_bbox"])
    assert role["line_bbox"][2]>role["line_bbox"][0]
    assert role["line_bbox"][3]>role["line_bbox"][1]
    assert role["alignment_confidence"]=="text_location_only"
    assert role["ready_for_training"] is False
    assert "平台运营" in role["source_line"]
    assert result["labels_are_hiring_outcomes"] is False


def test_repeated_text_does_not_become_unique_supervised_example():
    content = _pdf()
    doc=pymupdf.open(stream=content,filetype="pdf")
    page=doc[0]
    page.insert_font(fontname="FixtureCN",fontfile="C:/Windows/Fonts/simhei.ttf")
    page.insert_text((398,420),"平台运营",fontsize=11,fontname="FixtureCN")
    duplicated=doc.tobytes()
    doc.close()
    result=align_independent_annotations(duplicated,{
        "workExperience":[{"position":"平台运营"}]
    })
    stats=result["field_counts"]["work_role"]
    assert stats["expected"]==1
    assert stats["unique_native_line"]==0
    assert stats["ambiguous_multiple_lines"]==1
    assert result["unique_anchors"]==[]


def test_missing_label_has_no_silent_negative_training_examples():
    content=_pdf()
    result=align_independent_annotations(content,{
        "workExperience":[{"position":"不存在的职位"}]
    })
    stats=result["field_counts"]["work_role"]
    assert stats["not_found_in_native_lines"]==1
    assert result["unique_anchors"]==[]
    assert result["negative_examples_generated"]==0


def test_fixed_challenge_ids_are_never_allowed_into_training():
    for source_id in (1,10,101,105,201,205):
        assert source_id in IDS
        with pytest.raises(ValueError,match="保留测试集"):
            prohibit_holdout_training(source_id,holdout_ids=IDS)
    prohibit_holdout_training(299,holdout_ids=IDS)



def test_training_pool_and_fixed_holdout_are_disjoint_by_construction():
    from scripts.benchmark_annotation_alignment import (
        TRAIN_POOL_IDS, run,
    )
    assert len(TRAIN_POOL_IDS) == 20
    assert set(TRAIN_POOL_IDS).isdisjoint(IDS)
    # Both guards must fail before any source download or model training.
    with pytest.raises(ValueError,match="保留测试集"):
        run((IDS[0],),split="train_candidate_feasibility")
    with pytest.raises(ValueError,match="保留集"):
        run((TRAIN_POOL_IDS[0],),split="holdout_evaluation")



def test_same_row_relation_signal_requires_independently_unique_both_fields():
    from app.diagnosis.annotation_alignment import measure_work_relation_alignment

    raw = _pdf()
    truth = {"workExperience":[{
        "position":"平台运营",
        "companyName":"虚构技术有限公司",
    }]}
    anchors = align_independent_annotations(raw, truth)
    signal = measure_work_relation_alignment(anchors, truth)
    assert signal["annotated_pairs"]==1
    assert signal["both_uniquely_anchored"]==1
    assert signal["same_page"]==1
    assert signal["same_visual_row"]==1
    assert signal["nearby_on_same_page"]==1
    assert signal["training_pairs_emitted"]==0

    # A guessed employer or repeated role must never become a labeled pair.
    unrelated = {"workExperience":[{
        "position":"平台运营",
        "companyName":"不存在的集团",
    }]}
    signal = measure_work_relation_alignment(
        align_independent_annotations(raw, unrelated), unrelated
    )
    assert signal["annotated_pairs"]==1
    assert signal["both_uniquely_anchored"]==0
    assert signal["same_visual_row"]==0


def test_disjoint_pool_fetch_bypasses_global_git_https_to_ssh_rewrite(monkeypatch, tmp_path):
    from subprocess import CompletedProcess
    from scripts import benchmark_annotation_alignment as benchmark

    cache=tmp_path/"public-fixture"
    (cache/".git").mkdir(parents=True)
    monkeypatch.setattr(benchmark,"GIT_CACHE",cache)
    called=[]
    class Offline:
        def get(self,*_args,**_kwargs):
            raise AssertionError("Avoid rate-limited REST API when pinned Git cache exists")
    def fake_run(args,**kwargs):
        called.append((args,kwargs))
        if args[-2:] == ["rev-parse","HEAD"]:
            return CompletedProcess(args,0,stdout=benchmark.COMMIT+"\n")
        assert "show" in args and benchmark.COMMIT+":resume_list_pdf/21.pdf" in args
        assert kwargs['env']['GIT_CONFIG_GLOBAL'].lower() in {'nul', '/dev/null'}
        assert kwargs['env']['GIT_TERMINAL_PROMPT'] == '0'
        assert 'show' in args
        assert kwargs["timeout"]<=60
        return CompletedProcess(args,0,stdout=b"%PDF-1.6\nSYNTHE_TIC")
    monkeypatch.setattr(benchmark.subprocess,"run",fake_run)
    result=benchmark._disjoint_public_blob(Offline(),"resume_list_pdf/21.pdf")
    assert result.startswith(b"%PDF-")
    assert len(called)==2
    assert all(call[1]['env']['GIT_CONFIG_GLOBAL'].lower() in {'nul','/dev/null'}
               for call in called[1:])


def test_disjoint_pool_refuses_wrong_commit_before_blob_read(monkeypatch,tmp_path):
    from subprocess import CompletedProcess
    from scripts import benchmark_annotation_alignment as benchmark

    cache=tmp_path/"public-fixture"
    (cache/".git").mkdir(parents=True)
    monkeypatch.setattr(benchmark,"GIT_CACHE",cache)
    seen=[]
    def wrong_head(args,**kwargs):
        seen.append(args)
        return CompletedProcess(args,0,stdout="0"*40+"\n")
    monkeypatch.setattr(benchmark.subprocess,"run",wrong_head)
    with pytest.raises(ValueError,match="固定"):
        benchmark._disjoint_public_blob(None,"resume_list_pdf/21.pdf")
    assert len(seen)==1
