"""GT-blind WorkBlock candidates from PyMuPDF4LLM native layout JSON.

This module does not import or require PyMuPDF4LLM: a separate *optional*
isolated evaluator invokes that AGPL/commercial-license tool and passes its
JSON layout representation into this read-only adapter. The production
parser, CLI environment, score, and user files are not changed.

Source text and boxes remain in memory. An unknown model-classified section
header terminates any active work region: false promotions are not allowed.
Every result is an unverified region, NOT a confirmed employment record.
"""
from __future__ import annotations

from collections import Counter
import math

from app.parser import _section
from .workblock_regions import (
    MAX_WORKBLOCKS, _lane_of, _date_candidate, _union_bbox,
)


def _validated_layout_lines(page: dict, index: int) -> list[dict]:
    width=page.get("width")
    height=page.get("height")
    if (not isinstance(width,(int,float))
        or not isinstance(height,(int,float))
        or not math.isfinite(width) or not math.isfinite(height)
        or width<=0 or height<=0):
        raise ValueError("版式页面尺寸必须有效")
    lines=[]
    boxes=page.get("boxes") or []
    if not isinstance(boxes,list) or len(boxes)>500:
        raise ValueError("版式对象数量异常")
    for box in boxes:
        if not isinstance(box,dict) or not box.get("textlines"):
            continue
        boxclass=str(box.get("boxclass") or "")
        for entry in box["textlines"]:
            if not isinstance(entry,dict) or not entry.get("spans"):
                continue
            raw_box=entry.get("bbox")
            if not (isinstance(raw_box,(list,tuple))
                    and len(raw_box)==4
                    and all(isinstance(x,(int,float)) and math.isfinite(x)
                            for x in raw_box)):
                continue
            x0,y0,x1,y1=raw_box
            if not (0<=x0<x1<=width and 0<=y0<y1<=height):
                continue
            text="".join(
                span.get("text","") for span in entry["spans"]
                if isinstance(span,dict)
                and isinstance(span.get("text"),str)
            ).strip()
            if not text or len(text)>800:
                continue
            lines.append({
                "page_index":index,
                "line_bbox":tuple(
                    round(v/(width if j%2==0 else height),5)
                    for j,v in enumerate(raw_box)
                ),
                "source_line":text,
                "layout_section_header":boxclass in (
                    "section-header","title","chapter-header"
                ),
                "layout_boxclass":boxclass,
            })
    return lines


def _section_regions(
    lines: list[dict], *, unknown_heading_policy: str = "close"
) -> list[list[dict]]:
    regions=[]
    active=None
    current=[]
    for line in sorted(lines,key=lambda x:(
        x["line_bbox"][1],x["line_bbox"][0]
    )):
        section=_section(line["source_line"])
        # A recognized section is a strong semantic boundary. A model-only
        # "section-header" might instead be a styled company or job title;
        # its handling is a deliberately isolated experimental variable.
        should_close=bool(section) or (
            bool(line["layout_section_header"])
            and unknown_heading_policy=="close"
        )
        if should_close:
            if active=="experience" and current:
                regions.append(current)
            active=section
            current=[]
            continue
        if active=="experience":
            current.append(line)
    if active=="experience" and current:
        regions.append(current)
    return regions


def _split_for_independent_sections(lines: list[dict]) -> float | None:
    # A horizontal gutter alone cannot establish semantic column ownership.
    # Require two explicit section headings on opposite sides and enough
    # independent text. Never concatenate the entire left column first.
    for boundary in (0.5,0.45,0.55,0.4,0.6):
        headings={}
        count=Counter()
        for line in lines:
            lane=_lane_of(line,boundary)
            count[lane]+=1
            if (section:=_section(line["source_line"])) is not None:
                headings.setdefault(lane,set()).add(section)
        if (headings.get("left") and headings.get("right")
            and min(count["left"],count["right"])>=3
            and count["ambiguous"]<=max(1,len(lines)*.18)):
            return boundary
    return None


def propose_workblocks_from_layout(
    layout_json: dict, *, unknown_heading_policy: str = "close"
) -> dict:
    """Recognize only dated native-text work regions in optional layout JSON.

    Does not read GT and does not infer employer/role values. The caller owns
    original source-byte SHA and may check provenance before any display.
    """
    if unknown_heading_policy not in ("close","keep"):
        raise ValueError("Invalid unknown_heading_policy")
    if (not isinstance(layout_json,dict)
        or not isinstance(layout_json.get("pages"),list)
        or len(layout_json["pages"])>25):
        raise ValueError("需要包含不超过 25 页的版式 JSON")
    proposed=[]
    sections=Counter()
    pages=[]
    for page_index,page in enumerate(layout_json["pages"]):
        lines=_validated_layout_lines(page,page_index)
        sections.update(
            str(section) for line in lines
            if (section:=_section(line["source_line"])) is not None
        )
        split=_split_for_independent_sections(lines)
        lanes=("left","right") if split is not None else ("page",)
        pages.append({
            "page_index":page_index,
            "parallel_section_lanes":split is not None,
            "text_line_count":len(lines),
            "layout_boxes":len(page.get("boxes") or []),
        })
        for lane in lanes:
            selected=[line for line in lines if _lane_of(line,split)==lane]
            for region in _section_regions(
                selected,unknown_heading_policy=unknown_heading_policy
            ):
                anchors=[
                    (line,_date_candidate(line["source_line"]))
                    for line in region
                    if _date_candidate(line["source_line"]) is not None
                ]
                anchors.sort(key=lambda x:(
                    x[0]["line_bbox"][1],x[0]["line_bbox"][0]
                ))
                for anchor_index,(anchor,dates) in enumerate(anchors):
                    if len(proposed)>=MAX_WORKBLOCKS:
                        break
                    y0=anchor["line_bbox"][1]-.003
                    y1=(
                        anchors[anchor_index+1][0]["line_bbox"][1]-.003
                        if anchor_index+1<len(anchors) else 1.0
                    )
                    worklines=sorted(
                        (line for line in region
                         if y0<=line["line_bbox"][1]<y1),
                        key=lambda x:(x["line_bbox"][1],x["line_bbox"][0])
                    )
                    if not worklines or anchor not in worklines:
                        continue
                    proposed.append({
                        "id":f"layout-workblock-{page_index}-{lane}-{anchor_index}",
                        "source_page_index":page_index,
                        "lane":lane,
                        "section":"experience",
                        "source_kind":"external_layout_engine_native_text",
                        "bbox":_union_bbox(worklines),
                        "dates":{"start":dates[0],"end":dates[1]},
                        "source_lines":[line["source_line"] for line in worklines],
                        "source_line_boxes":[line["line_bbox"] for line in worklines],
                        "source_text":"\n".join(
                            line["source_line"] for line in worklines
                        ),
                        "status":"unverified",
                        "confidence":{
                            "tier":"low","calibrated":False,
                            "basis":"layout_engine_work_section_and_date"
                        },
                        "auto_promote":False,
                    })
    return {
        "engine":"pymupdf4llm",
        "method":"optional_native_layout",
        "source_sections":dict(sections,experience=sections["experience"]),
        "layout_pages":pages,
        "workblocks":proposed,
        "candidate_count":len(proposed),
        "experimental_unknown_heading_policy":unknown_heading_policy,
        "automatic_resume_mutation":False,
        "deployed":False,
        "requires_human_confirmation":True,
    }
