"""GT-blind WorkBlock region benchmark against *independent* synthetic GT.

The PDF geometry engine runs BEFORE the GT is loaded. All fields and source
text remain in memory. Only source IDs and aggregate counts are printed;
unmatched work entries are NOT labeled false employment claims.

SOURCE SPLIT: training-development only (21–35). Do not use this command to
access the frozen 41–60 cohort or the older 20 PDF fixed challenge set.
The candidate product API/score is not modified by this experiment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json

import httpx

from app.diagnosis.adapter import _normalized_month, convert_resume
from app.parser import extract_file, parse_resume
from app.diagnosis.workblock_regions import propose_pdf_workblocks
from app.diagnosis.annotation_alignment import _native_lines
from scripts.benchmark_annotation_alignment import _disjoint_public_blob
from scripts.benchmark_external_resume_corpus import COMMIT, IDS, normalized

TRAIN_IDS=tuple(range(21,36))
DEV_IDS=tuple(range(36,41))
UNSEEN_IDS=tuple(range(41,61))
assert set(TRAIN_IDS).isdisjoint(set(DEV_IDS)|set(UNSEEN_IDS)|set(IDS))


def _gt_work_items(gt: dict) -> list[dict]:
    entries=[]
    for record in gt.get("workExperience") or []:
        if not isinstance(record,dict):
            continue
        company=record.get("companyName")
        role=record.get("position")
        dates=record.get("employmentPeriod") or {}
        if not isinstance(company,str) or not company.strip():
            continue
        if not isinstance(role,str) or not role.strip():
            continue
        entries.append({
            "company":normalized(company),
            "role":normalized(role),
            "start":str(dates.get("startDate") or ""),
            "end":str(dates.get("endDate") or ""),
        })
    return entries


def _gt_covered(block: dict, work_item: dict) -> tuple[bool,bool,bool,bool]:
    text=normalized(block["source_text"])
    company=bool(work_item["company"] in text)
    role=bool(work_item["role"] in text)
    pair=company and role
    start=work_item["start"]
    end=work_item["end"]
    expected_start=_normalized_month(start) if start else ""
    expected_end=_normalized_month(end) if end else ""
    dates=block["dates"]
    correct_dates=(
        bool(expected_start and expected_end)
        and normalized(expected_start)==normalized(dates["start"])
        and normalized(expected_end)==normalized(dates["end"])
    )
    return company,role,pair,pair and correct_dates


def _legacy_covered(entry, expected: dict) -> tuple[bool,bool,bool]:
    """Compare existing structured work entry, without mutating production."""
    heading_text=normalized(
        " ".join([entry.heading,*entry.bullets])
    )
    source_pair=(
        expected["company"] in heading_text
        and expected["role"] in heading_text
    )
    structured_pair=(
        expected["company"] in normalized(entry.company)
        and expected["role"] in normalized(entry.role)
    )
    start=_normalized_month(expected["start"]) if expected["start"] else ""
    end=_normalized_month(expected["end"]) if expected["end"] else ""
    correct_dates=(
        bool(start and end)
        and normalized(entry.start_date)==normalized(start)
        and normalized(entry.end_date)==normalized(end)
    )
    return source_pair,structured_pair,structured_pair and correct_dates


def run(ids:tuple[int,...]=TRAIN_IDS) -> dict:
    if ids != TRAIN_IDS:
        raise ValueError("禁止改变 WorkBlock 训练开发池或读取保留测试集")
    tally=Counter()
    file_rows=[]
    with httpx.Client(timeout=21,headers={
        "User-Agent":"PaperPro-workblock-region-development"
    }) as http:
        for doc_id in ids:
            pdf=_disjoint_public_blob(http,f"resume_list_pdf/{doc_id}.pdf")
            proposed=propose_pdf_workblocks(pdf)
            assert proposed["automatic_resume_mutation"] is False
            assert all(b["status"]=="unverified" and not b["auto_promote"]
                       for b in proposed["workblocks"])
            lines=_native_lines(pdf)
            old_text,_,_=extract_file("source.pdf",pdf)
            legacy=convert_resume(
                parse_resume(old_text),raw_text="",fingerprint=""
            )
            # Independent GT is fetched after both extractors have run.
            gt=json.loads(_disjoint_public_blob(
                http,f"result_gt/{doc_id}.json"
            ))
            truth=_gt_work_items(gt)
            text=normalized(" ".join(line["source_line"] for line in lines))
            per_file=Counter()
            per_file["synthetic_id"]=doc_id
            per_file["expected_pairs"]=len(truth)
            per_file["candidate_blocks"]=len(proposed["workblocks"])
            per_file["legacy_experience_entries"]=len(legacy.experience)
            per_file["experience_sections"]=proposed["source_sections"]["experience"]
            per_file["parallel_pages"]=sum(
                page["parallel_section_lanes"] for page in proposed["layout_pages"]
            )
            for entry in truth:
                per_file["source_company_present"]+=bool(entry["company"] in text)
                per_file["source_role_present"]+=bool(entry["role"] in text)
                matches=[
                    _gt_covered(block,entry)
                    for block in proposed["workblocks"]
                ]
                per_file["gt_company_in_block"]+=any(m[0] for m in matches)
                per_file["gt_role_in_block"]+=any(m[1] for m in matches)
                per_file["gt_pair_in_same_block"]+=any(m[2] for m in matches)
                per_file["gt_pair_and_period_in_same_block"]+=any(m[3] for m in matches)
                old_matches=[
                    _legacy_covered(old_entry,entry)
                    for old_entry in legacy.experience
                ]
                per_file["legacy_source_pair_in_same_entry"]+=any(
                    m[0] for m in old_matches
                )
                per_file["legacy_structured_pair_in_same_entry"]+=any(
                    m[1] for m in old_matches
                )
                per_file["legacy_structured_pair_and_dates"]+=any(
                    m[2] for m in old_matches
                )
                new_has_pair=any(m[2] for m in matches)
                old_has_pair=any(m[0] for m in old_matches)
                if new_has_pair and not old_has_pair:
                    per_file["workblock_only_pair"]+=1
                elif old_has_pair and not new_has_pair:
                    per_file["legacy_only_pair"]+=1
                elif new_has_pair and old_has_pair:
                    per_file["both_region_pair"]+=1
                else:
                    per_file["neither_region_pair"]+=1
            for block in proposed["workblocks"]:
                if not any(_gt_covered(block,entry)[2] for entry in truth):
                    per_file["candidate_blocks_without_GT_pair"]+=1
            tally.update({
                k:v for k,v in per_file.items() if k!="synthetic_id"
            })
            file_rows.append(dict(per_file))
    n=tally["expected_pairs"]
    return {
        "source":"Apache-2.0 synthetic independent-GT work relations",
        "source_commit":COMMIT,
        "split":"training_development_only",
        "source_ids":list(ids),
        "pdf_count":len(ids),
        "aggregate":dict(tally),
        "joint_pair_coverage":round(tally["gt_pair_in_same_block"]/n,4) if n else None,
        "legacy_raw_entry_pair_coverage":round(
            tally["legacy_source_pair_in_same_entry"]/n,4
        ) if n else None,
        "legacy_structured_pair_coverage":round(
            tally["legacy_structured_pair_in_same_entry"]/n,4
        ) if n else None,
        "dual_source_raw_pair_union_count":(
            tally["both_region_pair"]+tally["workblock_only_pair"]
            +tally["legacy_only_pair"]
        ),
        "dual_source_raw_pair_union_coverage":round((
            tally["both_region_pair"]+tally["workblock_only_pair"]
            +tally["legacy_only_pair"]
        )/n,4) if n else None,
        "dual_source_auto_merge_performed":False,
        "promotion_gate":{
            "pass":False,
            "reason":"新区域同源共现 17/32，低于旧 Entry 19/32；存在未核实候选，尚无独立未见集的字段与雇佣事实验收",
            "production_integration_allowed":False,
            "frozen_holdout_access_allowed":False,
        },
        "joint_pair_date_coverage":round(
            tally["gt_pair_and_period_in_same_block"]/n,4
        ) if n else None,
        "per_file_privacy_safe":file_rows,
        "false_positive_classification_performed":False,
        "unmatched_blocks_are_unverified_not_false_positive":True,
        "independent_GT_loaded_after_proposals":True,
        "candidate_resume_mutated":False,
        "deployed":False,
        "model_training_performed":False,
        "heldout_41_60_read":False,
        "legacy_20_PDF_holdout_read":False,
        "metric_boundary":"GT substrings share one proposed source region; NOT verified parsed company/role values, job existence, or end-to-end resume recall.",
    }


if __name__=="__main__":
    measured=run()
    print(json.dumps({
        key:value for key,value in measured.items()
        if key!="per_file_privacy_safe"
    },ensure_ascii=True,indent=2))
