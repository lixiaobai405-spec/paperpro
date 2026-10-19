"""GT-blind candidate discovery from native PDF text lines.

EXPERIMENTAL ONLY. The function accepts only PDF bytes, not annotations,
job descriptions, or a trained model. It proposes *lines worth reviewing*;
it does not label someone's occupation, employment dates, or qualifications.
Candidate text stays in process memory and is never printed by CLI reports.

Unknown/unselected lines are NOT negative examples. Neither a candidate's
presence nor structural priority is a calibrated classification probability.
"""
from __future__ import annotations

import re

from .annotation_alignment import _native_lines

CJK_ROLE_TERM = re.compile(
    r"(?:工程师|开发人员|开发工程|经理|总监|主管|设计师|分析师|专员|"
    r"助理|技术支持|产品运营|市场运营|用户运营|平台运营|业务分析|"
    r"数据分析|运维|架构师|研究员|研究助理|顾问|会计|财务|法务|"
    r"行政|销售|编辑|教师|实习生|助教|测试|策划|客服|主任|"
    r"项目管理|人事|HRBP|产品负责人)"
)
LATIN_ROLE_TERM = re.compile(
    r"\b(?:engineer|developer|analyst|designer|manager|specialist|"
    r"consultant|director|intern|researcher|scientist|"
    r"administrator|accountant|architect|recruiter|assistant|"
    r"product\s+owner|technician|coordinator)\b", re.I
)
ORG_TERM = re.compile(
    r"(?:股份有限公司|有限责任公司|有限公司|股份公司|科技公司|"
    r"公司|集团|研究院|研究所|事务所|工作室|"
    r"实验室|医院|银行|基金会|"
    r"Corp\.?|Corporation|Inc\.?|LLC|Ltd\.?|Group|Labs|"
    r"Technologies|Technology|Systems|Bank)",re.I,
)
# Remove this class of résumé prose instead of declaring all unlabelled
# content to be a negative training sample.
PROSE_START = re.compile(
    r"^\s*(?:[-*•●▪◦·]\s*|(?:1|2|3)[、.]\s*|负责|参与|协助|实现|"
    r"优化|提升|开发了|设计了|完成了|掌握|熟练|熟悉|使用|通过|"
    r"期间|例如|主要工作|工作内容|职位描述|职责|描述|求职意向|"
    r"Summary\s*:|Responsibilities\s*:|Worked\s+on\b|"
    r"Responsible\s+for\b|Developed\s+|Improved\s+)", re.I,
)
CONTACT = re.compile(
    r"@|https?://|www\.|\b(?:tel|phone|mobile|email)\s*:|"
    r"(?<!\d)1[3-9]\d{9}(?!\d)|\b\d{5,}\b",re.I,
)
SECTION_TITLE = re.compile(
    r"^(?:工作经历|工作经验|实习经历|教育背景|教育经历|"
    r"项目经历|技能|证书|自我评价|个人简介|"
    r"Work\s*Experience|Internship\s*Experience|"
    r"Education|Projects|Skills|Certifications|"
    r"Professional\s*Summary)$",re.I
)


def _field_hints(text: str) -> tuple[str,...]:
    value = text.strip()
    # Date/role/employer rows are typically short (< one visible line).
    if not 2 <= len(value) <= 95:
        return ()
    if CONTACT.search(value) or PROSE_START.search(value) or SECTION_TITLE.fullmatch(value):
        return ()
    if re.fullmatch(r"[\d\s,.-]+",value):
        return ()

    fields=[]
    # School names are intentionally not company signals without an
    # independent business-entity suffix.
    if ORG_TERM.search(value) and not (
        re.search(r"大学|学院|中学|小学|University|College|School",value,re.I)
        and not re.search(r"公司|集团|Inc\.?|LLC|Ltd\.?",value,re.I)
    ):
        fields.append("employer")

    # A line with only a company can contain generic words "技术支持",
    # but literal "公司" without an independent role term is not a role.
    contains_role = bool(CJK_ROLE_TERM.search(value) or LATIN_ROLE_TERM.search(value))
    if contains_role:
        fields.append("work_role")
    return tuple(fields)


def propose_pdf_field_lines(
    pdf_bytes: bytes, *, max_candidates_per_field: int = 40,
) -> list[dict]:
    """GT-independent, source-anchored low-certainty role/employer *lines*.

    All candidates point to original native text-line boxes. No text is
    rewritten; the literal line can contain multiple semantic fields and
    cannot become a confirmed company/role by itself.
    """
    if not (1 <= max_candidates_per_field <= 200):
        raise ValueError("每个字段的候选上限必须在 1–200")
    if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes)>10*1024*1024:
        raise ValueError("需要有效的、大小不超过 10 MB 的 PDF")
    counts={"employer":0,"work_role":0}
    proposals=[]
    for line in _native_lines(pdf_bytes):
        text=line["source_line"]
        for field in _field_hints(text):
            if counts[field]>=max_candidates_per_field:
                continue
            counts[field]+=1
            proposals.append({
                "field":field,
                "source_kind":"native_pdf_text",
                "page_index":line["page_index"],
                "line_bbox":line["line_bbox"],
                "source_line":text,
                "status":"unverified",
                "confidence":{"tier":"low","calibrated":False},
                "automatic_resume_mutation":False,
                "ready_for_training":False,
            })
    return proposals
