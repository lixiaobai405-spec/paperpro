"""Experimental positive-only field CHAR-SPAN proposer for native PDFs.

Fits source-separated field-specific character endings / n-gram frequencies
from independently annotated positive span examples; NO unknown text is
assumed negative. GT is NOT passed to inference. Proposals are unverified,
have literal character offsets and MUST NOT be put into production scoring.

This is a bounded lexical prototype, not a CRF/LLM, employer verifier or
calibrated probability. It is not serialized or connected to app.main.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re

from .annotation_alignment import _native_lines
from .span_supervision import _normalized_chars
from .line_field_classifier import _UNSAFE, _SECTION_HEADING
from .adapter import DATE_RANGE

FIELDS = ("work_role", "employer")
_DELIMITERS = re.compile(r"[^|丨｜,，;；:：\t]+")
_WORDS = re.compile(r"\S+")
_ALLOWED = re.compile(r"[\u4e00-\u9fffA-Za-z]")
_DATE_PREFIX = re.compile(r"^\s*(?:19|20)\d{2}[\d./年\-—–\s至到月]{3,22}")
_MAX_LINE_CHARS = 180
_MAX_PROPOSALS_PER_FIELD = 40


def _plain(value: str) -> str:
    return _normalized_chars(value)[0]


def _suffixes(value: str) -> tuple[str, ...]:
    text = _plain(value)
    return tuple(text[-n:] for n in (2, 3, 4) if len(text) >= n)


def _ngrams(value: str) -> set[str]:
    text = _plain(value)
    return {
        text[pos:pos+n] for n in (2,3)
        for pos in range(max(0,len(text)-n+1))
    }


def fit_positive_span_proposer(
    bundles: list[dict], *, allowed_source_ids: tuple[int, ...],
    forbidden_source_ids: tuple[int, ...],
) -> dict:
    """Estimate lexical field evidence from positive GT anchors only.

    Contrasts derive from *other positively annotated classes*, not a
    fabricated background category. Known unknowns are always abstentions.
    """
    permitted=set(allowed_source_ids)
    forbidden=set(forbidden_source_ids)
    suffix_by_field={f:defaultdict(set) for f in FIELDS}
    grams_by_field={f:defaultdict(set) for f in FIELDS}
    lengths={f:[] for f in FIELDS}
    sources=set()
    count=Counter()
    literals={field:[] for field in FIELDS}

    if not bundles:
        raise ValueError("训练数据为空")
    for bundle in bundles:
        source_id=bundle["source_id"]
        if source_id in forbidden:
            raise ValueError("保留测试集不得进入训练")
        if source_id not in permitted or source_id in sources:
            raise ValueError("训练来源不在预定训练集合中或重复")
        sources.add(source_id)
        if bundle.get("unlabeled_character_negatives_created",0):
            raise ValueError("不能把未标注文字当成负样本")
        for span in bundle["positive_spans"]:
            if span.get("label_source")!="independent_gt":
                raise ValueError("仅允许独立 GT 正向字符区间标注")
            field=span["field"]
            if field not in FIELDS:
                continue
            source_text=span["source_line"]
            start,end=span["start_char"],span["end_char"]
            if (not isinstance(start,int) or not isinstance(end,int)
                or not 0<=start<end<=len(source_text)):
                raise ValueError("监督字符区间无效")
            literal=source_text[start:end]
            # Independently annotated text must itself be the literal
            # selected substring; no PII, score or inferred edits accepted.
            if not literal.strip() or len(literal)>85:
                continue
            lengths[field].append(len(_plain(literal)))
            literals[field].append(literal)
            count[field]+=1
            for suffix in _suffixes(literal):
                suffix_by_field[field][suffix].add(source_id)
            for gram in _ngrams(literal):
                grams_by_field[field][gram].add(source_id)
    if len(sources)<2 or min(count[f] for f in FIELDS)<2:
        raise ValueError("职位与公司均须有两个以上独立正向标注")

    model={
        "field_suffixes":{
            field:{token:len(ids) for token,ids in data.items()}
            for field,data in suffix_by_field.items()
        },
        "field_ngrams":{
            field:{token:len(ids) for token,ids in data.items()}
            for field,data in grams_by_field.items()
        },
        "field_lengths":{
            field:{
                "median":sorted(lengths[field])[len(lengths[field])//2],
                "maximum":max(lengths[field]),
            } for field in FIELDS
        },
        "training_source_count":len(sources),
        "positive_examples_by_field":dict(count),
        "trained_on_unknown_characters":False,
        "trained_on_independent_gt_only":True,
        "calibrated":False,
        "deployed":False,
    }
    # A fixed 10th-percentile positive-only acceptance threshold. It only
    # uses independently annotated TRAIN spans, never dev or holdout GT.
    qualities={}
    for field in FIELDS:
        values=sorted(_quality(model,field,item) for item in literals[field])
        qualities[field]=values[int((len(values)-1)*.10)]
    model["minimum_quality"] = qualities
    model["threshold_from_train_only"]=True
    return model


def _span_candidates(text: str, endings: set[str]) -> list[tuple[int,int]]:
    """GT-blind boundary hypotheses in ONE native-PDF source line.

    The candidate set deliberately includes punctuation-delimited chunks,
    contiguous whitespace-token groups, and segments cut at learned
    positive-field suffixes. It never returns edited character strings.
    """
    if not 2<=len(text)<=_MAX_LINE_CHARS:
        return []
    points=set()
    def add(start:int,end:int):
        while start<end and text[start].isspace():
            start+=1
        while end>start and text[end-1].isspace():
            end-=1
        if not 2<=end-start<=85 or not _ALLOWED.search(text[start:end]):
            return
        if _UNSAFE.search(text[start:end]) or _SECTION_HEADING.fullmatch(text[start:end]):
            return
        if re.fullmatch(r"[\d./\s年月\-—–至到]+",text[start:end]):
            return
        points.add((start,end))

    for match in _DELIMITERS.finditer(text):
        start,end=match.span()
        if not text[start:end].strip():
            continue
        # Remove a date RANGE only when it starts near the front of a
        # segment, not when digits in the field are meaningful.
        date=DATE_RANGE.search(text[start:end])
        if date and date.start()<=3:
            start=start+date.end()
        elif start==match.start():
            prefix=_DATE_PREFIX.match(text[start:end])
            if prefix and prefix.end()<end-start:
                start+=prefix.end()
        add(start,end)

        # Sliding full-token groups (up to four words) handle English
        # multiword roles / organizations without forcing a GT string.
        tokens=list(_WORDS.finditer(text,start,end))
        for i in range(len(tokens)):
            for n in range(1,5):
                if i+n>len(tokens):
                    break
                add(tokens[i].start(),tokens[i+n-1].end())

        # A line can also contain two CJK fields without punctuation;
        # use only endings learned on training positives to split them.
        sub=text[start:end]
        simple,_=_normalized_chars(sub)
        if not simple or len(simple)>120:
            continue
        for ending in endings:
            if len(ending)<2:
                continue
            idx=simple.find(ending)
            if idx<0 or idx>90:
                continue
            # Map normalized indices back to source characters.
            _,offsets=_normalized_chars(sub)
            tail=offsets[idx+len(ending)-1]+1
            if 2<=tail<len(sub):
                add(start,start+tail)
                add(start+tail,end)
    return sorted(points)


def _quality(model:dict,field:str,candidate:str) -> float:
    text=_plain(candidate)
    if len(text)<2:
        return -1e9
    suffix=model["field_suffixes"][field]
    rival=model["field_suffixes"][
        "employer" if field=="work_role" else "work_role"
    ]
    hits=[(len(token),count) for token,count in suffix.items()
          if text.endswith(token)]
    if not hits:
        return -1e8  # No trained ending evidence → abstain for this field.
    other=max((math.log1p(count) for token,count in rival.items()
               if text.endswith(token)),default=0.0)
    endings=max((math.log1p(count)+.10*size for size,count in hits))
    grams=model["field_ngrams"][field]
    other_grams=model["field_ngrams"][
        "employer" if field=="work_role" else "work_role"
    ]
    ngram_set=_ngrams(candidate)
    own=sum(min(3,grams.get(g,0)) for g in ngram_set)
    cross=sum(min(3,other_grams.get(g,0)) for g in ngram_set)
    lexical=(own-.45*cross)/max(2,len(ngram_set))
    expected=model["field_lengths"][field]["median"]
    penalty=abs(len(text)-expected)/max(4,expected)
    return round(2.5*endings-other*1.7+.8*lexical-.8*penalty,7)


def propose_pdf_char_spans(
    pdf_bytes: bytes, model:dict, *, per_field:int=8,
) -> list[dict]:
    """Source-provenanced top-K substring suggestions, NO ground truth."""
    if not 1<=per_field<=_MAX_PROPOSALS_PER_FIELD:
        raise ValueError("候选数量必须在 1–40")
    if model.get("deployed") is not False or model.get("calibrated") is not False:
        raise ValueError("只允许未部署、未校准的实验模型")
    if set(model.get("field_suffixes",{}))!=set(FIELDS):
        raise ValueError("候选模型类别或数据无效")
    if not isinstance(pdf_bytes,(bytes,bytearray)) or (
        not pdf_bytes.startswith(b"%PDF-")
        or len(pdf_bytes)>10*1024*1024
    ):
        raise ValueError("需要有效的 10 MB 内 PDF")
    endings=set().union(*(
        set(model["field_suffixes"][f]) for f in FIELDS
    ))
    candidates={field:[] for field in FIELDS}
    for line in _native_lines(bytes(pdf_bytes)):
        text=line["source_line"]
        if _UNSAFE.search(text) or _SECTION_HEADING.fullmatch(text.strip()):
            continue
        for start,end in _span_candidates(text,endings):
            literal=text[start:end]
            for field in FIELDS:
                value=_quality(model,field,literal)
                if value<=-1e7 or value<model["minimum_quality"][field]:
                    continue
                candidates[field].append((value,{
                    "field":field,
                    "source_line":text,
                    "start_char":start,"end_char":end,
                    "proposed_text":literal,
                    "page_index":line["page_index"],
                    "line_bbox":line["line_bbox"],
                    "source_kind":"native_pdf_text",
                    "status":"unverified",
                    "confidence":{"tier":"low","calibrated":False},
                    "ranking_score":value,
                    "ranking_score_is_probability":False,
                    "automatic_resume_mutation":False,
                    "ready_for_training":False,
                }))
    result=[]
    for field in FIELDS:
        ranked=sorted(candidates[field],key=lambda row:(-row[0],
                     row[1]["page_index"],row[1]["line_bbox"][1],
                     row[1]["start_char"]))
        seen=set()
        for value,item in ranked:
            key=(item["page_index"],tuple(item["line_bbox"]),
                 item["start_char"],item["end_char"])
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
            if sum(r["field"]==field for r in result)>=per_field:
                break
    return result
