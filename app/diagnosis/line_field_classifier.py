"""Small GT-supervised native PDF text-line classifier (research only).

Only uniquely aligned *positive* annotations from an independent dataset can
be used to fit the 3-way contrastive classifier (role/employer/school). A line
that is unknown to GT is NEVER interpreted as a negative. Text lines that
are ambiguously aligned to multiple classes or duplicate GT annotations are
excluded from fitting. The resulting softmax scores are ranking utilities,
NOT probability of occupation/employment and are NOT calibrated.

The inference API only accepts PDF bytes plus this research model. No
annotations, personal identifiers, hiring outcomes, or applicant scores.
No model is serialized and nothing is connected to the production parser.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import math
import re

import numpy as np

from .annotation_alignment import align_independent_annotations, _native_lines

FIELD_CLASSES = ("work_role", "employer", "school")
_HASH_DIM = 768
_NUMERIC_DIM = 13
_TOTAL_DIM = _HASH_DIM + _NUMERIC_DIM
_EPOCHS = 420
_RATE = 0.38
_REG = 0.018

# This safety screen only rejects obvious personal contacts/links or section
# headings; it does NOT rely on a role/org vocabulary from the failed rule
# baseline, nor on any reference labels.
_UNSAFE = re.compile(
    r"@|https?://|www\.|(?<!\d)1[3-9]\d{9}(?!\d)|"
    r"(?<!\w)(?:phone|tel|email|mobile)\s*[:：]", re.I
)
_SECTION_HEADING = re.compile(
    r"^(?:工作经历|工作经验|实习经历|教育背景|教育经历|个人简介|"
    r"工作经历Work Experience|项目经历|项目经验|技能|证书|"
    r"Work\s*Experience|Internship\s*Experience|Education|"
    r"Projects|Skills|Professional\s*Summary|Certifications)$", re.I
)


def _line_features(line: dict) -> np.ndarray:
    """Deterministic hashing of character n-grams and PDF geometry.

    All features are derived from the original source line, before any GT
    is consulted. Personal names can be transiently hashed in memory, but
    the feature vectors are never saved or printed as artifacts.
    """
    source = line["source_line"]
    text = re.sub(r"[\W_]+", "", source, flags=re.UNICODE).casefold()
    v = np.zeros(_TOTAL_DIM, dtype=np.float64)
    seen = set()
    for width in (2, 3, 4):
        for start in range(max(0, len(text)-width+1)):
            token = f"{width}:{text[start:start+width]}".encode("utf-8")
            digest = hashlib.blake2b(token, digest_size=8).digest()
            pos = int.from_bytes(digest[:4], "little") % _HASH_DIM
            # Presence, not TF: duplicating a word cannot multiply its value.
            seen.add(pos)
    for pos in seen:
        v[pos] = 1.0
    if seen:
        v[:_HASH_DIM] /= math.sqrt(len(seen))
    box = line["line_bbox"]
    chars = max(1, len(source))
    cjk_count = sum("\u4e00" <= c <= "\u9fff" for c in source)
    digit_count = sum(c.isdigit() for c in source)
    ascii_letter_count = sum(c.isascii() and c.isalpha() for c in source)
    numeric = [
        float(box[0]), float(box[1]), float(box[2]), float(box[3]),
        min(1.0, box[2]-box[0]), min(1.0, box[3]-box[1]),
        min(1.0, chars/85),
        cjk_count/chars,
        ascii_letter_count/chars,
        digit_count/chars,
        float(bool(re.search(r"(?:19|20)\d{2}", source))),
        float(bool(re.search(r"[:：|｜丨]", source))),
        float(bool(re.match(r"^\s*[-•*]\s+", source))),
    ]
    v[_HASH_DIM:] = numeric
    return v


def build_verified_line_labels(
    pdf_bytes: bytes, annotation: dict, *,
    source_id: int, forbidden_ids: tuple[int, ...],
) -> dict:
    """Construct positive-only, exclusively annotated supervised labels.

    Each selected line has an independent GT anchor for exactly one of the
    three field classes. Other *annotated* classes act as contrastive classes
    in fitting; all unannotated lines remain unknown.
    """
    if source_id in set(forbidden_ids):
        raise ValueError("保留测试集不能生成训练标签")
    aligned = align_independent_annotations(pdf_bytes, annotation)
    anchors = aligned["unique_anchors"]
    duplicates = Counter(
        (a["page_index"], tuple(a["line_bbox"])) for a in anchors
    )
    rows = []
    ambiguous = 0
    for a in anchors:
        key = (a["page_index"], tuple(a["line_bbox"]))
        if duplicates[key] != 1:
            ambiguous += 1
            continue
        if a["field"] not in FIELD_CLASSES:
            continue
        features = _line_features(a)
        rows.append({
            "source_id": source_id,
            "label": a["field"],
            "features": features.tolist(),
            "label_source": "independent_unique_GT_anchor",
            "background_assumption": "unknown_unlabeled_not_negative",
        })
    counts=Counter(row["label"] for row in rows)
    return {
        "source_id": source_id,
        "rows": rows,
        "class_counts": {name: counts[name] for name in FIELD_CLASSES},
        "ambiguous_gt_line_count": ambiguous,
        "unknown_unlabeled_lines": max(
            0,aligned["native_line_count"]-len(rows)
        ),
        "negative_background_labels_created": 0,
        "note": "Labels distinguish only positive GT types; no background negatives.",
    }


def fit_line_field_model(
    bundles: list[dict], *, allowed_train_ids: tuple[int, ...],
) -> dict:
    """Deterministic full-batch multinomial fit using CPU NumPy.

    Model weights and labels are ephemeral. No filesystem, network, or GPU.
    Hyperparameters are frozen in code before testing unseen PDFs.
    """
    permitted=set(allowed_train_ids)
    seen_source=set()
    features=[]
    targets=[]
    for bundle in bundles:
        source_id=bundle["source_id"]
        if source_id not in permitted:
            raise ValueError("训练候选池之外的数据不得用于拟合")
        if source_id in seen_source:
            raise ValueError("同一 PDF 不得重复计为不同训练来源")
        seen_source.add(source_id)
        if bundle.get("negative_background_labels_created",0)!=0:
            raise ValueError("未经 GT 标注的文字行不能视为负样本")
        for sample in bundle["rows"]:
            if sample["source_id"]!=source_id or sample.get("label_source")!="independent_unique_GT_anchor":
                raise ValueError("仅使用来自独立 GT 唯一文字行的正向标注")
            if sample.get("label") not in FIELD_CLASSES:
                raise ValueError("字段类别不在固定 schema 内")
            vector=np.asarray(sample["features"],dtype=np.float64)
            if (vector.shape!=(_TOTAL_DIM,) or
                not np.all(np.isfinite(vector)) or
                np.max(np.abs(vector)) > 1.01):
                raise ValueError("训练特征格式无效")
            features.append(vector)
            targets.append(FIELD_CLASSES.index(sample["label"]))
    if len(features)<6 or len(set(targets))<2 or len(seen_source)<2:
        raise ValueError("独立 GT 字段证据不足以训练行分类器")

    X=np.stack(features)
    y=np.asarray(targets,dtype=np.int64)
    n,dim=X.shape
    k=len(FIELD_CLASSES)
    W=np.zeros((dim,k),dtype=np.float64)
    b=np.zeros(k,dtype=np.float64)
    eye=np.eye(k,dtype=np.float64)
    Y=eye[y]
    # Equalize GT category contributions, rather than relying on arbitrary
    # class proportions from the synthetic data generator.
    class_sizes=np.bincount(y,minlength=k)
    weights=np.asarray([1/max(1,class_sizes[v]) for v in y])
    weights/=sum(weights)
    for _ in range(_EPOCHS):
        logits=X@W+b
        logits-=np.max(logits,axis=1,keepdims=True)
        p=np.exp(logits)
        p/=np.sum(p,axis=1,keepdims=True)
        error=(p-Y)*weights[:,None]
        dW=X.T@error+_REG*W
        db=np.sum(error,axis=0)
        W-=_RATE*dW
        b-=_RATE*db
    return {
        "class_names":list(FIELD_CLASSES),
        "feature_dim":_TOTAL_DIM,
        "weights":W.tolist(),
        "bias":b.tolist(),
        "train_sources":len(seen_source),
        "supervised_line_count":n,
        "hyperparameters":{
            "epochs":_EPOCHS, "rate":_RATE, "regularization":_REG,
            "hash_dim":_HASH_DIM,
        },
        "trained_on_unknown_lines":False,
        "trained_on_hiring_outcomes":False,
        "trained_only_on_independent_GT_anchors":True,
        "calibrated":False,
        "deployed":False,
    }


def propose_line_fields(
    pdf_bytes: bytes, model: dict, *, per_field: int = 6,
) -> list[dict]:
    """GT-blind top-K review proposals for each field with provenance.

    No user-facing probabilistic claims; 'ranking_score' merely orders rows.
    All rows remain unverified and are not fed to PaperPro Resume or scoring.
    """
    if not 1<=per_field<=40:
        raise ValueError("每类候选限额应为 1–40")
    if model.get("class_names")!=list(FIELD_CLASSES) or model.get("deployed") is not False:
        raise ValueError("只能使用未部署的固定类型研究模型")
    if not (isinstance(pdf_bytes,(bytes,bytearray))
            and pdf_bytes.startswith(b"%PDF-")
            and len(pdf_bytes)<=10*1024*1024):
        raise ValueError("需要 10 MB 内的有效 PDF")
    lines=[
        row for row in _native_lines(pdf_bytes)
        if 2<=len(row["source_line"])<=185
        and not _UNSAFE.search(row["source_line"])
        and not _SECTION_HEADING.fullmatch(row["source_line"].strip())
    ]
    if not lines:
        return []
    X=np.stack([_line_features(line) for line in lines])
    W=np.asarray(model["weights"],dtype=np.float64)
    b=np.asarray(model["bias"],dtype=np.float64)
    if W.shape!=(_TOTAL_DIM,len(FIELD_CLASSES)) or b.shape!=(len(FIELD_CLASSES),):
        raise ValueError("模型特征或类别维度不一致")
    logits=X@W+b
    logits-=np.max(logits,axis=1,keepdims=True)
    exp=np.exp(logits)
    ranking=exp/np.sum(exp,axis=1,keepdims=True)
    result=[]
    for field in ("work_role","employer"):
        k=FIELD_CLASSES.index(field)
        rank=sorted(range(len(lines)),key=lambda i:(-ranking[i,k],i))
        for pos,i in enumerate(rank[:per_field],1):
            line=lines[i]
            result.append({
                "field":field,
                "page_index":line["page_index"],
                "line_bbox":line["line_bbox"],
                "source_line":line["source_line"],
                "source_kind":"native_pdf_text",
                "ranking_position":pos,
                "ranking_score":round(float(ranking[i,k]),6),
                "ranking_score_is_probability":False,
                "status":"unverified",
                "confidence":{"tier":"low","calibrated":False},
                "ready_for_training":False,
                "automatic_resume_mutation":False,
            })
    return result
