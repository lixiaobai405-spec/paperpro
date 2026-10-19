"""Aggregate only, privacy-safe profile of external synthetic work-role layouts.

No names, contact details, employer strings, role strings or PDF text emitted.
Uses the pinned 20-item corpus with unchanged independent ground truth.
"""
from __future__ import annotations

from collections import Counter
import json

import httpx
from app.parser import extract_file, parse_resume
from app.diagnosis.adapter import convert_resume
from scripts.benchmark_external_resume_corpus import IDS, _fetch, normalized


def summarize(ids=IDS):
    tally = Counter()
    examples = {}
    heading_shapes=[]
    with httpx.Client(timeout=15, headers={"User-Agent":"PaperPro-open-benchmark"}) as client:
        for n in ids:
            gt = json.loads(_fetch(client, f"result_gt/{n}.json"))
            pdf = _fetch(client, f"resume_list_pdf/{n}.pdf")
            text, _, _ = extract_file(f"external-synthetic-{n}.pdf",pdf)
            source = parse_resume(text)
            draft = convert_resume(source,raw_text="",fingerprint="")
            work = gt.get("workExperience") or []
            for item in work:
                role=normalized(str(item.get("position") or ""))
                if not role:
                    continue
                tally["total"]+=1
                if role not in normalized(text):
                    category="role_not_in_pdf_text"
                elif not draft.experience:
                    category="no_experience_parsed"
                elif any(role in normalized(e.role) for e in draft.experience):
                    category="already_in_role"
                elif any(role in normalized(e.heading) for e in draft.experience):
                    category="role_in_experience_heading_but_not_role_field"
                elif any(role in normalized(" ".join(e.bullets)) for e in draft.experience):
                    category="role_in_experience_bullets"
                else:
                    category="role_elsewhere_in_document"
                tally[category]+=1
                if category=="role_in_experience_heading_but_not_role_field":
                    employer=normalized(str(item.get("companyName") or ""))
                    for entry in draft.experience:
                        head=normalized(entry.heading)
                        pos=head.find(role)
                        if pos<0:
                            continue
                        employer_pos=head.find(employer) if employer else -1
                        group=(
                            "employer_precedes_role" if 0<=employer_pos<pos
                            else "role_precedes_employer" if 0<=pos<employer_pos
                            else "employer_not_in_heading"
                        )
                        tally["shape_"+group]+=1
                        literal_role=str(item.get("position") or "")
                        raw_pos=entry.heading.find(literal_role)
                        if raw_pos>=0:
                            before=entry.heading[raw_pos-1] if raw_pos else ""
                            sep_class=("whitespace" if before.isspace() else
                                       "punctuation" if before in "-–—|｜丨:：/·" else
                                       "chinese_character" if "\u4e00"<=before<="\u9fff" else
                                       "other")
                            tally["preceding_"+sep_class]+=1
                            if raw_pos+len(literal_role)==len(entry.heading):
                                tally["role_at_literal_end"]+=1
                        if len(heading_shapes)<16:
                            heading_shapes.append({
                                "id":n,"role_at_end":pos+len(role)==len(head),
                                "role_at_start":pos==0,"company_relation":group,
                                "has_vertical_bar":"|" in entry.heading or "丨" in entry.heading,
                                "has_colon":":" in entry.heading or "：" in entry.heading,
                                "has_date_prefix":entry.heading[:4].isdigit(),
                                "heading_length":len(entry.heading),
                            })
                        break
                examples.setdefault(category,[])
                if len(examples[category])<8 and n not in examples[category]:
                    examples[category].append(n)
    return {"total_expected_roles":tally["total"],"categories":dict(tally),"example_public_synthetic_ids":examples,"safe_heading_shapes":heading_shapes}


if __name__=="__main__":
    print(json.dumps(summarize(),ensure_ascii=True,indent=2))
