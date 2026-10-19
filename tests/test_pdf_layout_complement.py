"""Two-view, provenance-preserving PDF layout complement regression.

Only missing identity/education fields may be enriched from geometrically
separated native PDF columns. Work history and source hashes are immutable.
"""
from __future__ import annotations
from hashlib import sha256

import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.parser import extract_file, parse_resume

client=TestClient(app,raise_server_exceptions=False)


def make_two_column_pdf(*, left_name: str = "合成人员甲") -> bytes:
    pdf=pymupdf.open()
    page=pdf.new_page(width=595,height=842)
    font="C:/Windows/Fonts/simhei.ttf"
    page.insert_font(fontname="FixtureCN",fontfile=font)
    # Right column begins above the left candidate identity, so naive
    # y-sorting can treat work experience as an initial heading.
    right=[
        "工作经历",
        "2022.07-2025.06 虚构科技 | 后端开发工程师",
        "负责 SQL 接口开发及 Python 服务维护",
        "参与虚构订单接口联调",
        "项目经历",
        "虚构项目甲",
        "使用 Python 开发服务",
        "虚构项目乙",
        "完成系统联调",
    ]
    left=[
        left_name,
        "联系方式",
        "13800138000",
        "demo@example.invalid",
        "教育背景",
        "2018.09-2022.06 虚构大学 本科学士",
        "专业技能",
        "Python SQL",
        "其他经历",
        "虚构志愿者活动",
    ]
    for index,value in enumerate(right):
        page.insert_text((315,43+27*index),value,fontsize=11,fontname="FixtureCN")
    for index,value in enumerate(left):
        page.insert_text((42,96+27*index),value,fontsize=11,fontname="FixtureCN")
    raw=pdf.tobytes()
    pdf.close()
    return raw


def test_two_column_complement_only_fills_missing_name_and_school():
    content=make_two_column_pdf()
    extracted,_,method=extract_file("columns.pdf",content)
    assert method=="pdf-text"
    # Show this fixture is a real blind spot in the current sort-based parser.
    before=parse_resume(extracted)
    assert before.name != "合成人员甲" or not before.education

    response=client.post("/api/diagnosis/parse",files={
        "file":("columns.pdf",content,"application/pdf"),
    })
    assert response.status_code==200,response.text
    payload=response.json()
    assert payload["sha256"]==sha256(content).hexdigest()
    assert payload["source_text"]==extracted
    draft=payload["resume"]
    assert draft["name"]=="合成人员甲"
    assert any("虚构大学" in e["heading"] for e in draft["education"])
    assert any("多栏" in note for note in payload["warnings"])
    assert any("Python" in text for e in draft["experience"] for text in e["bullets"])
    # Complement has no authority to rewrite job content or fabricate dates.
    previous=parse_resume(extracted)
    assert len(draft["experience"])==len(previous.experience)
    assert [e["heading"] for e in draft["experience"]]==[
        e.heading for e in previous.experience
    ]
    assert all(e["start_date"] and e["end_date"] for e in draft["experience"])


def test_already_parsed_identity_is_not_overwritten_by_layout_hypothesis():
    from app.diagnosis.pdf_layout import conservative_complement

    class FakePage:
        pass

    # Avoid reading an actual PDF for pure semantic test.
    from app.diagnosis.schema import CandidateResume
    from app.models import Education
    source=CandidateResume(
        name="已校对姓名",source_text="已校对姓名\n其他人\n某大学",
        education=[Education(heading="已校对大学")],
    )
    alt=CandidateResume(
        name="其他人",education=[Education(heading="某大学")],
    )
    output,changed=conservative_complement(source,alt,original_text=source.source_text)
    assert output.name=="已校对姓名"
    assert output.education[0].heading=="已校对大学"
    assert changed==[]


def test_unsupported_name_and_education_claims_fail_closed():
    from app.diagnosis.pdf_layout import conservative_complement
    from app.diagnosis.schema import CandidateResume
    from app.models import Education

    missing=CandidateResume(source_text="姓名\n学校未披露\n")
    fabricated=CandidateResume(
        name="姓名",
        education=[Education(heading="虚构大学 | 不在原文中的学历")],
    )
    checked,changes=conservative_complement(
        missing,fabricated,original_text=missing.source_text
    )
    assert checked.name==""
    assert checked.education==[]
    assert changes==[]


def test_single_column_pdf_does_not_trigger_geometry_guess():
    import pymupdf
    from app.diagnosis.pdf_layout import detect_columns, augment_missing_fields_from_pdf
    from app.diagnosis.schema import CandidateResume

    doc=pymupdf.open()
    page=doc.new_page()
    for i in range(9):
        page.insert_text((65,65+i*40),f"Sample line {i} technical role",fontsize=11)
    data=doc.tobytes()
    assert detect_columns(page) is None
    current=CandidateResume(source_text="sample")
    new,changes=augment_missing_fields_from_pdf(current,data,method="pdf-text")
    assert new.model_dump()==current.model_dump()
    assert changes==[]
    doc.close()


def test_ambiguous_identity_rejected_by_layout_complement():
    from app.diagnosis.pdf_layout import conservative_complement
    from app.diagnosis.schema import CandidateResume

    source=CandidateResume(source_text="工作经历\n2023.01-2024.01 项目工程师\n")
    alt=CandidateResume(name="工作经历")
    final,changed=conservative_complement(source,alt,original_text=source.source_text)
    assert final.name==""
    assert changed==[]
