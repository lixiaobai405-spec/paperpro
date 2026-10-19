"""Read-only structural diagnosis of pinned third-party *synthetic* resumes.

No names, emails, employer names, raw CV lines, or role strings are output.
Only known section tags, offsets and mapping states.
"""
from __future__ import annotations

from collections import Counter
import json
import re
import httpx

from scripts.benchmark_external_resume_corpus import IDS, _fetch, normalized
from app.parser import extract_file, parse_resume, _section
from app.diagnosis.adapter import convert_resume


SECTION_HINTS = {
    "work": ("工作经历", "工作经验", "实习", "任职", "校园实践",
             "社会实践", "社会工作", "工作履历", "职场经历",
             "employment", "experience", "career history", "job history",
             "work history", "activities", "practice", "professional"),
    "education": ("教育", "学历", "学习经历", "education", "academic"),
    "project": ("项目", "作品", "projects", "project"),
    "summary": ("自我", "简介", "评价", "总结", "summary", "about me"),
}


def run(ids=IDS) -> dict:
    records=[]
    patterns=Counter()
    with httpx.Client(timeout=16,headers={"User-Agent":"PaperPro-open-benchmark"}) as http:
        for n in ids:
            gt=json.loads(_fetch(http,f"result_gt/{n}.json"))
            blob=_fetch(http,f"resume_list_pdf/{n}.pdf")
            text,_,_=extract_file("source.pdf",blob)
            parsed=convert_resume(parse_resume(text),raw_text="",fingerprint="")
            lines=[v.strip() for v in text.splitlines() if v.strip()]
            states=[]
            current="header"
            cues=[]
            for i,line in enumerate(lines):
                section=_section(line)
                if section:
                    current=section
                    states.append({"at":i,"section":section})
                for kind,terms in SECTION_HINTS.items():
                    if any(term.casefold() in line.casefold() for term in terms):
                        if len(line)<65:
                            cues.append({
                                "index":i,"expected_kind":kind,
                                "recognized_as":_section(line),
                                "has_slash":"/" in line or "|" in line,
                                "has_colon":":" in line or "：" in line,
                                "line_length":len(line),
                                "recognized_hint_tokens":[term for term in terms
                                    if term.casefold() in line.casefold()],
                                "looks_like_standalone_heading":(
                                    len(line.strip())<=32
                                    and not any(char.isdigit() for char in line)
                                    and not any(c in line for c in ("@", ".com", "http"))
                                ),

                            })
            expected_roles=[normalized(item.get("position",""))
                            for item in gt.get("workExperience",[]) if item.get("position")]
            basic=gt.get("basicInfo") or {}
            candidate_email=str(basic.get("personalEmail") or "")
            candidate_phone=str(basic.get("phoneNumber") or "")
            contact_places={}
            for key,value in (("email",candidate_email),("phone",candidate_phone)):
                if not value:
                    continue
                contact_places[key]=[{
                    "line":i,
                    "section":next((s["section"] for s in reversed(states)
                                    if s["at"]<i),"header"),
                    "has_label":any(marker in line.casefold() for marker in (
                        "邮箱","电子邮件","邮件","手机","电话","email","phone","tel",
                        "mobile","contact"
                    )),
                    "line_chars":len(line),
                } for i,line in enumerate(lines) if normalized(value) in normalized(line)][:5]
            role_locations=[]
            for role in expected_roles:
                positions=[i for i,line in enumerate(lines) if role in normalized(line)]
                role_locations.append({
                    "found":bool(positions),
                    "line_indices":positions[:4],
                    "in_sections":[{
                        "index":i,
                        "group":next((s["section"] for s in reversed(states) if s["at"]<i),"header"),
                    } for i in positions[:4]],
                })
            classification=(
                "no_work_block" if not parsed.experience else "has_work_block"
            )
            patterns[classification]+=1
            records.append({
                "synthetic_id":n,"gt_work_count":len(expected_roles),
                "parsed_work_count":len(parsed.experience),
                "section_events":states[:17],
                "section_cue_features":cues[:18],
                "role_placement":role_locations[:8],
                "contact_locations":contact_places,
                "contact_found_in_result":{"email":bool(parsed.email),"phone":bool(parsed.phone)},
            })
    return {
        "pinned_source":True,"pdf_count":len(ids),
        "counts":dict(patterns),"records":records,
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True,indent=2))
