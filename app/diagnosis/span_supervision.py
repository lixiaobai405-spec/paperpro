"""Independent-GT → native PDF text character-span alignment.

Research data interface ONLY. A GT "companyName" and "position" appearing in
one native PDF line are two *different substrings*, not contradictory line
classes. Matching is textual, not a job-semantic check. Every original line
remains reviewable and no inferred field is written into PaperPro.

No unannotated characters or lines receive negative labels. All positive
spans are unapproved for training until a separate relationship/provenance
gate decides whether their GT association is trustworthy.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .annotation_alignment import (
    FIELD_NAMES, _independent_fields, _native_lines
)


def _normalized_chars(source: str) -> tuple[str,list[int]]:
    """Normalized case-insensitive searchable text with original offsets."""
    buf=[]
    offsets=[]
    for original_index,char in enumerate(source):
        if char=="_":
            continue
        for folded in char.casefold():
            if folded.isalnum():
                buf.append(folded)
                offsets.append(original_index)
    return "".join(buf),offsets


def _substring_occurrences(source: str, target: str) -> list[tuple[int,int]]:
    line,index_map=_normalized_chars(source)
    normalized,_=_normalized_chars(target)
    if not normalized:
        return []
    hits=[]
    offset=0
    while offset<len(line):
        position=line.find(normalized,offset)
        if position<0:
            break
        start=index_map[position]
        end=index_map[position+len(normalized)-1]+1
        hits.append((start,end))
        offset=position+1
    return hits


def align_gt_char_spans(pdf_bytes: bytes, annotation: dict) -> dict:
    """Conservatively locate each independent GT field in one PDF line.

    Same-line distinct spans are preserved. Repeated GT text across lines,
    repeated substring occurrences in the same line, or overlapping GT
    labels are ambiguous and never emitted as supervised examples.
    """
    source_lines=_native_lines(pdf_bytes)
    per_field=defaultdict(lambda:{
        "expected":0,"found":0,"ambiguous":0,
        "missing":0,"overlapping_rejected":0,
    })
    candidates=[]
    for field,ref,expected in _independent_fields(annotation):
        if field not in FIELD_NAMES:
            continue
        per_field[field]["expected"]+=1
        hits=[]
        for line in source_lines:
            for start,end in _substring_occurrences(line["source_line"],expected):
                hits.append({
                    "field":field,
                    "annotation_ref":ref,
                    "annotation_text":expected,
                    "page_index":line["page_index"],
                    "line_bbox":line["line_bbox"],
                    "source_line":line["source_line"],
                    "start_char":start,
                    "end_char":end,
                    "label_source":"independent_gt",
                    "ready_for_training":False,
                })
        if len(hits)==1:
            candidates.append(hits[0])
        elif len(hits)>1:
            per_field[field]["ambiguous"]+=1
        else:
            per_field[field]["missing"]+=1

    # Detect duplicate annotations, company strings containing role strings,
    # and other overlapping GT spans. Neither side is silently selected.
    rejected=set()
    for i,a in enumerate(candidates):
        for j in range(i+1,len(candidates)):
            b=candidates[j]
            if (a["page_index"]!=b["page_index"] or
                    tuple(a["line_bbox"])!=tuple(b["line_bbox"])):
                continue
            if max(a["start_char"],b["start_char"])<min(a["end_char"],b["end_char"]):
                rejected.add(i)
                rejected.add(j)
    positive=[]
    for i,span in enumerate(candidates):
        if i in rejected:
            per_field[span["field"]]["overlapping_rejected"]+=1
        else:
            per_field[span["field"]]["found"]+=1
            positive.append(span)
    span_per_line=Counter(
        (span["page_index"],tuple(span["line_bbox"]))
        for span in positive
    )
    return {
        "source_kind":"public_synthetic_independent_GT",
        "native_line_count":len(source_lines),
        "positive_spans":positive,
        "field_counts":{key:dict(per_field[key]) for key in FIELD_NAMES},
        "shared_native_line_positive_spans":sum(
            count for count in span_per_line.values() if count>1
        ),
        "overlapping_span_occurrences":len(rejected),
        "unlabeled_character_negatives_created":0,
        "training_examples_emitted":0,
        "labels_are_hiring_outcomes":False,
    }
