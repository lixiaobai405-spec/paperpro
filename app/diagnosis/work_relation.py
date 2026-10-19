"""Conservative PDF geometry relationship for existing dated work entries.

Only a three-span row (date range | organization | possible job title) may
generate a review proposal. Geometry is weak supporting evidence, never
proof of employment; it must not rewrite source records or scoring features.
No new work entries, titles or dates are created before human confirmation.
"""
from __future__ import annotations

import re

import pymupdf

from .adapter import DATE_RANGE, _normalized_month
from .schema import WorkRelationHint

ORG_SUFFIX = re.compile(
    r"(?:有限公司|股份公司|集团|公司|事务所|研究院|研究所|学校|大学|医院|"
    r"实验室|机构|工厂|服务中心|事业部|工作室)$"
)
CHINESE_ROLE = re.compile(r"^[\u4e00-\u9fff]{2,14}$")
CONTACT = re.compile(r"(?:@|(?:^|\D)1[3-9]\d{9}(?:\D|$))")


def _compact(value: str) -> str:
    return re.sub(r"[\s|丨｜·•]+", "", value).casefold()


def _visual_rows(page: pymupdf.Page) -> list[list[dict]]:
    """Return text spans in a common physical row (not sorted reading order)."""
    spans=[]
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type")!=0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text=span.get("text","").strip()
                if not text:
                    continue
                x0,y0,x1,y1=span["bbox"]
                spans.append({
                    "text":text,"x0":x0,"x1":x1,"y0":y0,"y1":y1
                })
    if not 3<=len(spans)<=650:
        return []
    # Text-run start y (same baseline/font) is stable in separate PDF
    # columns. Require near-identical top coordinates for a relationship.
    rows=[]
    for s in sorted(spans,key=lambda v:(v["y0"],v["x0"])):
        if rows and abs(s["y0"]-rows[-1][0]["y0"])<=2.5:
            rows[-1].append(s)
        else:
            rows.append([s])
    return [sorted(row,key=lambda v:v["x0"]) for row in rows]


def _candidate_row(row: list[dict]) -> tuple[str,str,str,str] | None:
    if len(row)!=3:
        return None
    date_run,employer,role=row
    if not (date_run["x1"]+4<=employer["x0"]
            and employer["x1"]+4<=role["x0"]):
        return None
    match=DATE_RANGE.fullmatch(date_run["text"].strip())
    if not match:
        return None
    company=employer["text"].strip()
    position=role["text"].strip()
    if not (3<=len(company)<=65 and ORG_SUFFIX.search(company)):
        return None
    if not (CHINESE_ROLE.fullmatch(position)
            and not ORG_SUFFIX.search(position)
            and not CONTACT.search(company+position)
            and not re.search(r"工作经历|教育经历|求职意向|项目经历|联系方式|"
                              r"学校地址|个人简介|代表作品|职责描述|简介|履历|课程",
                              position)):
        return None
    return (_normalized_month(match.group("start")),
            _normalized_month(match.group("end")) if re.match(
                r"^(?:19|20)\d{2}",match.group("end")) else match.group("end"),
            company,position)


def _normalized_box(span: dict, page: pymupdf.Page) -> tuple[float, float, float, float] | None:
    """Use the same 0–1 physical coordinate system for every page."""
    if page.rect.width <= 0 or page.rect.height <= 0:
        return None
    values = (
        span["x0"] / page.rect.width,
        span["y0"] / page.rect.height,
        span["x1"] / page.rect.width,
        span["y1"] / page.rect.height,
    )
    result = tuple(round(min(1.0, max(0.0, value)), 5) for value in values)
    if not (0 <= result[0] < result[2] <= 1
            and 0 <= result[1] < result[3] <= 1):
        return None
    return result


def propose_existing_work_relations(
    candidate, pdf_bytes: bytes, *, method: str
) -> list[dict]:
    """Return uncertain role/company proposals; NEVER update resume or score.

    Three side-by-side text spans do not prove the final one is a job title.
    Candidates are informational until a human explicitly accepts one in
    the review UI. A multi-match or duplicated source row is omitted.
    """
    if method!="pdf-text" or not candidate.experience or all(
        record.role or not record.start_date or not record.end_date
        for record in candidate.experience
    ):
        return []
    source_norm=_compact(candidate.source_text)
    choices={}
    with pymupdf.open(stream=pdf_bytes,filetype="pdf") as pdf:
        if len(pdf)>25:
            return []
        for page_index,page in enumerate(pdf):
            for row in _visual_rows(page):
                fields=_candidate_row(row)
                if not fields:
                    continue
                start,end,employer,position=fields
                row_text=" ".join(s["text"] for s in row)
                if _compact(row_text) not in source_norm:
                    continue
                boxes = {
                    field:_normalized_box(span,page)
                    for field,span in zip(("date","employer","role"),row)
                }
                if any(box is None for box in boxes.values()):
                    continue
                evidence={
                    "source_kind":"native_pdf_text",
                    "page_index":page_index,
                    "page_number":page_index+1,
                    "boxes":boxes,
                }
                key=(start,end,_compact(row_text))
                candidates=choices.setdefault(key,[])
                if not any(
                    item["company"]==employer and item["role"]==position
                    for item in candidates
                ):
                    candidates.append({
                        "company":employer,"role":position,
                        "evidence":evidence,
                    })
    proposals=[]
    used=set()
    for i,entry in enumerate(candidate.experience):
        if entry.role or not entry.start_date or not entry.end_date:
            continue
        head=_compact(entry.heading)
        options=[
            (key,value) for key,values in choices.items()
            if key[0]==entry.start_date and key[1]==entry.end_date
            and key[2]==head for value in values
            if _compact(value["company"]) in _compact(entry.company)
            and _compact(value["role"]) in _compact(entry.company)
        ]
        if len(options)!=1 or options[0][0] in used:
            continue
        key,value=options[0]
        if sum(_compact(item.heading)==head for item in candidate.experience)!=1:
            continue
        used.add(key)
        # These signals demonstrate layout alignment, not semantic truth.
        # The pinned external set has a known false positive even with all
        # signals; NEVER convert these into a probability or auto-adopt them.
        proposal=WorkRelationHint.model_validate({
            "id":f"work-relation-{i}",
            "experience_index":i,
            "field_path":f"experience.{i}.role",
            "source_path":f"experience.{i}.heading",
            "source_heading":entry.heading,
            "suggested_company":value["company"],
            "suggested_role":value["role"],
            "status":"unverified",
            "note":"仅为同行文字块排版候选，不能证明职位事实；人工确认前不写入简历，也不参与评分。",
            "evidence":value["evidence"],
            "confidence":{
                "tier":"low",
                "calibrated":False,
                "semantic_check":"not_verified",
                "signals":[
                    "horizontal_alignment",
                    "existing_dated_experience",
                    "same_source_text",
                    "organization_suffix",
                    "unique_existing_record",
                ],
                "missing":["independent_role_confirmation"],
            },
        })
        proposals.append(proposal.model_dump())
    return proposals
