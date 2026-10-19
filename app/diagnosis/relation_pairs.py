"""Pairwise geometry interface for independently labeled synthetic resumes.

Never use the existing PaperPro score or inferred role as ground truth.
Candidate pairs are drawn from independently annotated company/role entries
when *both* source strings uniquely align to native PDF text. A different
work-entry index is a negative only when company AND role texts differ.
Repeated or ambiguous anchors are excluded, not mislabeled as negatives.

Rows contain no source resume text, contact, employer name, or role string.
No model is trained, saved, or deployed by this module.
"""
from __future__ import annotations

from collections import Counter
import math
import re

from .annotation_alignment import prohibit_holdout_training

FEATURE_NAMES=(
    "same_page", "vertical_alignment", "vertical_gap",
    "horizontal_center_delta", "role_right_of_company", "vertical_overlap"
)


def _norm(value: str) -> str:
    return re.sub(r"[\W_]+","",value,flags=re.UNICODE).casefold()


def _overlap(a: tuple,b: tuple) -> float:
    return max(0,min(a[3],b[3])-max(a[1],b[1]))


def _geometry(company: dict,role: dict) -> tuple[float,...]:
    cb,rb=company["line_bbox"],role["line_bbox"]
    same=float(company["page_index"]==role["page_index"])
    ch=max(1e-5,cb[3]-cb[1]);rh=max(1e-5,rb[3]-rb[1])
    cy=(cb[1]+cb[3])/2; ry=(rb[1]+rb[3])/2
    ydiff=abs(cy-ry)
    alignment= max(0.0,1.0-ydiff/(6*max(ch,rh))) if same else 0.0
    gap= max(0.0,max(cb[1],rb[1])-min(cb[3],rb[3])) if same else 1.0
    gap=min(1.0,gap/(6*max(ch,rh)))
    cx=(cb[0]+cb[2])/2; rx=(rb[0]+rb[2])/2
    center_delta=round(max(-1.0,min(1.0,rx-cx)),6)
    right=float(rb[0]>=cb[2]-.002) if same else 0.0
    overlap=min(1.0,_overlap(cb,rb)/min(ch,rh)) if same else 0.0
    return tuple(round(float(x),6) for x in (
        same,alignment,gap,center_delta,right,overlap
    ))


def build_relation_pairs(
    aligned: dict, annotation: dict, *, source_id: int,
    holdout_ids: tuple[int,...], training: bool,
) -> list[dict]:
    """Return only uniquely anchored, independently labeled relation rows.

    Excludes ambiguous same-line annotations and duplicate job identities;
    no negative labels are inferred from absent or OCR-missing fields.
    """
    if training:
        prohibit_holdout_training(source_id,holdout_ids=holdout_ids)
    anchors={
        item["annotation_ref"]:item
        for item in aligned.get("unique_anchors",[])
        if item.get("field") in {"work_role","employer"}
    }
    if not anchors:
        return []
    # If a field's single source line is referenced by two GT entries, its
    # ownership is ambiguous even though both individual text matches are
    # unique. Never use the duplicated anchor for training.
    identities=Counter(
        (item["field"],item["page_index"],tuple(item["line_bbox"]))
        for item in anchors.values()
    )
    valid={
        ref:anchor for ref,anchor in anchors.items()
        if identities[(anchor["field"],anchor["page_index"],
                       tuple(anchor["line_bbox"]))]==1
    }
    jobs=[]
    for i,work in enumerate(annotation.get("workExperience") or []):
        if not isinstance(work,dict):
            continue
        company=valid.get(f"workExperience.{i}.companyName")
        role=valid.get(f"workExperience.{i}.position")
        company_string=work.get("companyName")
        role_string=work.get("position")
        if not company or not role or not (
            isinstance(company_string,str) and company_string.strip() and
            isinstance(role_string,str) and role_string.strip()
        ):
            continue
        jobs.append((i,company,role,_norm(company_string),_norm(role_string)))
    rows=[]
    for role_id,_,role_anchor,_,role_text in jobs:
        for employer_id,company_anchor,_,company_text,_ in jobs:
            label=int(role_id==employer_id)
            if not label:
                # Shared employer or shared role across separate GT entries
                # need further human review. Do not invent contradictory
                # labels from their work-record ordering.
                role_job=next(v for v in jobs if v[0]==role_id)
                employer_job=next(v for v in jobs if v[0]==employer_id)
                if (role_text==employer_job[4]
                    or company_text==role_job[3]):
                    continue
            rows.append({
                "source_id":source_id,
                "role_ref":f"workExperience.{role_id}.position",
                "employer_ref":f"workExperience.{employer_id}.companyName",
                "features":list(_geometry(company_anchor,role_anchor)),
                "label":label,
                "label_source":"independent_gt_work_record",
                "split":"train_candidate" if training else "holdout_evaluation",
                "ready_for_deployment":False,
            })
    return rows
