"""CPU native-PDF line-recognition experiment with predeclared source splits.

TRAIN: 21–35 (independent GT positive anchors only)
DEV:   36–40 (model-selection sanity check; NEVER fit)
FRESH: 41–60 (new, sealed test; evaluate once AFTER fixed candidate recipe)
LEGACY fixed challenge: 1–10,101–105,201–205 (NEVER train/tune)

There are no external LLM/API calls: the only retrieval is reading the pinned,
public Apache-2.0 synthetic PDFs from the OS-temp Git object cache. No data,
model weights or source texts are saved or printed. Inference takes PDF ONLY,
then annotations are fetched *after* predictions for evaluation.

"GT-supported" is a proxy for review relevance, not verified precision;
an unannotated line could still contain a valid field.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import argparse
import json

import httpx

from app.diagnosis.annotation_alignment import _native_lines
from app.diagnosis.line_field_classifier import (
    build_verified_line_labels, fit_line_field_model, propose_line_fields,
)
from app.diagnosis.native_candidate_lines import propose_pdf_field_lines
from scripts.benchmark_annotation_alignment import _disjoint_public_blob, _http_public_blob
from scripts.benchmark_external_resume_corpus import IDS, COMMIT, normalized
from scripts.benchmark_native_candidate_lines import _expected, _score_candidates

TRAIN_IDS = tuple(range(21,36))
EXTRA_TRAIN_IDS = tuple(range(61,81))
EXPANDED_TRAIN_IDS = TRAIN_IDS + EXTRA_TRAIN_IDS
DEV_IDS = tuple(range(36,41))
NEW_TEST_IDS = tuple(range(41,61))
CANDIDATES_PER_FIELD = 8
ALLOWED_IDS = set(EXPANDED_TRAIN_IDS) | set(DEV_IDS) | set(NEW_TEST_IDS)
assert (not set(EXPANDED_TRAIN_IDS)&set(DEV_IDS)
        and not set(EXPANDED_TRAIN_IDS)&set(NEW_TEST_IDS)
        and not set(DEV_IDS)&set(NEW_TEST_IDS)
        and not ALLOWED_IDS&set(IDS))


def _load(client: httpx.Client, sample_id: int) -> tuple[bytes,dict]:
    if sample_id not in ALLOWED_IDS:
        raise ValueError("样本不是已固定的开发/新测试集成员")
    # Existing 21–35 are cached in the pinned Git object store. Extra
    # 61–80 are read through the public pinned GitHub Contents API when
    # github.com Git smart-HTTP is temporarily unreachable. Do not fallback
    # to a different commit or copy fixture blobs into the project tree.
    reader=(
        _http_public_blob if sample_id in EXTRA_TRAIN_IDS
        else _disjoint_public_blob
    )
    file_bytes=reader(client,f"resume_list_pdf/{sample_id}.pdf")
    gt=json.loads(reader(
        client,f"result_gt/{sample_id}.json"
    ))
    return file_bytes,gt


def fit_frozen_training_pool(
    client: httpx.Client, *, training_ids: tuple[int,...] = TRAIN_IDS
) -> tuple[dict,dict]:
    if training_ids not in (TRAIN_IDS,EXPANDED_TRAIN_IDS):
        raise ValueError("训练来源必须使用预先固定的小/扩展划分")
    bundles=[]
    hashes=set()
    for sample_id in training_ids:
        pdf,gt=_load(client,sample_id)
        h=sha256(pdf).hexdigest()
        if h in hashes:
            raise ValueError("训练来源重复 PDF 内容")
        hashes.add(h)
        bundles.append(build_verified_line_labels(
            pdf,gt,source_id=sample_id,
            forbidden_ids=tuple(IDS)+DEV_IDS+NEW_TEST_IDS,
        ))
    model=fit_line_field_model(bundles,allowed_train_ids=training_ids)
    stats={
        "pdfs":len(training_ids),
        "positive_anchors_by_type":{
            field:sum(b["class_counts"][field] for b in bundles)
            for field in ("work_role","employer","school")
        },
        "ambiguous_anchor_occurrences":sum(
            b["ambiguous_gt_line_count"] for b in bundles
        ),
        "unannotated_lines_not_used_as_negatives":True,
        "training_source_hashes_disjoint_from":list(
            ["development_validation","new_unseen_test",
             "legacy_fixed_challenge"]
        ),
        "model_saved":False,
    }
    return model,stats


def _metric_for_view(proposals: list[dict],gt: dict) -> dict:
    measured=_score_candidates(proposals,gt)
    return {
        field:{
            "GT_hits":measured[field]["gt_items_with_candidate_line"],
            "candidate_lines":measured[field]["candidate_lines"],
            "candidate_lines_with_GT_support":
                measured[field]["candidate_lines_with_gt_text_support"],
            "unverified_candidate_lines":
                measured[field]["candidate_lines_not_verified_by_gt"],
        } for field in ("work_role","employer")
    }


def evaluate_split(
    client: httpx.Client,model: dict, *,
    name: str, ids: tuple[int,...], per_field: int = CANDIDATES_PER_FIELD,
    forbidden_pdf_hashes: set[str] | None = None,
) -> dict:
    valid=DEV_IDS if name=="development_validation" else NEW_TEST_IDS
    if ids != valid:
        raise ValueError("已冻结的评估池编号不能被替换或重分组")
    agg={
        comparator:defaultdict(Counter)
        for comparator in ("learned_topk","legacy_equal_budget","legacy_full")
    }
    counts=Counter()
    seen_hashes=set(forbidden_pdf_hashes or ())
    for sample_id in ids:
        # GT-blind prediction BEFORE fetching GT, including both comparators.
        pdf=_disjoint_public_blob(client,f"resume_list_pdf/{sample_id}.pdf")
        h=sha256(pdf).hexdigest()
        if h in seen_hashes:
            raise ValueError("训练/测试 PDF 内容重复或同组重复")
        seen_hashes.add(h)
        learned=propose_line_fields(pdf,model,per_field=per_field)
        static=propose_pdf_field_lines(pdf,max_candidates_per_field=40)
        budgeted=[
            x for field in ("work_role","employer")
            for x in [p for p in static if p["field"]==field][:per_field]
        ]
        gt=json.loads(_disjoint_public_blob(
            client,f"result_gt/{sample_id}.json"
        ))
        for method,proposals in (
            ("learned_topk",learned),("legacy_equal_budget",budgeted),
            ("legacy_full",static),
        ):
            m=_metric_for_view(proposals,gt)
            for field,item in m.items():
                agg[method][field].update(item)
        lines=[normalized(x["source_line"]) for x in _native_lines(pdf)]
        for field,truths in _expected(gt).items():
            if field not in ("work_role","employer"):
                continue
            counts[field+"_GT"]+=len(truths)
            counts[field+"_native_visible"]+=sum(
                bool(normalized(t)) and any(
                    normalized(t) in text for text in lines
                ) for t in truths
            )
        counts["sample_count"]+=1
    results={}
    for method,items in agg.items():
        results[method]={}
        for field,item in items.items():
            denominator=counts[field+"_GT"]
            results[method][field]={
                **{k:int(v) for k,v in item.items()},
                "GT_text_coverage":round(
                    item["GT_hits"]/denominator,4
                ) if denominator else None,
                "GT_coverage_given_native_text":round(
                    item["GT_hits"]/counts[field+"_native_visible"],4
                ) if counts[field+"_native_visible"] else None,
            }
    return {
        "split":name,
        "pdf_count":counts["sample_count"],
        "source_ids":list(ids),
        "GT_expected":{
            field:counts[field+"_GT"] for field in ("work_role","employer")
        },
        "GT_native_text_visible":{
            field:counts[field+"_native_visible"]
            for field in ("work_role","employer")
        },
        "per_field_review_budget":per_field,
        "methods":results,
        "labels_used_only_after_prediction":True,
        "candidate_precision_claimed":False,
        "unknown_lines_as_negative_count":0,
        "deployed":False,
    }


def _development_gate(evaluation: dict) -> dict:
    """Gate declared BEFORE any fresh-test results are requested.

    To spend the new 41–60 test pool, both recall dimensions must beat or
    equal the old rules at an identical per-field review budget, and total
    review burden must not exceed the old full candidate list by >50%.
    """
    methods=evaluation["methods"]
    learned=methods["learned_topk"]
    legacy=methods["legacy_equal_budget"]
    counts=methods["legacy_full"]
    gains={
        key: learned[key]["GT_hits"]-legacy[key]["GT_hits"]
        for key in ("work_role","employer")
    }
    burden=sum(learned[k]["candidate_lines"] for k in gains)
    prior_burden=sum(counts[k]["candidate_lines"] for k in gains)
    accepted=(all(x>=0 for x in gains.values())
              and burden <= max(1,prior_burden)*1.5)
    return {
        "pass":accepted,
        "GT_coverage_deltas":gains,
        "learned_review_lines":burden,
        "legacy_full_review_lines":prior_burden,
        "frozen_new_test_allowed":accepted,
        "definition":"no worse recall for role/employer at equal per-field budget, review lines <=1.5x legacy",
    }


def run(*, target_split: str, training: str = "small") -> dict:
    if target_split not in {"development_validation","new_unseen_test"}:
        raise ValueError("Unknown evaluation stage")
    if training not in {"small","expanded"}:
        raise ValueError("Unknown training size")
    training_ids=TRAIN_IDS if training=="small" else EXPANDED_TRAIN_IDS
    with httpx.Client(
        timeout=20,
        headers={"User-Agent":"PaperPro-GT-independent-line-classifier"}
    ) as client:
        model,train_stats=fit_frozen_training_pool(client,training_ids=training_ids)
        # Never read fresh holdout GT while an inferior candidate is being
        # debugged against development labels.
        development=evaluate_split(
            client,model,name="development_validation",ids=DEV_IDS
        )
        gate=_development_gate(development)
        if target_split=="new_unseen_test" and not gate["pass"]:
            return {
                "experiment":"independent_gt_positive_only_native_line_classification",
                "training_group":training,
                "training":train_stats,
                "development":development,
                "predeclared_gate":gate,
                "fresh_test_read":False,
                "deployed":False,
            }
        evaluation=development if target_split=="development_validation" else evaluate_split(
            client,model,name="new_unseen_test",ids=NEW_TEST_IDS
        )
    return {
        "experiment":"independent_gt_positive_only_native_line_classification",
        "source_commit":COMMIT,
        "training_group":training,
        "training":train_stats,
        "development_gate":gate,
        "model_recipe":model["hyperparameters"],
        "classification_labels":model["class_names"],
        "evaluation":evaluation,
        "model_fitted_cpu_only":True,
        "model_saved":False,
        "model_deployed":False,
        "training_background_negative_labels":0,
        "hiring_outcome_predictive_validity":False,
        "note":"Source-line proposal coverage only. No candidate is a confirmed job or employer; unknown lines cannot be called false positives.",
    }


def main():
    parser=argparse.ArgumentParser(
        description="CPU native PDF text-line field recognition with frozen splits."
    )
    parser.add_argument("--split",required=True,
                        choices=["development_validation","new_unseen_test"])
    parser.add_argument("--training",default="small",
                        choices=["small","expanded"])
    args=parser.parse_args()
    print(json.dumps(run(target_split=args.split,training=args.training),
                     ensure_ascii=True,indent=2))


if __name__=="__main__":
    main()
