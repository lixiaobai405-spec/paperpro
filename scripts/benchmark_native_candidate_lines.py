"""GT-blind candidate-line recall and review-load benchmark for PDF extraction.

Candidates are generated from PDF bytes *before* the third-party GT JSON is
examined. GT is used for evaluation only. An unannotated candidate is
'unsupported by this GT', NOT necessarily a false positive, because labels
may be incomplete or contain cross-page relations.

Fixed training-development IDs 21–40 and frozen challenge IDs are disjoint.
No model fitting, personal data output or product changes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import json

import httpx

from app.diagnosis.native_candidate_lines import propose_pdf_field_lines
from app.diagnosis.annotation_alignment import _native_lines
from scripts.benchmark_annotation_alignment import (
    TRAIN_POOL_IDS, _disjoint_public_blob
)
from scripts.benchmark_external_resume_corpus import (
    IDS, COMMIT, _fetch, normalized
)


FIELDS=("work_role","employer")


def _expected(annotation: dict) -> dict[str,list[str]]:
    work=annotation.get("workExperience") or []
    return {
        "work_role":[x["position"].strip() for x in work if isinstance(x,dict)
                     and isinstance(x.get("position"),str) and x["position"].strip()],
        "employer":[x["companyName"].strip() for x in work if isinstance(x,dict)
                    and isinstance(x.get("companyName"),str) and x["companyName"].strip()],
    }


def _score_candidates(candidates: list[dict], annotation: dict) -> dict:
    expected=_expected(annotation)
    field_results={}
    for field in FIELDS:
        lines=[normalized(x["source_line"]) for x in candidates
               if x["field"]==field]
        gt=[normalized(x) for x in expected[field]]
        covered=sum(bool(term) and any(term in text for text in lines) for term in gt)
        supported=sum(any(term and term in text for term in gt) for text in lines)
        field_results[field]={
            "expected":len(gt),
            "gt_items_with_candidate_line":covered,
            "candidate_lines":len(lines),
            "candidate_lines_with_gt_text_support":supported,
            "candidate_lines_not_verified_by_gt":len(lines)-supported,
        }
    return field_results


def run(*, split: str, ids: tuple[int,...] | None = None) -> dict:
    if split not in {"train_candidate_feasibility","holdout_evaluation"}:
        raise ValueError("未知的测试划分")
    allowed=TRAIN_POOL_IDS if split=="train_candidate_feasibility" else IDS
    sample_ids=allowed if ids is None else ids
    if not sample_ids or not set(sample_ids).issubset(set(allowed)):
        raise ValueError("无法读取测试之外的简历或混入另一个分组")
    loader=(
        _disjoint_public_blob if split=="train_candidate_feasibility"
        else _fetch
    )
    totals=defaultdict(Counter)
    file_summaries=[]
    with httpx.Client(timeout=23,headers={
        "User-Agent":"PaperPro-GT-blind-candidate-benchmark"
    }) as client:
        for source_id in sample_ids:
            # Extractor receives ONLY these PDF bytes. Independent labels
            # are loaded afterwards, and never passed to proposer.
            pdf=loader(client,f"resume_list_pdf/{source_id}.pdf")
            candidates=propose_pdf_field_lines(pdf)
            annotation=json.loads(loader(client,f"result_gt/{source_id}.json"))
            metrics=_score_candidates(candidates,annotation)
            # Independent evaluation only, after the GT-blind proposal.
            # Separate extraction failures from candidate selection failures.
            native_lines=[normalized(x["source_line"])
                          for x in _native_lines(pdf)]
            expected=_expected(annotation)
            for field in FIELDS:
                native_available=sum(
                    bool(normalized(term)) and any(
                        normalized(term) in line for line in native_lines
                    ) for term in expected[field]
                )
                metrics[field]["gt_items_present_in_native_text"]=native_available
            if any(x["status"]!="unverified" or
                   x["automatic_resume_mutation"] is not False for x in candidates):
                raise ValueError("实验候选违反人工确认安全边界")
            for field in FIELDS:
                totals[field].update(metrics[field])
            file_summaries.append({
                "synthetic_id":source_id,
                "role_candidate_lines":metrics["work_role"]["candidate_lines"],
                "company_candidate_lines":metrics["employer"]["candidate_lines"],
                "role_gt_items_covered":metrics["work_role"]["gt_items_with_candidate_line"],
                "company_gt_items_covered":metrics["employer"]["gt_items_with_candidate_line"],
            })
    summaries={}
    for field in FIELDS:
        total=totals[field]
        summaries[field]={
            **{k:int(v) for k,v in total.items()},
            "gt_text_coverage":(
                round(total["gt_items_with_candidate_line"]/total["expected"],4)
                if total["expected"] else None
            ),
            "native_text_upper_bound":(
                round(total["gt_items_present_in_native_text"]/total["expected"],4)
                if total["expected"] else None
            ),
            "candidate_coverage_given_native_text":(
                round(total["gt_items_with_candidate_line"]/
                      total["gt_items_present_in_native_text"],4)
                if total["gt_items_present_in_native_text"] else None
            ),
            "gt_support_among_proposed_lines":(
                round(total["candidate_lines_with_gt_text_support"]/total["candidate_lines"],4)
                if total["candidate_lines"] else None
            ),
        }
    return {
        "type":"GT_blind_native_PDF_line_proposals",
        "split":split,"source_commit":COMMIT,
        "pdf_count":len(sample_ids),
        "source_ids":list(sample_ids),
        "fields":summaries,
        "files":file_summaries,
        "product_code_modified":False,
        "candidate_auto_adopted":False,
        "candidate_precision_validated":False,
        "true_negative_labels_inferred":0,
        "real_applicant_accuracy_validated":False,
        "metric_boundary":"GT text inclusion in proposed PDF source lines, not extraction of exact field values or correctness of a work record.",
    }


def main():
    parser=argparse.ArgumentParser(description="GT-blind PDF field-line feasibility.")
    parser.add_argument("--split",required=True,choices=[
        "train_candidate_feasibility","holdout_evaluation"
    ])
    args=parser.parse_args()
    stats=run(split=args.split)
    print(json.dumps({
        k:v for k,v in stats.items() if k!="files"
    },ensure_ascii=True,indent=2))


if __name__=="__main__":
    main()
