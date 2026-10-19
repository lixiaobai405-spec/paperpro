from pathlib import Path

import pymupdf
from docx import Document

from app.exporter import make_docx, make_pdf
from app.models import Education, Entry, Resume


def test_visual_template_fixture():
    example = Resume(
        name="陈晓明",
        title="后端开发工程师",
        email="demo@example.com",
        phone="138 0000 0000",
        location="深圳",
        summary="具备3年后端服务开发经验，熟悉Python和关系型数据库。注重系统可靠性、清晰的代码结构与团队协作。",
        skills=["Python", "FastAPI", "MySQL", "Redis", "Docker", "Git", "Linux"],
        experience=[
            Entry(heading="2022.07—2025.06  星辰科技 | 后端开发工程师", bullets=[
                "参与订单管理系统开发与接口联调，提升核心接口响应效率20%",
                "维护业务数据库与自动化测试，支持新功能稳定上线",
                "根据代码审查反馈持续改进模块结构与异常处理",
            ]),
            Entry(heading="2021.07—2021.12  示范软件 | 开发实习生", bullets=[
                "参与内部管理工具开发，完成需求拆分与接口测试",
            ]),
        ],
        education=[Education(heading="2018.09—2022.06 华南理工大学 | 计算机科学与技术 学士")],
        projects=[Entry(heading="订单数据分析平台  |  Python / SQL", bullets=[
            "实现订单清洗与数据统计模块，为业务分析提供可复用接口",
            "编写单元测试并参与上线验证，记录关键异常场景",
        ])],
        additional=["英语 CET-6", "熟悉 Git 版本管理及协作开发流程"],
    )
    docx = make_docx(example)
    pdf = make_pdf(example, docx)
    page_doc = Document(__import__("io").BytesIO(docx))
    assert 209 < page_doc.sections[0].page_width.mm < 211
    assert 296 < page_doc.sections[0].page_height.mm < 298

    rendered = pymupdf.open(stream=pdf, filetype="pdf")
    assert len(rendered) == 1, f"Expected 1-page sample, got {len(rendered)}"
    page = rendered[0]
    text = page.get_text()
    for word in ("陈晓明", "星辰科技", "华南理工大学", "20%", "订单数据分析平台"):
        assert word in text, f"Missing template evidence: {word}"
    assert abs(page.rect.width - 595.3) < 1
    assert abs(page.rect.height - 841.9) < 1
    for box in page.get_text("blocks"):
        assert box[0] >= 0 and box[1] >= 0
        assert box[2] <= page.rect.width + 1 and box[3] <= page.rect.height + 1

    output = Path(__file__).resolve().parents[1] / "artifacts" / "visual"
    output.mkdir(parents=True, exist_ok=True)
    (output / "paperpro_smoke.docx").write_bytes(docx)
    (output / "paperpro_smoke.pdf").write_bytes(pdf)
    image = page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False)
    image.save(str(output / "paperpro_smoke.png"))
