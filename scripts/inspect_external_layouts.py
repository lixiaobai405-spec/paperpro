"""Source-schema layout diagnostics for independent synthetic PDF files.

Optional GitHub API calls (rate limited); outputs field counts and structural
signals only, never names, phones, emails, gender, affiliations, or PDF text.
"""
from __future__ import annotations

import json
import httpx

from .benchmark_external_resume_corpus import _fetch
from app.parser import extract_file, parse_resume
from app.diagnosis.adapter import convert_resume


def debug(ids=(1, 2)) -> list[dict]:
    result=[]
    with httpx.Client(timeout=25, headers={
        "User-Agent":"PaperPro-open-benchmark"
    }) as client:
        for id_ in ids:
            annotation=json.loads(_fetch(client,f"result_gt/{id_}.json"))
            file=_fetch(client,f"resume_list_pdf/{id_}.pdf")
            source,_,method=extract_file("reference.pdf",file)
            draft=convert_resume(parse_resume(source),raw_text="",fingerprint="")
            sections=("工作经历 / Experience","教育背景 / Education","个人评价 / About Me")
            result.append({
                "external_synthetic_id":id_,
                "method":method,
                "source_line_count":len(source.splitlines()),
                "bilingual_header_count":sum(s in source for s in sections),
                "independent_work_annotation_count":len(annotation.get("workExperience") or []),
                "parsed_work_entry_count":len(draft.experience),
                "parsed_role_count":sum(bool(e.role) for e in draft.experience),
                "independent_education_annotation_count":len(annotation.get("education") or []),
                "parsed_education_count":len(draft.education),
            })
    return result


if __name__=="__main__":
    print(json.dumps(debug(),ensure_ascii=True,indent=2))
