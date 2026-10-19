"""Isolated mature PDF layout → WorkBlock development comparison.

Run:
  uv run --python 3.12 --with 'pymupdf4llm==1.28.2' python -m scripts.benchmark_layout_workblocks

Project dependencies are NOT modified. Optional AGPL/commercial-license layout
engine is only used internally for evaluation and is not integrated or shipped.
Regions remain unverified. Test uses only fixed synthetic development IDs 21–35.
GT is read AFTER the PDF geometry candidate extraction. All raw text remains
in memory; output contains counts only.
"""
from __future__ import annotations

from collections import Counter
import json
import time

import httpx
import pymupdf

from app.diagnosis.layout_workblocks import propose_workblocks_from_layout
from scripts.benchmark_annotation_alignment import _disjoint_public_blob
from scripts.benchmark_external_resume_corpus import IDS, COMMIT
from scripts.benchmark_workblock_regions import (
    TRAIN_IDS,DEV_IDS,UNSEEN_IDS,_gt_work_items,_gt_covered
)

assert set(TRAIN_IDS).isdisjoint(set(IDS)|set(DEV_IDS)|set(UNSEEN_IDS))
MATURE_VERSION="1.28.2"
OLD_GEOMETRY_PAIR_COUNT=17
OLD_LEGACY_ENTRY_PAIR_COUNT=19
OLD_BOTH_SOURCE_UNION_PAIR_COUNT=23
DENOMINATOR=32


def _mature_region_proposals(pdf_bytes: bytes) -> tuple[dict,int]:
    try:
        import pymupdf4llm
        from importlib.metadata import version
    except ImportError as error:
        raise RuntimeError(
            "需要隔离运行 --with 'pymupdf4llm==1.28.2'，未修改项目依赖"
        ) from error
    if version("pymupdf4llm")!=MATURE_VERSION:
        raise ValueError("需要锁定 PyMuPDF4LLM 1.28.2；2.0 是空兼容包")
    with pymupdf.open(stream=pdf_bytes,filetype="pdf") as document:
        if document.is_encrypted or document.page_count>25:
            raise ValueError("加密或 PDF 页数超限")
        layout_json=pymupdf4llm.to_json(
            document,use_ocr=False,show_progress=False
        )
    metadata=(
        json.loads(layout_json)
        if isinstance(layout_json,str) else layout_json
    )
    candidate=propose_workblocks_from_layout(metadata)
    return candidate,sum(
        len(page.get("boxes") or []) for page in metadata["pages"]
    )


def run(ids:tuple[int,...]=TRAIN_IDS) -> dict:
    if ids!=TRAIN_IDS:
        raise ValueError("只能评估固定训练开发池；不得访问冻结测试集")
    totals=Counter()
    safe_per_file=[]
    with httpx.Client(
        timeout=25,headers={"User-Agent":"PaperPro-isolated-layout-benchmark"}
    ) as client:
        for source_id in ids:
            pdf=_disjoint_public_blob(client,f"resume_list_pdf/{source_id}.pdf")
            t0=time.perf_counter()
            candidate,n_boxes=_mature_region_proposals(pdf)
            elapsed=time.perf_counter()-t0
            if candidate["automatic_resume_mutation"] is not False or any(
                b["status"]!="unverified" or b["auto_promote"] is not False
                for b in candidate["workblocks"]
            ):
                raise ValueError("版式候选不得修改简历或确认任职")
            gt=json.loads(_disjoint_public_blob(
                client,f"result_gt/{source_id}.json"
            ))
            truth=_gt_work_items(gt)
            counts=Counter()
            counts["gt_pairs"]=len(truth)
            counts["layout_workblocks"]=len(candidate["workblocks"])
            counts["layout_boxes"]=n_boxes
            counts["work_sections"]=candidate["source_sections"]["experience"]
            counts["parallel_pages"]=sum(
                p["parallel_section_lanes"] for p in candidate["layout_pages"]
            )
            for item in truth:
                outcome=[
                    _gt_covered(block,item)
                    for block in candidate["workblocks"]
                ]
                counts["pair_covered"]+=any(m[2] for m in outcome)
                counts["pair_and_dates_covered"]+=any(m[3] for m in outcome)
            for block in candidate["workblocks"]:
                if not any(_gt_covered(block,item)[2] for item in truth):
                    counts["blocks_without_GT_pair"]+=1
            totals.update(counts)
            safe_per_file.append({
                "source_id":source_id,"gt_pairs":counts["gt_pairs"],
                "workblocks":counts["layout_workblocks"],
                "pair_covered":counts["pair_covered"],
                "pair_and_dates":counts["pair_and_dates_covered"],
                "layout_seconds":round(elapsed,3),
            })
    if totals["gt_pairs"]!=DENOMINATOR:
        raise ValueError("开发集 GT 分母改变，拒绝本次评测")
    return {
        "experiment":"isolated_mature_PDF_layout_WorkBlock_regions",
        "engine":"pymupdf4llm",
        "engine_version":MATURE_VERSION,
        "license_note":"AGPL/commercial: research comparison only, no product integration",
        "public_synthetic_commit":COMMIT,
        "dataset_split":"development_21_35",
        "pdf_count":len(ids),
        "counts":dict(totals),
        "mature_layout_pair_coverage":round(
            totals["pair_covered"]/DENOMINATOR,4
        ),
        "mature_layout_pair_dates_coverage":round(
            totals["pair_and_dates_covered"]/DENOMINATOR,4
        ),
        "prior_same_source_comparisons":{
            "base_PyMuPDF_geometry_pairs":OLD_GEOMETRY_PAIR_COUNT,
            "base_legacy_entry_pairs":OLD_LEGACY_ENTRY_PAIR_COUNT,
            "prior_dual_source_raw_union_pairs":OLD_BOTH_SOURCE_UNION_PAIR_COUNT,
            "gt_denominator":DENOMINATOR,
        },
        "safe_per_file":safe_per_file,
        "product_dependency_changed":False,
        "production_integration_allowed":False,
        "GT_loaded_only_after_prediction":True,
        "real_resume_or_HR_validity":False,
        "fresh_holdout_read":False,
        "historical_challenge_read":False,
        "model_training_performed":False,
        "caveat":"Source text co-located in a region is not exact field extraction or hiring validation.",
    }


if __name__=="__main__":
    result=run()
    print(json.dumps({
        key:value for key,value in result.items() if key!="safe_per_file"
    },ensure_ascii=True,indent=2))
