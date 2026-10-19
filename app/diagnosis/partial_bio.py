"""Partially observed BIO training interface from independent PDF annotations.

Unlike conventional complete BIO data, these public synthetic résumés only
identify a few positive field strings. Everything outside uniquely anchored
GT substrings is UNKNOWN, **not O**. Assigning O there would fabricate many
negative labels and train an invalid background detector.

All source text and per-character labels remain strictly in process memory;
only aggregate summaries may be printed. This is a training-data contract,
not a trained sequence model, model confidence, or verified job relationship.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import re

from .annotation_alignment import _native_lines, _independent_fields
from .span_supervision import align_gt_char_spans, _substring_occurrences

FIELD_TAGS = {
    "work_role": "WORK_ROLE",
    "employer": "EMPLOYER",
    "school": "SCHOOL",
}
BIO_TAGS = ("O",) + tuple(
    tag for field in FIELD_TAGS.values()
    for tag in (f"B-{field}", f"I-{field}")
)

_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_PHONE = re.compile(r"^\+?\d[\d ().\-]*\d$")
_CONTACT_FIELDS = ("personalEmail", "phoneNumber")


def _independent_contacts(annotation: dict) -> list[tuple[str,str]]:
    """Only explicitly annotated contacts, never heuristically found ones."""
    basic = annotation.get("basicInfo") or {}
    if not isinstance(basic, dict):
        return []
    return [
        (field, basic[field].strip())
        for field in _CONTACT_FIELDS
        if isinstance(basic.get(field), str) and basic[field].strip()
    ]


def _valid_contact(field: str, value: str) -> bool:
    if field == "personalEmail":
        return bool(_EMAIL.fullmatch(value)) and len(value) <= 254
    if field == "phoneNumber":
        digits = sum(char.isdigit() for char in value)
        return (len(value) <= 32 and 8 <= digits <= 15
                and bool(_PHONE.fullmatch(value)))
    return False


def _literal_contact_occurrences(
    lines: list[dict], field: str, value: str,
) -> list[tuple[int,int,int]]:
    """Exact source substring offsets, including +, @, spaces and punctuation.

    Normalized/fuzzy contact matches are not background evidence: offsets
    could otherwise silently include unrelated characters.
    """
    matches=[]
    for i,line in enumerate(lines):
        source=line["source_line"]
        for match in re.finditer(re.escape(value), source, re.I):
            start,end=match.span()
            preceding = source[start-1] if start else ""
            following = source[end] if end < len(source) else ""
            if ((preceding and (preceding.isalnum() or preceding in ".@_"))
                or (following and (following.isalnum() or following in ".@_"))):
                continue
            if not _valid_contact(field,source[start:end]):
                continue
            matches.append((i,start,end))
    return matches


def _protected_gt_ranges(lines: list[dict], annotation: dict) -> dict[int,list[tuple[int,int]]]:
    """Protect target GT text even when its source location is ambiguous."""
    ranges:dict[int,list[tuple[int,int]]]={}
    for field,ref,raw in _independent_fields(annotation):
        if field not in FIELD_TAGS:
            continue
        for i,line in enumerate(lines):
            for start,end in _substring_occurrences(line["source_line"],raw):
                ranges.setdefault(i,[]).append((start,end))
    return ranges


def _verified_background_candidates(
    lines: list[dict], annotation: dict,
) -> tuple[list[dict],dict[str,int]]:
    counters={"ambiguous":0,"missing":0,"invalid":0,"conflicting":0}
    selected=[]
    for field,value in _independent_contacts(annotation):
        if not _valid_contact(field,value):
            counters["invalid"]+=1
            continue
        matches=_literal_contact_occurrences(lines,field,value)
        if len(matches)!=1:
            counters["ambiguous" if matches else "missing"]+=1
            continue
        i,start,end=matches[0]
        selected.append({
            "line_index":i,
            "start_char":start,"end_char":end,
            "field":field,
            "label_source":"independent_gt_contact",
        })
    protected=_protected_gt_ranges(lines,annotation)
    rejected=set()
    for a,s in enumerate(selected):
        if any(
            max(s["start_char"],start)<min(s["end_char"],end)
            for start,end in protected.get(s["line_index"],[])
        ):
            rejected.add(a)
        for b in range(a+1,len(selected)):
            other=selected[b]
            if s["line_index"]==other["line_index"] and (
                max(s["start_char"],other["start_char"]) <
                min(s["end_char"],other["end_char"])
            ):
                rejected.add(a);rejected.add(b)
    counters["conflicting"]=len(rejected)
    return [
        record for i,record in enumerate(selected) if i not in rejected
    ],counters


def build_partial_bio(
    pdf_bytes: bytes,
    independent_annotation: dict,
    *,
    source_id: int,
    allowed_train_ids: tuple[int, ...],
    forbidden_ids: tuple[int, ...],
) -> dict:
    """Build observed positives only, retaining unknown masks everywhere else.

    Source-ID safety is checked BEFORE independent labels are inspected. A
    unique native line must contain each non-overlapping GT match literally.
    If a line is repeated with the same coordinate/text key, omit ambiguous
    source anchors rather than invent a field location.
    """
    if source_id in set(forbidden_ids):
        raise ValueError("保留测试集不可用于构造序列训练标注")
    if source_id not in set(allowed_train_ids):
        raise ValueError("训练来源不属于已批准的训练分组")
    if not isinstance(pdf_bytes,bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("需要有效的 PDF 原始字节")
    lines=_native_lines(pdf_bytes)
    source_index: dict[tuple,list[int]]={}
    records=[]
    for idx,line in enumerate(lines):
        src=line["source_line"]
        key=(line["page_index"],tuple(line["line_bbox"]),src)
        source_index.setdefault(key,[]).append(idx)
        records.append({
            "page_index":line["page_index"],
            "line_bbox":line["line_bbox"],
            "source_line":src,
            "tags":[None]*len(src),
            "observed_mask":[False]*len(src),
            "verified_background_spans":[],
        })

    alignment=align_gt_char_spans(pdf_bytes,independent_annotation)
    applied=Counter()
    ambiguous_line_anchors=0
    for entry in alignment["positive_spans"]:
        key=(entry["page_index"],tuple(entry["line_bbox"]),entry["source_line"])
        indices=source_index.get(key,[])
        if len(indices)!=1:
            ambiguous_line_anchors+=1
            continue
        row=records[indices[0]]
        start,end=entry["start_char"],entry["end_char"]
        if not (0<=start<end<=len(row["source_line"])):
            ambiguous_line_anchors+=1
            continue
        if any(row["observed_mask"][i] for i in range(start,end)):
            ambiguous_line_anchors+=1
            continue
        label=FIELD_TAGS.get(entry["field"])
        if label is None:
            continue
        for i in range(start,end):
            row["tags"][i]=f"B-{label}" if i==start else f"I-{label}"
            row["observed_mask"][i]=True
        applied[entry["field"]]+=1

    background_candidates,background_abstentions=(
        _verified_background_candidates(lines,independent_annotation)
    )
    background_by_type=Counter()
    verified_background_spans=0
    for background in background_candidates:
        row=records[background["line_index"]]
        start,end=background["start_char"],background["end_char"]
        if any(row["observed_mask"][i] for i in range(start,end)):
            background_abstentions["conflicting"]+=1
            continue
        for i in range(start,end):
            row["tags"][i]="O"
            row["observed_mask"][i]=True
        row["verified_background_spans"].append({
            key:value for key,value in background.items() if key!="line_index"
        })
        background_by_type[background["field"]]+=1
        verified_background_spans+=1

    known=sum(sum(line["observed_mask"]) for line in records)
    n_chars=sum(len(line["tags"]) for line in records)
    if n_chars<known:
        raise AssertionError("Observed characters exceed all PDF text")
    fully=sum(bool(line["tags"]) and all(line["observed_mask"]) for line in records)
    background_chars=sum(sum(tag=="O" for tag in line["tags"]) for line in records)

    # The source dataset supplies no exhaustively annotated background. A
    # conventional O-vs-entity CRF/softmax is NOT identifiable from these
    # partial labels alone; a later loss must marginalize unknown positions.
    return {
        "source_id":source_id,
        "source_sha256":sha256(pdf_bytes).hexdigest(),
        "training_source_kind":"independent_GT_unique_char_spans",
        "lines":records,
        "total_characters":n_chars,
        "known_characters":known,
        "known_positive_characters":known-background_chars,
        "unknown_characters":n_chars-known,
        "observed_O_count":background_chars,
        "verified_background_span_count":verified_background_spans,
        "background_by_type":{field:background_by_type[field] for field in _CONTACT_FIELDS},
        "abstained_ambiguous_contact_spans":background_abstentions["ambiguous"],
        "abstained_missing_contact_spans":background_abstentions["missing"],
        "abstained_invalid_contact_fields":background_abstentions["invalid"],
        "abstained_conflicting_contact_spans":background_abstentions["conflicting"],
        "background_provenance":"independent_GT_contact_only",
        "negative_background_labels_created":0,
        "positive_span_count":sum(applied.values()),
        "positive_by_field":{field:applied[field] for field in FIELD_TAGS},
        "fully_labeled_lines":fully,
        "abstained_ambiguous_line_anchors":ambiguous_line_anchors,
        "complete_background_annotation":False,
        "standard_supervised_BIO_ready":False,
        "ready_for_deployment":False,
        "label_provenance":"independent_GT_textual_alignment_not_job_verification",
    }


def summarize_partial_bio(dataset: list[dict]) -> dict:
    """Privacy-preserving aggregate: NEVER serialize line data or field text."""
    if not dataset:
        raise ValueError("标注序列为空")
    ids=[item["source_id"] for item in dataset]
    hashes=[item["source_sha256"] for item in dataset]
    if len(ids)!=len(set(ids)) or len(hashes)!=len(set(hashes)):
        raise ValueError("同一 PDF 的重复记录不可当独立训练数据")
    known=sum(item["known_characters"] for item in dataset)
    known_positive=sum(item["known_positive_characters"] for item in dataset)
    o_total=sum(item["observed_O_count"] for item in dataset)
    n_chars=sum(item["total_characters"] for item in dataset)
    if not n_chars or any(item["negative_background_labels_created"]!=0 for item in dataset):
        raise ValueError("数据缺少源文字或含有未经审核的背景负例")
    # Every observed O must have a complete, exclusive, traceable contact
    # annotation. This also catches accidental global "UNKNOWN → O" code.
    for item in dataset:
        o_checked=0
        for row in item["lines"]:
            if len(row["source_line"])!=len(row["tags"]) or len(row["tags"])!=len(row["observed_mask"]):
                raise ValueError("BIO 标签或掩码与 PDF 原文字元数不一致")
            if any((tag is not None)!=bool(mask)
                   for tag,mask in zip(row["tags"],row["observed_mask"])):
                raise ValueError("观察掩码与实际标签不一致")
            observed=set()
            for span in row["verified_background_spans"]:
                start,end=span["start_char"],span["end_char"]
                field=span["field"]
                if (span["label_source"]!="independent_gt_contact" or
                    not 0<=start<end<=len(row["tags"]) or
                    not _valid_contact(field,row["source_line"][start:end])):
                    raise ValueError("背景标签缺少独立联系方式字段证明")
                if any(i in observed for i in range(start,end)):
                    raise ValueError("背景标签区间存在重复计数")
                observed.update(range(start,end))
            actual={i for i,tag in enumerate(row["tags"]) if tag=="O"}
            if observed!=actual:
                raise ValueError("不能把未知字符无来源地标为背景 O")
            o_checked+=len(actual)
        if o_checked!=item["observed_O_count"]:
            raise ValueError("背景字符计数与独立 GT 不一致")
    by_field=Counter()
    background=Counter()
    for item in dataset:
        by_field.update(item["positive_by_field"])
        background.update(item["background_by_type"])
    return {
        "sources":len(dataset),
        "lines":sum(len(item["lines"]) for item in dataset),
        "total_characters":n_chars,
        "known_characters":known,
        "known_positive_characters":known_positive,
        "unknown_characters":n_chars-known,
        "supervised_character_fraction":round(known/n_chars,6),
        "positive_supervised_character_fraction":round(known_positive/n_chars,6),
        "known_positive_spans":sum(by_field.values()),
        "positive_spans_by_field":{field:by_field[field] for field in FIELD_TAGS},
        "observed_O_count":o_total,
        "verified_background_span_count":sum(item["verified_background_span_count"] for item in dataset),
        "background_by_type":{field:background[field] for field in _CONTACT_FIELDS},
        "abstained_ambiguous_contact_spans":sum(item["abstained_ambiguous_contact_spans"] for item in dataset),
        "abstained_missing_contact_spans":sum(item["abstained_missing_contact_spans"] for item in dataset),
        "abstained_invalid_contact_fields":sum(item["abstained_invalid_contact_fields"] for item in dataset),
        "abstained_conflicting_contact_spans":sum(item["abstained_conflicting_contact_spans"] for item in dataset),
        "background_provenance":"independent_GT_contact_only",
        "negative_background_labels_created":0,
        "standard_supervised_BIO_ready":False,
        "fully_labeled_lines":sum(item["fully_labeled_lines"] for item in dataset),
        "background_identifiability":"contact_only_partial" if o_total else "not_established",
        "trained_model":False,
        "production_integrated":False,
        "note":"Unknown positions are masked; no complete O labels or job-semantic validation supplied.",
    }
