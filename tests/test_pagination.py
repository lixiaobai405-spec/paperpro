from io import BytesIO
import re

import pymupdf
from docx import Document

from app.exporter import make_docx, make_pdf
from app.models import Entry, Resume


def test_long_resume_spills_to_next_a4_page_without_losing_last_bullet():
    bullets = [
        f"第{i:03d}条履历：设计并验证具体业务流程，保留本条的唯一编号，并记录测试结果。"
        for i in range(1, 60)
    ]
    resume = Resume(
        name="长文档候选人",
        summary="完整保留跨页履历",
        experience=[Entry(heading="2022 - 2026 测试公司 | 工程师", bullets=bullets)],
    )
    docx = make_docx(resume)
    document = Document(BytesIO(docx))
    assert document.sections[0].page_width.mm >= 209
    assert "第059条" in "\n".join(p.text for p in document.paragraphs)
    pdf = pymupdf.open(stream=make_pdf(resume, docx), filetype="pdf")
    assert len(pdf) >= 2
    text = "\n".join(page.get_text() for page in pdf)
    assert re.search(r"第001\s*条", text)
    assert re.search(r"第059\s*条", text)
    assert all(abs(page.rect.width - 595.3) < 1 for page in pdf)
