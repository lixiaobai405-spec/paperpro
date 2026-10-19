"""GT-blind native-PDF substring proposals: frozen, one-shot development gate.

Train positives from public synthetic PDFs 21–35. Dev=36–40.
Frozen new test 41–60 may be read ONLY after a predeclared development pass.
Legacy test IDs 1–10,101–105,201–205 must never train or tune this method.

Source character substrings stay in memory; CLI prints aggregates only.
This experiment never deploys, saves weights or emits hiring probabilities.
"""
from __future__ import annotations

from collections import Counter,defaultdict
from hashlib import sha256
import argparse
import json

import httpx

from app.diagnosis.span_supervision import align_gt_char_spans
from app.diagnosis.span_proposer import (
    fit_positive_span_proposer,propose_pdf_char_spans,
)
from app.diagnosis.native_candidate_lines import propose_pdf_field_lines
from app.diagnosis.annotation_alignment import _native_lines
from scripts.benchmark_annotation_alignment import _disjoint_public_blob
from scripts.benchmark_external_resume_corpus import IDS, COMMIT, normalized
from scripts.benchmark_native_candidate_lines import _expected

TRAIN_IDS=tuple(range(21,36))
DEV_IDS=tuple(range(36,41))
NEW_TEST_IDS=tuple(range(41,61))
BUDGET=8
FIELDS=("work_role","employer")
assert not set(TRAIN_IDS)&(set(DEV_IDS)|set(NEW_TEST_IDS)|set(IDS))
assert not set(DEV_IDS)&set(NEW_TEST_IDS)


def _train(client:httpx.Client) -> tuple[dict,dict,set[str]]:
    bundles=[]
    hashes=set()
    stats=Counter()
    for sample_id in TRAIN_IDS:
        raw=_disjoint_public_blob(client,f"resume_list_pdf/{sample_id}.pdf")
        digest=sha256(raw).hexdigest()
        if digest in hashes:
            raise ValueError("训练池出现重复的原始 PDF")
        hashes.add(digest)
        gt=json.loads(_disjoint_public_blob(
            client,f"result_gt/{sample_id}.json"
        ))
        a=align_gt_char_spans(raw,gt)
        stats["sources"]+=1
        stats["ambiguous"]+=sum(v["ambiguous"] for v in a["field_counts"].values())
        stats["overlapping_rejected"]+=a["overlapping_span_occurrences"]
        bundles.append({
            "source_id":sample_id,
            "positive_spans":a["positive_spans"],
            "unlabeled_character_negatives_created":0,
        })
    model=fit_positive_span_proposer(
        bundles,allowed_source_ids=TRAIN_IDS,
        forbidden_source_ids=tuple(IDS)+DEV_IDS+NEW_TEST_IDS
    )
    return model,{
        "pdfs":len(TRAIN_IDS),
        "positive_spans_by_field":model["positive_examples_by_field"],
        "ambiguous_label_occurrences":stats["ambiguous"],
        "overlap_rejected":stats["overlapping_rejected"],
        "threshold_from_train_only":model["threshold_from_train_only"],
    },hashes


def _metric(candidates:list[dict],gt:dict,*,is_span:bool) -> dict:
    truth=_expected(gt)
    result={}
    for field in FIELDS:
        selected=[v for v in candidates if v["field"]==field]
        # Source-line containment is directly comparable to the legacy
        # baseline; exact substring extraction is a stricter independent
        # metric and should not be disguised as a comparable accuracy.
        sources=[normalized(x["source_line"]) for x in selected]
        snippets=[
            normalized(x["proposed_text"] if is_span else x["source_line"])
            for x in selected
        ]
        expected=[normalized(x) for x in truth[field]]
        covered=sum(bool(label) and any(label in src for src in sources)
                    for label in expected)
        exact=sum(bool(label) and any(label==token for token in snippets)
                  for label in expected)
        result[field]={
            "expected":len(expected),
            "source_line_containment_hits":covered,
            "full_field_exact_hits":exact,
            "review_items":len(selected),
            "items_with_GT_text_support":sum(
                any(value and value in src for value in expected)
                for src in sources
            ),
        }
    return result


def evaluate(
    client:httpx.Client,model:dict,*,
    split:str,source_ids:tuple[int,...],
    forbidden_hashes:set[str]|None=None,
) -> dict:
    expected=DEV_IDS if split=="development" else NEW_TEST_IDS
    if source_ids!=expected:
        raise ValueError("禁止改动开发或冻结测试集编号")
    totals={m:defaultdict(Counter) for m in (
        "span_proposer","old_equal_budget","old_full"
    )}
    n=Counter()
    seen=set(forbidden_hashes or ())
    for source_id in source_ids:
        raw=_disjoint_public_blob(client,f"resume_list_pdf/{source_id}.pdf")
        digest=sha256(raw).hexdigest()
        if digest in seen:
            raise ValueError("开发/测试 PDF 与训练源内容重复")
        seen.add(digest)
        spans=propose_pdf_char_spans(raw,model,per_field=BUDGET)
        legacy=propose_pdf_field_lines(raw,max_candidates_per_field=40)
        budgeted=[
            candidate
            for field in FIELDS
            for candidate in [x for x in legacy if x["field"]==field][:BUDGET]
        ]
        if any(
            x["status"]!="unverified" or
            x["automatic_resume_mutation"] is not False or
            x["ranking_score_is_probability"] is not False
            for x in spans
        ):
            raise ValueError("未经核实片段不能作为职位事实或概率")
        # GT is fetched strictly AFTER BOTH methods have predicted.
        gt=json.loads(_disjoint_public_blob(
            client,f"result_gt/{source_id}.json"
        ))
        variants=(
            ("span_proposer",spans,True),
            ("old_equal_budget",budgeted,False),
            ("old_full",legacy,False),
        )
        for method,candidates,is_span in variants:
            metrics=_metric(candidates,gt,is_span=is_span)
            for field,item in metrics.items():
                totals[method][field].update(item)
        native=[normalized(x["source_line"]) for x in _native_lines(raw)]
        for field,strings in _expected(gt).items():
            if field not in FIELDS:
                continue
            n[field+"_expected"]+=len(strings)
            n[field+"_native_present"]+=sum(
                bool(normalized(value)) and any(
                    normalized(value) in source for source in native
                )
                for value in strings
            )
        n["processed_pdfs"]+=1
    values={}
    for method,fields in totals.items():
        values[method]={}
        for field in FIELDS:
            counters=dict(fields[field])
            denom=n[field+"_expected"]
            values[method][field]={
                **counters,
                "source_line_recall":round(
                    counters.get("source_line_containment_hits",0)/denom,4
                ) if denom else None,
                "exact_field_recall":round(
                    counters.get("full_field_exact_hits",0)/denom,4
                ) if denom else None,
            }
    return {
        "split":split,
        "pdf_count":n["processed_pdfs"],
        "fixed_GT_denominators":{
            field:n[field+"_expected"] for field in FIELDS
        },
        "native_text_upper_bounds":{
            field:n[field+"_native_present"] for field in FIELDS
        },
        "per_field_review_budget":BUDGET,
        "methods":values,
        "no_background_negatives":True,
        "scores_are_hiring_probabilities":False,
        "produced_any_job_record":False,
    }


def _gate(report:dict) -> dict:
    """The predeclared stop/go criterion BEFORE any new-test evaluation."""
    now=report["methods"]["span_proposer"]
    old=report["methods"]["old_equal_budget"]
    volume=report["methods"]["old_full"]
    # Demand that exact *extracted* field hits at least equal the old
    # source-line coverage hits, and keep human-review burden controlled.
    deficits={
        f:now[f]["full_field_exact_hits"]-
          old[f]["source_line_containment_hits"]
        for f in FIELDS
    }
    review=sum(now[f]["review_items"] for f in FIELDS)
    baseline_review=sum(volume[f]["review_items"] for f in FIELDS)
    accepted=(all(x>=0 for x in deficits.values())
              and review<=1.5*max(1,baseline_review))
    return {
        "pass":accepted,
        "exact_span_vs_old_line_coverage_deltas":deficits,
        "span_review_items":review,
        "legacy_full_review_items":baseline_review,
        "frozen_test_access_allowed":accepted,
        "stated_before_holdout":"both exact span recalls >= old top-k line containment; review <=1.5x old full count",
    }


def run(*,split:str) -> dict:
    if split not in ("development","new_unseen_test"):
        raise ValueError("仅允许预定义的数据集划分")
    with httpx.Client(
        timeout=20,headers={"User-Agent":"PaperPro-independent-span-proposer"}
    ) as client:
        model,training,hashes=_train(client)
        dev=evaluate(client,model,split="development",
                     source_ids=DEV_IDS,forbidden_hashes=hashes)
        gate=_gate(dev)
        if split=="new_unseen_test" and not gate["pass"]:
            return {
                "experiment":"positive_only_pdf_char_span_proposals",
                "training":training,"development":dev,
                "development_gate":gate,
                "new_test_read":False,
                "new_holdout":None,
                "model_saved":False,
                "deployed":False,
            }
        heldout=None
        if split=="new_unseen_test":
            heldout=evaluate(client,model,split="new_unseen_test",
                            source_ids=NEW_TEST_IDS,forbidden_hashes=hashes)
    return {
        "experiment":"positive_only_pdf_char_span_proposals",
        "source_commit":COMMIT,
        "training":training,
        "development":dev,
        "development_gate":gate,
        "new_test_read":heldout is not None,
        "new_holdout":heldout,
        "model_saved":False,
        "deployed":False,
        "user_file_edited":False,
        "external_api_models_used":False,
        "comparison_boundary":"Exact role/company substrings versus baseline source-line containment; not end-to-end resume correctness.",
    }


if __name__=="__main__":
    p=argparse.ArgumentParser(
        description="Offline GT-independent company/role character span proposer."
    )
    p.add_argument("--split",choices=("development","new_unseen_test"),
                   required=True)
    arguments=p.parse_args()
    print(json.dumps(run(split=arguments.split),
                     ensure_ascii=True,indent=2))
