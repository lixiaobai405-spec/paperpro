"""Diagnose *where* mature-layout→WorkBlock drops independently labeled GT.

TRAIN/DEV ONLY: public synthetic source IDs 21–35, fixed pinned Git commit.
All engines run BEFORE third-party GT is loaded. No CV strings, names,
employer or role text, original PDF bytes, or inferred facts leave memory.

Research-only: isolates whether failure comes from missing model-extracted
text, section recognition, or work-region grouping. Does not rewrite the
production PDF parser, resume schema, or scoring.
"""
from __future__ import annotations

from collections import Counter
import json
import time
import httpx
import pymupdf

from app.parser import _section
from app.diagnosis.annotation_alignment import _native_lines
from app.diagnosis.layout_workblocks import (
    _validated_layout_lines, propose_workblocks_from_layout,
)
from app.diagnosis.workblock_regions import propose_pdf_workblocks
from scripts.benchmark_annotation_alignment import _disjoint_public_blob
from scripts.benchmark_external_resume_corpus import COMMIT, IDS, normalized
from scripts.benchmark_workblock_regions import (
    TRAIN_IDS, DEV_IDS, UNSEEN_IDS, _gt_covered, _gt_work_items,
)

assert set(TRAIN_IDS).isdisjoint(set(IDS)|set(DEV_IDS)|set(UNSEEN_IDS))


def _native_model_layout(pdf: bytes) -> dict:
    """Real optional external layout engine; never a mocked model."""
    from importlib.metadata import version
    import pymupdf4llm
    if version("pymupdf4llm")!="1.28.2":
        raise RuntimeError("Only isolated pymupdf4llm==1.28.2 is supported")
    with pymupdf.open(stream=pdf,filetype="pdf") as document:
        if document.is_encrypted or document.page_count>25:
            raise ValueError("PDF source rejected")
        content=pymupdf4llm.to_json(
            document, use_ocr=False, show_progress=False
        )
    return json.loads(content) if isinstance(content,str) else content


def run(ids: tuple[int,...]=TRAIN_IDS) -> dict:
    if ids!=TRAIN_IDS:
        raise ValueError("固定 21–35 开发池不得替换成冻结样本")
    total=Counter()
    by_doc=[]
    with httpx.Client(
        timeout=23,headers={"User-Agent":"PaperPro-layout-loss-diagnosis"}
    ) as client:
        for source_id in ids:
            pdf=_disjoint_public_blob(client,f"resume_list_pdf/{source_id}.pdf")
            native=_native_lines(pdf)
            raw_proposals=propose_pdf_workblocks(pdf)
            tick=time.perf_counter()
            layout=_native_model_layout(pdf)
            classified_lines=[
                line for index,page in enumerate(layout["pages"])
                for line in _validated_layout_lines(page,index)
            ]
            layout_regions=propose_workblocks_from_layout(layout)
            layout_regions_keep=propose_workblocks_from_layout(
                layout,unknown_heading_policy="keep"
            )
            runtime=round(time.perf_counter()-tick,3)

            # Query independent GT only AFTER all layout candidates exist.
            gt=json.loads(_disjoint_public_blob(
                client,f"result_gt/{source_id}.json"
            ))
            truth=_gt_work_items(gt)
            native_text=normalized(" ".join(x["source_line"] for x in native))
            model_text=normalized(
                " ".join(x["source_line"] for x in classified_lines)
            )
            stats=Counter()
            stats["source_id"]=source_id
            stats["GT_pairs"]=len(truth)
            stats["native_lines"]=len(native)
            stats["layout_lines"]=len(classified_lines)
            stats["layout_workblocks"]=len(layout_regions["workblocks"])
            stats["keep_unknown_workblocks"]=len(layout_regions_keep["workblocks"])
            stats["native_workblocks"]=len(raw_proposals["workblocks"])
            stats["recognized_work_headings_native"]=raw_proposals[
                "source_sections"
            ]["experience"]
            stats["recognized_work_headings_layout"]=layout_regions[
                "source_sections"
            ]["experience"]
            stats["layout_header_boxes"]=sum(
                b.get("boxclass") in ("section-header","title","chapter-header")
                for page in layout["pages"]
                for b in page.get("boxes",[])
            )
            stats["layout_processing_millis"]=round(runtime*1000)
            for pair in truth:
                native_has_both=(
                    pair["company"] in native_text and pair["role"] in native_text
                )
                model_has_both=(
                    pair["company"] in model_text and pair["role"] in model_text
                )
                native_block=any(
                    _gt_covered(block,pair)[2]
                    for block in raw_proposals["workblocks"]
                )
                mature_block=any(
                    _gt_covered(block,pair)[2]
                    for block in layout_regions["workblocks"]
                )
                keeping_block=any(
                    _gt_covered(block,pair)[2]
                    for block in layout_regions_keep["workblocks"]
                )
                stats["keep_unknown_region_pair"]+=keeping_block
                stats["keep_only_recovered_pairs"]+=keeping_block and not mature_block
                stats["native_source_pair_present"]+=native_has_both
                stats["layout_source_pair_present"]+=model_has_both
                stats["native_or_soft_layout_pair"]+=native_block or keeping_block
                stats["soft_layout_only_over_native"]+=(
                    keeping_block and not native_block
                )
                stats["native_only_over_soft_layout"]+=(
                    native_block and not keeping_block
                )
                stats["native_region_pair"]+=native_block
                stats["layout_region_pair"]+=mature_block
                if not model_has_both and native_has_both:
                    stats["loss_at_layout_text_stage"]+=1
                elif model_has_both and not mature_block:
                    stats["loss_at_layout_region_stage"]+=1
                elif mature_block:
                    stats["retained_by_layout_region"]+=1
                if native_block and not mature_block:
                    stats["native_only_pair"]+=1
                elif mature_block and not native_block:
                    stats["layout_only_pair"]+=1
            for candidate in layout_regions_keep["workblocks"]:
                if not any(_gt_covered(candidate,pair)[2] for pair in truth):
                    stats["keep_unknown_blocks_unsupported_by_GT"]+=1
            for candidate in layout_regions["workblocks"]:
                if not any(_gt_covered(candidate,pair)[2] for pair in truth):
                    stats["close_unknown_blocks_unsupported_by_GT"]+=1
            total.update({
                k:v for k,v in stats.items() if k!="source_id"
            })
            by_doc.append({
                k:stats[k] for k in (
                    "source_id","GT_pairs","native_source_pair_present",
                    "layout_source_pair_present","native_region_pair",
                    "layout_region_pair","keep_unknown_region_pair",
                    "keep_only_recovered_pairs","loss_at_layout_text_stage",
                    "loss_at_layout_region_stage",
                    "recognized_work_headings_native",
                    "recognized_work_headings_layout",
                )
            })
    expected=total["GT_pairs"]
    if expected!=32:
        raise ValueError("independent GT denominator changed")
    return {
        "experiment":"mature_layout_failure_attribution",
        "engine":"pymupdf4llm",
        "engine_version":"1.28.2",
        "source_commit":COMMIT,
        "development_ids":list(ids),
        "source_count":len(ids),
        "GT_pair_denominator":expected,
        "aggregate":dict(total),
        "breakdown":{
            "native_PDF_text_available":total["native_source_pair_present"],
            "mature_layout_text_available":total["layout_source_pair_present"],
            "mature_layout_region_contains_pair":total["layout_region_pair"],
            "native_PyMuPDF_region_contains_pair":total["native_region_pair"],
            "lost_text_during_mature_conversion":total["loss_at_layout_text_stage"],
            "model_text_intact_but_region_missed":total[
                "loss_at_layout_region_stage"
            ],
            "mature_only_recovered_pairs":total["layout_only_pair"],
            "model_unknown_heading_keep_pairs":total[
                "keep_unknown_region_pair"
            ],
            "soft_layout_and_native_pair_union":total[
                "native_or_soft_layout_pair"
            ],
            "mature_layout_unique_pair_beyond_native":total[
                "soft_layout_only_over_native"
            ],
            "native_unique_pair_beyond_mature_layout":total[
                "native_only_over_soft_layout"
            ],
            "extra_pairs_from_keeping_model_only_headings":total[
                "keep_only_recovered_pairs"
            ],
            "model_unknown_heading_close_workblocks":total["layout_workblocks"],
            "model_unknown_heading_keep_workblocks":total[
                "keep_unknown_workblocks"
            ],
            "keep_workblocks_without_GT_pair":total[
                "keep_unknown_blocks_unsupported_by_GT"
            ],
            "close_workblocks_without_GT_pair":total[
                "close_unknown_blocks_unsupported_by_GT"
            ],
        },
        "safe_per_file":by_doc,
        "GT_seen_only_after_proposals":True,
        "promotion_gate":{
            "pass":False,
            "product_integration_allowed":False,
            "reason":"Unknown model typography is not a reliable section boundary; exploratory recall improvement creates unsupported candidate work regions and requires independent confirmation.",
        },
        "candidate_fields_auto_filled":False,
        "model_training_performed":False,
        "production_modified":False,
        "holdout_read":False,
        "next_decision_note":"Typographic unknown headers explain many lost regions; no product promotion until field-level precision and fictitious employment are independently assessed.",
    }


if __name__=="__main__":
    output=run()
    print(json.dumps({
        key:value for key,value in output.items() if key!="safe_per_file"
    },ensure_ascii=True,indent=2))
