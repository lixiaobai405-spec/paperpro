"""GT-blind PDF WorkBlock region extraction contracts.

No work history is auto-created; a WorkBlock is a spatial candidate only.
The fixture deliberately interleaves columns in native reading order.
"""
from __future__ import annotations

from hashlib import sha256

import pymupdf
import pytest

from app.diagnosis.workblock_regions import propose_pdf_workblocks

FONT="C:/Windows/Fonts/simhei.ttf"


def _make_pdf(*, include_work=True, include_date=True,
              include_project=True, parallel=True, second_work=True):
    pdf=pymupdf.open()
    page=pdf.new_page(width=595,height=842)
    page.insert_font(fontname="WorkFixtureCN",fontfile=FONT)
    def put(x,y,text):
        page.insert_text((x,y),text,fontname="WorkFixtureCN",fontsize=10)
    if parallel:
        # Overlapping vertical positions but independent physical columns.
        put(330,78,"教育背景")
        put(333,124,"2018.09-2022.06")
        put(333,148,"模拟理工学院")
        put(333,175,"数据科学专业")
        put(333,205,"综合评价")
        put(335,235,"2023.01-2023.12 学校社团")
    if include_work:
        put(34,86,"工作经历")
    if include_work and include_date:
        put(36,142,"2021.07-2023.02")
        put(36,167,"合成技术有限公司")
        put(36,191,"平台开发工程师")
        put(46,215,"- 维护 Python 服务")
    if include_work and second_work:
        put(36,259,"2023.03-2024.05")
        put(36,283,"虚构网络有限公司")
        put(36,307,"数据分析师")
        put(46,327,"- 处理团队数据")
    if include_project:
        put(34,376,"项目经历")
        put(36,409,"2023.05-2024.04")
        put(36,434,"虚构项目甲")
        put(36,457,"参与产品开发")
    raw=pdf.tobytes()
    pdf.close()
    return raw


def test_two_column_work_area_never_absorbs_parallel_education_or_project():
    data=_make_pdf()
    before=sha256(data).hexdigest()
    result=propose_pdf_workblocks(data)
    assert result["source_sha256"]==before
    assert result["method"]=="native_pdf_geometry"
    assert result["automatic_resume_mutation"] is False
    assert result["source_sections"]["experience"]>=1
    assert result["layout_pages"][0]["parallel_section_lanes"] is True
    assert len(result["workblocks"])==2
    a,b=result["workblocks"]
    assert a["dates"]=={"start":"2021.07","end":"2023.02"}
    assert b["dates"]=={"start":"2023.03","end":"2024.05"}
    assert "合成技术有限公司" in a["source_text"]
    assert "平台开发工程师" in a["source_text"]
    assert "虚构网络有限公司" in b["source_text"]
    assert "数据分析师" in b["source_text"]
    for block in result["workblocks"]:
        assert block["status"]=="unverified"
        assert block["auto_promote"] is False
        assert block["source_page_index"]==0
        assert all(0<=x<=1 for x in block["bbox"])
        assert block["bbox"][0]<block["bbox"][2]
        assert block["bbox"][1]<block["bbox"][3]
        assert "模拟理工学院" not in block["source_text"]
        assert "学校社团" not in block["source_text"]
        assert "虚构项目甲" not in block["source_text"]
    assert sha256(data).hexdigest()==before


def test_work_heading_without_date_does_not_generate_fictitious_employment():
    result=propose_pdf_workblocks(
        _make_pdf(include_date=False,second_work=False)
    )
    assert result["workblocks"]==[]
    assert result["automatic_resume_mutation"] is False


def test_dates_in_project_or_education_never_become_work_blocks():
    result=propose_pdf_workblocks(
        _make_pdf(include_work=False,second_work=False)
    )
    assert result["workblocks"]==[]
    assert result["source_sections"]["experience"]==0


def test_one_column_date_job_in_one_line_is_one_candidate():
    doc=pymupdf.open()
    page=doc.new_page()
    page.insert_font(fontname="Fixture",fontfile=FONT)
    page.insert_text((70,100),"实习经历",fontname="Fixture")
    page.insert_text(
        (70,147),"2022.07-2023.09 合成科技有限公司 | 数据分析师",
        fontname="Fixture"
    )
    page.insert_text((70,180),"参与日报分析",fontname="Fixture")
    page.insert_text((70,222),"教育背景",fontname="Fixture")
    page.insert_text((70,249),"2020.09-2024.06 模拟大学",
                     fontname="Fixture")
    data=doc.tobytes()
    doc.close()
    result=propose_pdf_workblocks(data)
    assert len(result["workblocks"])==1
    assert result["workblocks"][0]["dates"]=={
        "start":"2022.07","end":"2023.09"
    }
    assert "数据分析师" in result["workblocks"][0]["source_text"]
    assert "模拟大学" not in result["workblocks"][0]["source_text"]


def test_date_inside_work_bullet_does_not_create_an_extra_job():
    data=_make_pdf(parallel=False,second_work=False,include_project=False)
    doc=pymupdf.open(stream=data,filetype="pdf")
    doc[0].insert_font(fontname="WorkFixtureCN",fontfile=FONT)
    doc[0].insert_text(
        (46,305),"- 参与 2022.01-2022.03 的接口调试",
        fontname="WorkFixtureCN",fontsize=10
    )
    final=doc.tobytes()
    doc.close()
    result=propose_pdf_workblocks(final)
    assert len(result["workblocks"])==1
    assert result["workblocks"][0]["dates"]["start"]=="2021.07"


def test_reject_invalid_pdf_or_over_25_pages():
    with pytest.raises(ValueError):
        propose_pdf_workblocks(b"Not a PDF")
    pdf=pymupdf.open()
    for _ in range(26):
        pdf.new_page()
    data=pdf.tobytes()
    pdf.close()
    with pytest.raises(ValueError,match="25"):
        propose_pdf_workblocks(data)
