"""Private-free counts of independently labeled PDF company-role pair candidates.

Uses pinned Apache-2.0 synthetic PDFs in memory. Challenge IDs never train.
Rows are numeric geometry plus public synthetic ID; no personal text emitted.
The module only validates whether a supervised data interface is feasible;
it does not train or tune a classifier.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json

import httpx

from app.diagnosis.annotation_alignment import align_independent_annotations
from app.diagnosis.relation_pairs import build_relation_pairs
from scripts.benchmark_annotation_alignment import (
    TRAIN_POOL_IDS, _disjoint_public_blob
)
from scripts.benchmark_external_resume_corpus import IDS, _fetch, COMMIT


def collect_pairs(
    *, split: str, source_ids: tuple[int,...] | None = None
) -> tuple[list[dict],dict]:
    if split not in {"train_candidate","holdout_evaluation"}:
        raise ValueError("Unknown dataset split")
    allowed=TRAIN_POOL_IDS if split=="train_candidate" else IDS
    ids=allowed if source_ids is None else source_ids
    if not set(ids).issubset(set(allowed)):
        raise ValueError("候选训练池与固定保留测试集不得交叉")
    training=split=="train_candidate"
    get_blob=_disjoint_public_blob if training else _fetch
    examples=[]
    by_file=[]
    with httpx.Client(timeout=20,headers={
        "User-Agent":"PaperPro-independent-pair-feasibility"
    }) as http:
        for source_id in ids:
            content=get_blob(http,f"resume_list_pdf/{source_id}.pdf")
            annotations=json.loads(
                get_blob(http,f"result_gt/{source_id}.json")
            )
            unique=align_independent_annotations(content,annotations)
            pairs=build_relation_pairs(
                unique,annotations,source_id=source_id,
                holdout_ids=IDS,training=training,
            )
            examples.extend(pairs)
            by_file.append({
                "synthetic_id":source_id,
                "labeled_pairs":len(pairs),
                "positive":sum(item["label"]==1 for item in pairs),
                "cross_record_negative":sum(item["label"]==0 for item in pairs),
            })
    counts=Counter(item["label"] for item in examples)
    return examples,{
        "source":"pinned_public_synthetic_resumes_independent_gt",
        "commit":COMMIT,
        "split":split,
        "pdf_count":len(ids),
        "usable_pairs":len(examples),
        "positive_pairs":counts[1],
        "cross_record_negative_pairs":counts[0],
        "files_with_paired_signal":sum(bool(r["positive"]) for r in by_file),
        "files_with_hard_negatives":sum(bool(r["cross_record_negative"]) for r in by_file),
        "training_or_scoring_performed":False,
        "per_file_without_private_text":by_file,
    }


def main() -> None:
    parser=argparse.ArgumentParser(
        description="Check independent-GT company/role pair supervision readiness."
    )
    parser.add_argument("--split",choices=["train_candidate","holdout_evaluation"],
                        required=True)
    args=parser.parse_args()
    _,stats=collect_pairs(split=args.split)
    print(json.dumps({key:value for key,value in stats.items()
                      if key!="per_file_without_private_text"},ensure_ascii=True,indent=2))


if __name__=="__main__":
    main()
