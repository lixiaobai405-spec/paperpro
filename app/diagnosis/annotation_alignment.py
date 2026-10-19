"""Independent-annotation → native PDF text-line alignment (in-memory only).

This is the data interface for *future* structured extraction training. It
does not train a model, label unlabeled regions as negatives, call an API,
modify extracted resume data, or infer hiring outcomes.

The resulting anchors contain résumé text and MUST stay in process memory.
Callers and CLI scripts may display only aggregated counts / public synthetic
IDs, never the raw anchors or uploaded document text.
"""
from __future__ import annotations

from collections import defaultdict
import re

import pymupdf

FIELD_NAMES = ("work_role", "employer", "school")


def _norm(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _native_lines(pdf_bytes: bytes) -> list[dict]:
    lines=[]
    with pymupdf.open(stream=pdf_bytes,filetype="pdf") as document:
        if document.page_count>25:
            raise ValueError("最多支持 25 页 PDF")
        for page_index,page in enumerate(document):
            width,height=page.rect.width,page.rect.height
            if width<=0 or height<=0:
                continue
            for block in page.get_text("dict").get("blocks",[]):
                if block.get("type")!=0:
                    continue
                for line in block.get("lines",[]):
                    spans=[
                        s for s in line.get("spans",[])
                        if isinstance(s.get("text"),str) and s["text"].strip()
                    ]
                    if not spans:
                        continue
                    text="".join(s["text"] for s in spans).strip()
                    boxes=[s["bbox"] for s in spans]
                    x0=min(b[0] for b in boxes)
                    y0=min(b[1] for b in boxes)
                    x1=max(b[2] for b in boxes)
                    y1=max(b[3] for b in boxes)
                    bbox=(
                        round(x0/width,5),round(y0/height,5),
                        round(x1/width,5),round(y1/height,5),
                    )
                    if not (0<=bbox[0]<bbox[2]<=1 and
                            0<=bbox[1]<bbox[3]<=1):
                        continue
                    lines.append({
                        "page_index":page_index,
                        "line_bbox":bbox,
                        "source_line":text,
                        "span_count":len(spans),
                    })
    return lines


def _independent_fields(annotation: dict) -> list[tuple[str,str,str]]:
    annotations=[]
    for index,work in enumerate(annotation.get("workExperience") or []):
        if not isinstance(work,dict):
            continue
        for key,field in (("position","work_role"),("companyName","employer")):
            value=work.get(key)
            if isinstance(value,str) and value.strip():
                annotations.append((field,f"workExperience.{index}.{key}",value.strip()))
    for index,education in enumerate(annotation.get("education") or []):
        if not isinstance(education,dict):
            continue
        value=education.get("school")
        if isinstance(value,str) and value.strip():
            annotations.append(("school",f"education.{index}.school",value.strip()))
    return annotations


def prohibit_holdout_training(source_id: int, *, holdout_ids) -> None:
    """Prevent accidental train/test leakage when assembling future datasets."""
    if source_id in set(holdout_ids):
        raise ValueError("该编号属于保留测试集，不能混入训练数据")


def align_independent_annotations(pdf_bytes: bytes, annotation: dict) -> dict:
    """Align GT labels to *one* native PDF line, or abstain.

    A matching line does not prove which underlying employer/position record
    owns the token. Hence confidence is 'text_location_only' and all anchors
    require further label review before training.
    """
    lines=_native_lines(pdf_bytes)
    source_fields=_independent_fields(annotation)
    stats=defaultdict(lambda:{
        "expected":0,"unique_native_line":0,
        "ambiguous_multiple_lines":0,"not_found_in_native_lines":0
    })
    anchors=[]
    for field,ref,expected in source_fields:
        stats[field]["expected"]+=1
        target=_norm(expected)
        matches=[
            line for line in lines
            if target and target in _norm(line["source_line"])
        ]
        if not matches:
            stats[field]["not_found_in_native_lines"]+=1
        elif len(matches)>1:
            stats[field]["ambiguous_multiple_lines"]+=1
        else:
            stats[field]["unique_native_line"]+=1
            match=matches[0]
            anchors.append({
                "annotation_ref":ref,
                "field":field,
                "page_index":match["page_index"],
                "line_bbox":match["line_bbox"],
                "source_line":match["source_line"],
                "annotation_text":expected,
                "span_count":match["span_count"],
                "alignment_confidence":"text_location_only",
                "ready_for_training":False,
            })
    return {
        "source_kind":"independent_public_synthetic_annotations",
        "native_line_count":len(lines),
        "field_counts":{field:stats[field] for field in FIELD_NAMES},
        "unique_anchors":anchors,
        "negative_examples_generated":0,
        "labels_are_hiring_outcomes":False,
        "note":"Unique textual locations are alignment candidates, not verified job relationships.",
    }



def measure_work_relation_alignment(aligned: dict, annotation: dict) -> dict:
    """Count independent-GT employer/role pairs whose anchors are co-located.

    Geometry can suggest candidate training relations but is *not* proof of
    true employment or correctness of a future extracted tuple. All counts
    exclude ambiguous textual matches. Never output source text or names.
    """
    by_ref={
        anchor["annotation_ref"]:anchor
        for anchor in aligned["unique_anchors"]
    }
    result={
        "annotated_pairs":0,
        "both_uniquely_anchored":0,
        "same_page":0,
        "same_visual_row":0,
        "nearby_on_same_page":0,
        "training_pairs_emitted":0,
    }
    for index,work in enumerate(annotation.get("workExperience") or []):
        if not isinstance(work,dict) or not (
            isinstance(work.get("position"),str) and work["position"].strip()
            and isinstance(work.get("companyName"),str)
            and work["companyName"].strip()
        ):
            continue
        result["annotated_pairs"]+=1
        role=by_ref.get(f"workExperience.{index}.position")
        company=by_ref.get(f"workExperience.{index}.companyName")
        if not role or not company:
            continue
        result["both_uniquely_anchored"]+=1
        if role["page_index"]!=company["page_index"]:
            continue
        result["same_page"]+=1
        rb=role["line_bbox"]
        cb=company["line_bbox"]
        rcy=(rb[1]+rb[3])/2
        ccy=(cb[1]+cb[3])/2
        rheight=rb[3]-rb[1]
        cheight=cb[3]-cb[1]
        # Compare local line heights, not fixed PDF-page dimensions.
        if abs(rcy-ccy)<=0.35*max(rheight,cheight):
            result["same_visual_row"]+=1
        separation=max(0,max(rb[1],cb[1])-min(rb[3],cb[3]))
        if separation<=2*max(rheight,cheight):
            result["nearby_on_same_page"]+=1
    return result
