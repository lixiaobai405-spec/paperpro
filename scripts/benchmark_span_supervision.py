"""Compare exclusive-line vs multi-field character-span supervision on TRAIN only.

Uses source IDs 21–35 from the pinned public synthetic Git object cache.
No new frozen-test labels are read and no training is performed.
All PDF text and labels remain in memory. Output is aggregate counts only,
never names, phone numbers, employer names, role strings or raw PDF content.
"""
from __future__ import annotations

from collections import Counter
import json

import httpx

from app.diagnosis.annotation_alignment import FIELD_NAMES
from app.diagnosis.line_field_classifier import build_verified_line_labels
from app.diagnosis.span_supervision import align_gt_char_spans
from scripts.benchmark_annotation_alignment import _disjoint_public_blob
from scripts.benchmark_external_resume_corpus import IDS, COMMIT
from scripts.experiment_line_field_classifier import TRAIN_IDS, DEV_IDS, NEW_TEST_IDS


def run() -> dict:
    assert not(set(TRAIN_IDS)&(set(IDS)|set(DEV_IDS)|set(NEW_TEST_IDS)))
    old=Counter()
    source_counts=Counter()
    multi=Counter()
    seen_ids=[]
    with httpx.Client(
        timeout=18,headers={"User-Agent":"PaperPro-span-label-feasibility"}
    ) as client:
        for id_ in TRAIN_IDS:
            blob=_disjoint_public_blob(client,f"resume_list_pdf/{id_}.pdf")
            gt=json.loads(_disjoint_public_blob(
                client,f"result_gt/{id_}.json"
            ))
            old_labels=build_verified_line_labels(
                blob,gt,source_id=id_,
                forbidden_ids=tuple(IDS)+DEV_IDS+NEW_TEST_IDS,
            )
            spans=align_gt_char_spans(blob,gt)
            for field in FIELD_NAMES:
                old[field]+=old_labels["class_counts"][field]
                source_counts[(field,"expected")]+=spans["field_counts"][field]["expected"]
                source_counts[(field,"found")]+=spans["field_counts"][field]["found"]
                source_counts[(field,"ambiguous")]+=spans["field_counts"][field]["ambiguous"]
                source_counts[(field,"missing")]+=spans["field_counts"][field]["missing"]
                source_counts[(field,"overlapping_rejected")]+=spans["field_counts"][field]["overlapping_rejected"]
            multi["shared_positive_spans"]+=spans["shared_native_line_positive_spans"]
            multi["ambiguous_line_gt_labels"]+=old_labels["ambiguous_gt_line_count"]
            multi["overlapping_spans_rejected"]+=spans["overlapping_span_occurrences"]
            seen_ids.append(id_)
    output={}
    for field in FIELD_NAMES:
        output[field]={
            "expected":source_counts[(field,"expected")],
            "eligible_as_whole_line_class":old[field],
            "unambiguous_char_spans":source_counts[(field,"found")],
            "extra_positive_anchors":source_counts[(field,"found")]-old[field],
            "ambiguous_char_occurrences":source_counts[(field,"ambiguous")],
            "missing_char_occurrences":source_counts[(field,"missing")],
            "overlap_rejected":source_counts[(field,"overlapping_rejected")],
        }
    return {
        "experiment":"positive_only_GT_char_span_alignment",
        "source_commit":COMMIT,
        "dataset":"public_synthetic_training_pool_only",
        "training_source_ids":seen_ids,
        "source_count":len(seen_ids),
        "by_field":output,
        "shared_line_source_statistics":dict(multi),
        "unannotated_negative_labels_created":0,
        "actual_training_performed":False,
        "fresh_holdout_read":False,
        "deployed":False,
        "real_applicant_validation":False,
        "note":"Alignment candidates still need work-entry semantic validation before downstream use.",
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True,indent=2))
