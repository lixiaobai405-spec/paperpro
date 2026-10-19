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

from .annotation_alignment import _native_lines
from .span_supervision import align_gt_char_spans

FIELD_TAGS = {
    "work_role": "WORK_ROLE",
    "employer": "EMPLOYER",
    "school": "SCHOOL",
}
BIO_TAGS = ("O",) + tuple(
    tag for field in FIELD_TAGS.values()
    for tag in (f"B-{field}", f"I-{field}")
)


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

    known=sum(sum(line["observed_mask"]) for line in records)
    n_chars=sum(len(line["tags"]) for line in records)
    if n_chars<known:
        raise AssertionError("Observed characters exceed all PDF text")
    fully=sum(bool(line["tags"]) and all(line["observed_mask"]) for line in records)

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
        "unknown_characters":n_chars-known,
        "observed_O_count":0,
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
    n_chars=sum(item["total_characters"] for item in dataset)
    if not n_chars or any(item["observed_O_count"]!=0 for item in dataset):
        raise ValueError("数据缺少源文字或含有未经审核的背景负例")
    by_field=Counter()
    for item in dataset:
        by_field.update(item["positive_by_field"])
    return {
        "sources":len(dataset),
        "lines":sum(len(item["lines"]) for item in dataset),
        "total_characters":n_chars,
        "known_positive_characters":known,
        "unknown_characters":n_chars-known,
        "supervised_character_fraction":round(known/n_chars,6),
        "known_positive_spans":sum(by_field.values()),
        "positive_spans_by_field":{field:by_field[field] for field in FIELD_TAGS},
        "observed_O_count":0,
        "negative_background_labels_created":0,
        "standard_supervised_BIO_ready":False,
        "fully_labeled_lines":sum(item["fully_labeled_lines"] for item in dataset),
        "background_identifiability":"not_established",
        "trained_model":False,
        "production_integrated":False,
        "note":"Unknown positions are masked; no complete O labels or job-semantic validation supplied.",
    }
