"""Anonymized geometry evidence for role tokens missing from structured fields.

Uses independent labels only for diagnosing error *classes*, never for filling
the extracted résumé. Output excludes strings from CV or GT.
"""
from __future__ import annotations
from collections import Counter
import json,re
import httpx,pymupdf

from app.parser import extract_file,parse_resume
from app.diagnosis.adapter import convert_resume
from scripts.benchmark_external_resume_corpus import IDS,_fetch,normalized

TITLE_SUFFIXES=("工程师","经理","主管","总监","设计师","分析师",
                "专员","负责人","助理","实习生","Engineer",
                "Developer","Manager","Analyst","Designer")


def run(ids=IDS):
    output=[]; counts=Counter()
    with httpx.Client(timeout=18,headers={"User-Agent":"PaperPro-geometry-debug"}) as http:
        for number in ids:
            pdf_bytes=_fetch(http,f"resume_list_pdf/{number}.pdf")
            gt=json.loads(_fetch(http,f"result_gt/{number}.json"))
            text,_,_=extract_file("cv.pdf",pdf_bytes)
            r=convert_resume(parse_resume(text),raw_text="",fingerprint="")
            with pymupdf.open(stream=pdf_bytes,filetype="pdf") as pdf:
                spans=[]
                for page_index,page in enumerate(pdf):
                    for block in page.get_text("dict").get("blocks",[]):
                        if block.get("type")!=0:continue
                        for line in block["lines"]:
                            for span in line["spans"]:
                                if span.get("text","").strip():
                                    spans.append((page_index,span))
            for expected in gt.get("workExperience") or []:
                role=str(expected.get("position") or "")
                norm=normalized(role)
                if not norm or not any(norm in normalized(e.heading) for e in r.experience):
                    continue
                if any(norm in normalized(e.role) for e in r.experience):
                    continue
                likely=next(e for e in r.experience if norm in normalized(e.heading))
                visible=likely.heading
                matches=[(pg,s) for pg,s in spans if norm in normalized(s["text"])]
                company=str(expected.get("companyName") or "")
                company_matches=[(pg,s) for pg,s in spans if normalized(company) and normalized(company) in normalized(s["text"])]
                suffix_known=any(role.endswith(x) for x in TITLE_SUFFIXES)
                role_loc=matches[0] if matches else None
                employer_loc=company_matches[0] if company_matches else None
                if role_loc and employer_loc:
                    ar=role_loc[1]["bbox"];ae=employer_loc[1]["bbox"]
                    horizontal_gap=round(ar[0]-ae[2],1)
                    vertical_gap=round(ar[1]-ae[1],1)
                    overlapping_y=max(0,min(ar[3],ae[3])-max(ar[1],ae[1]))
                    vertical_overlap=round(overlapping_y/max(.001,min(ar[3]-ar[1],ae[3]-ae[1])),2)
                else:
                    horizontal_gap=vertical_gap=vertical_overlap=None
                same_row=(
                    [(pg,s) for pg,s in spans
                     if role_loc and pg==role_loc[0] and
                     abs(s["bbox"][1]-role_loc[1]["bbox"][1])<=2.5]
                    if role_loc else []
                )
                row_sorted=sorted(same_row,key=lambda x:x[1]["bbox"][0])
                try:
                    role_at_x=next(i for i,(_,s) in enumerate(row_sorted)
                                   if s is role_loc[1])
                except (StopIteration,TypeError):
                    role_at_x=-1
                detail={
                    "id":number,
                    "same_row_span_count":len(same_row),
                    "row_matches_heading":bool(same_row and (
                        normalized(visible) in normalized(" ".join(
                            s["text"] for _,s in row_sorted))
                        or normalized(" ".join(
                            s["text"] for _,s in row_sorted)) in normalized(visible)
                    )),
                    "role_index_in_row":role_at_x,
                    "row_has_year":any(re.search(r"(?:19|20)\d\d",s["text"])
                                       for _,s in same_row),
                    "first_span_contains_complete_period":bool(
                        row_sorted and __import__(
                            "app.diagnosis.adapter",fromlist=["DATE_RANGE"]
                        ).DATE_RANGE.search(row_sorted[0][1]["text"])
                    ),
                    "last_span_has_company_suffix":bool(
                        row_sorted and re.search(
                            r"公司|集团|事务所|机构|研究院|中心|学校|大学|学院|实验室",
                            row_sorted[-1][1]["text"]
                        )
                    ),
                    "middle_span_has_company_suffix":bool(
                        len(row_sorted)>1 and re.search(
                            r"公司|集团|事务所|机构|研究院|中心|学校|大学|学院|实验室",
                            row_sorted[1][1]["text"]
                        )
                    ),
                    "row_has_contact":any("@" in s["text"] for _,s in same_row),
                    "role_company_horizontal_gap":horizontal_gap,
                    "role_company_vertical_gap":vertical_gap,
                    "role_company_vertical_overlap":vertical_overlap,
                    "role_span_page":role_loc[0] if role_loc else None,
                    "company_span_page":employer_loc[0] if employer_loc else None,
                    "literal_suffix_known":suffix_known,
                    "entry_has_year":bool(re.search(r"(?:19|20)\d{2}",visible)),
                    "entry_has_role_near_end":normalized(visible).endswith(norm),
                    "found_own_span":bool(matches),
                    "role_and_company_in_same_span":any(
                        normalized(company) in normalized(s["text"]) for _,s in matches
                    ) if company else False,
                    "role_span_font_size":round(matches[0][1].get("size",0),1) if matches else None,
                    "role_span_boldish":bool(matches and ("Bold" in matches[0][1].get("font","") or
                                                       (matches[0][1].get("flags",0)&16))),
                    "role_company_share_span":bool(matches and company_matches and
                        matches[0][1] is company_matches[0][1]),
                    "num_matching_spans":len(matches),
                }
                output.append(detail)
                for key in ("literal_suffix_known","entry_has_year","entry_has_role_near_end",
                            "found_own_span","role_and_company_in_same_span"):
                    counts[key+"_true" if detail[key] else key+"_false"]+=1
    return {"unmapped_role_occurrences":len(output),"stats":dict(counts),"safe_cases":output}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True))
