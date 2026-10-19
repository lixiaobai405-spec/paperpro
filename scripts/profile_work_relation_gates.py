"""Pinned external synthetic-PDF work-relation hint audit.

Only synthetic source IDs and aggregate verdicts are printed. A geometric hint
is never automatically added to the scored résumé, even if it happens to agree
with a GT field. This audit needs the optional external Git object cache.
"""
from __future__ import annotations

import json
from collections import Counter
import httpx

from app.parser import extract_file, parse_resume
from app.diagnosis.adapter import convert_resume
from app.diagnosis.work_relation import propose_existing_work_relations
from scripts.benchmark_external_resume_corpus import IDS,_fetch,normalized


def run(ids=IDS):
    summary=Counter()
    safe_cases=[]
    with httpx.Client(timeout=18,headers={"User-Agent":"PaperPro-work-hint-audit"}) as client:
        for number in ids:
            blob=_fetch(client,f"resume_list_pdf/{number}.pdf")
            gt=json.loads(_fetch(client,f"result_gt/{number}.json"))
            text,_,method=extract_file("reference.pdf",blob)
            draft=convert_resume(parse_resume(text),raw_text=text,fingerprint="")
            snapshot=draft.model_dump()
            hints=propose_existing_work_relations(draft,blob,method=method)
            if draft.model_dump()!=snapshot:
                raise AssertionError("Candidate hints mutated the source résumé")
            summary["checked_pdfs"]+=1
            summary["hint_count"]+=len(hints)
            for hint in hints:
                record=draft.experience[hint["experience_index"]]
                if not (hint["status"]=="unverified" and
                        hint["source_heading"]==record.heading and
                        record.role=="" and record.start_date and record.end_date):
                    raise AssertionError("Hint lacks the required provenance boundary")
                matched=any(
                    normalized(item.get("position",""))==normalized(hint["suggested_role"])
                    and normalized(item.get("companyName",""))==normalized(hint["suggested_company"])
                    for item in gt.get("workExperience",[])
                )
                summary["matched_paired_external_gt" if matched else
                        "not_matched_paired_external_gt"]+=1
                safe_cases.append({"synthetic_id":number,
                                   "matched_paired_external_gt":bool(matched)})
    return {
        "dataset":"pinned_external_synthetic_resume",
        "counts":dict(summary),
        "hint_metadata":safe_cases,
        "source_resume_altered":False,
        "hints_auto_scored":False,
        "real_applicant_validation":False,
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True))
