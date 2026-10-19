"""GT-blind work-experience region candidates from *native PDF geometry*.

Unlike the old full-text parser, this intermediate representation keeps
section ownership and the visual coordinates of every contributing source
line. In clear two-column pages, left/right sections are scanned independently
instead of interleaving their text into a single linear stream.

This module does NOT assign a company, occupation, employment fact or hiring
score, and is intentionally NOT connected to the production candidate API.
Its workblocks are *unverified page regions*, not new CareerEntry records.
An independent GT is only used by offline evaluation *after* generation.

No external models, downloads, GPU, OCR, or document modification required.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import re

import pymupdf

from app.parser import _section
from .adapter import DATE_RANGE, _normalized_month
from .annotation_alignment import _native_lines
from .pdf_layout import detect_columns

BULLET = re.compile(r"^\s*(?:[-*•●▪◦·]\s+|\d{1,2}[)）.、]\s+)")
CONTACT = re.compile(r"@|https?://|www\.|(?<!\d)1[3-9]\d{9}(?!\d)",re.I)
MAX_WORKBLOCKS = 35


def _lane_of(line: dict, split: float | None, *, tolerance: float=.005) -> str:
    if split is None:
        return "page"
    left,right=line["line_bbox"][0],line["line_bbox"][2]
    if right<split-tolerance:
        return "left"
    if left>split+tolerance:
        return "right"
    # A bridging full-width line must not contaminate both section columns.
    return "ambiguous"


def _date_candidate(value: str) -> tuple[str,str] | None:
    """A short dated header, never a bullet or contact/date inside prose."""
    clean=value.strip()
    if len(clean)>110 or BULLET.match(clean) or CONTACT.search(clean):
        return None
    match=DATE_RANGE.search(clean)
    if not match or match.start()>48:
        return None
    # Prose discussing work performed 'during 2022.01–2023.04' is not
    # evidence of a new career entry. Date-at-start is the safest anchor;
    # allow only a short prefix that could be a source employer header.
    prefix=clean[:match.start()].strip()
    if prefix and (len(prefix)>32 or re.search(
        r"参与|负责|协助|完成|开发|项目|工作内容|期间|因|由于|数据处理",
        prefix
    )):
        return None
    end=match.group("end")
    return (
        _normalized_month(match.group("start")),
        _normalized_month(end) if re.match(r"^(?:19|20)\d{2}",end)
        else end
    )


def _union_bbox(lines: list[dict]) -> list[float]:
    xs=[p for item in lines for p in (
        item["line_bbox"][0],item["line_bbox"][2]
    )]
    ys=[p for item in lines for p in (
        item["line_bbox"][1],item["line_bbox"][3]
    )]
    return [
        round(min(xs),5),round(min(ys),5),
        round(max(xs),5),round(max(ys),5)
    ]


def _work_regions(page_lines: list[dict], lane: str) -> list[list[dict]]:
    """Partition each section from its own heading until the next heading."""
    ordered=sorted(page_lines,key=lambda x:(
        x["line_bbox"][1],x["line_bbox"][0]
    ))
    active=None
    current=[]
    regions=[]
    for line in ordered:
        section=_section(line["source_line"])
        if section:
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


def propose_pdf_workblocks(pdf_bytes: bytes) -> dict:
    """Return evidence-only WorkBlock proposals, never confirmed work records.

    Requires the experience section to be explicitly recognized. In a page
    with two genuinely independent column sections, use separate lane scans.
    For all other layouts, scan the native text lines in visual row order
    without imposing a global left-then-right reorder.
    """
    if (not isinstance(pdf_bytes,bytes) or not pdf_bytes.startswith(b"%PDF-")
        or len(pdf_bytes)>12*1024*1024):
        raise ValueError("需要大小不超过 12 MB 的有效 PDF 原文件")
    output=[]
    layout=[]
    section_counts=Counter()
    with pymupdf.open(stream=pdf_bytes,filetype="pdf") as document:
        if document.is_encrypted:
            raise ValueError("加密 PDF 不可进行版式分析")
        if document.page_count>25:
            raise ValueError("PDF 最多支持 25 页")
        source_lines=_native_lines(pdf_bytes)
        for index,page in enumerate(document):
            page_lines=[
                line for line in source_lines
                if line["page_index"]==index
            ]
            proposed_split=detect_columns(page)
            detected=(
                proposed_split[0]/page.rect.width
                if proposed_split and page.rect.width>0 else None
            )
            # PyMuPDF's native block density gate may abstain for short CVs.
            # A central-gutter fallback is allowed ONLY when two separate
            # explicit sections are present on opposite sides and there are
            # enough source lines on both sides, with little gutter bridging.
            # It is never permission to reorder an entire page by columns.
            split=None
            for boundary in (detected, 0.5):
                if boundary is None:
                    continue
                types={
                    lane:{
                        _section(line["source_line"])
                        for line in page_lines
                        if _lane_of(line,boundary)==lane
                        and _section(line["source_line"]) is not None
                    }
                    for lane in ("left","right")
                }
                lane_count={
                    lane:sum(_lane_of(line,boundary)==lane
                             for line in page_lines)
                    for lane in ("left","right","ambiguous")
                }
                if (types["left"] and types["right"]
                    and min(lane_count["left"],lane_count["right"])>=3
                    and lane_count["ambiguous"]<=len(page_lines)*.18):
                    split=boundary
                    break
            lanes=("left","right") if split is not None else ("page",)
            layout.append({
                "page_index":index,
                "parallel_section_lanes":split is not None,
                "declared_lanes":list(lanes),
                "text_line_count":len(page_lines),
            })
            for line in page_lines:
                section=_section(line["source_line"])
                if section:
                    section_counts[section]+=1

            for lane in lanes:
                in_lane=[
                    item for item in page_lines
                    if _lane_of(item,split)==lane
                ]
                for region in _work_regions(in_lane,lane):
                    # A region is bounded by explicit section headings.
                    # Missing date anchors are an abstention, not a reason
                    # to invent company/role/tenure.
                    anchors=[
                        (n,item,_date_candidate(item["source_line"]))
                        for n,item in enumerate(region)
                        if _date_candidate(item["source_line"]) is not None
                    ]
                    anchors.sort(key=lambda x:(
                        x[1]["line_bbox"][1],x[1]["line_bbox"][0]
                    ))
                    if not anchors:
                        continue
                    for nth,(_,anchor,dates) in enumerate(anchors):
                        if len(output)>=MAX_WORKBLOCKS:
                            break
                        begin=anchor["line_bbox"][1]-.003
                        end=(
                            anchors[nth+1][1]["line_bbox"][1]-.003
                            if nth+1<len(anchors) else 1.0
                        )
                        selected=sorted(
                            [
                                item for item in region
                                if begin<=item["line_bbox"][1]<end
                            ],
                            key=lambda x:(
                                x["line_bbox"][1],x["line_bbox"][0]
                            )
                        )
                        if not selected or anchor not in selected:
                            continue
                        output.append({
                            "id":f"workblock-{index}-{lane}-{nth}",
                            "source_page_index":index,
                            "lane":lane,
                            "section":"experience",
                            "source_kind":"native_pdf_geometry",
                            "bbox":_union_bbox(selected),
                            "dates":{
                                "start":dates[0],"end":dates[1],
                            },
                            "source_line_boxes":[
                                item["line_bbox"] for item in selected
                            ],
                            "source_lines":[
                                item["source_line"] for item in selected
                            ],
                            "source_text":"\n".join(
                                item["source_line"] for item in selected
                            ),
                            "status":"unverified",
                            "confidence":{
                                "tier":"low","calibrated":False,
                                "basis":"explicit_work_section_and_date_anchor"
                            },
                            "auto_promote":False,
                        })
    return {
        "method":"native_pdf_geometry",
        "source_sha256":sha256(pdf_bytes).hexdigest(),
        "source_sections":dict(section_counts, experience=section_counts["experience"]),
        "layout_pages":layout,
        "workblocks":output,
        "candidate_count":len(output),
        "automatic_resume_mutation":False,
        "deployed":False,
        "requires_human_confirmation":True,
    }
