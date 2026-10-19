"""Untrusted layout-JSON → WorkBlock candidates; production remains untouched.

The adapter must not invent employer/role fields or mix parallel PDF columns.
The independent layout renderer is optional and is exercised separately.
"""
from __future__ import annotations

import copy
import pytest

from app.diagnosis.layout_workblocks import propose_workblocks_from_layout


def _box(text, x, y, *, kind="text"):
    return {
        "boxclass":kind,
        "x0":x,"y0":y-12,"x1":x+155,"y1":y+3,
        "textlines":[{
            "bbox":[x,y-12,x+155,y+3],
            "spans":[{"text":text}],
        }],
    }


def _layout():
    return {"pages":[{
        "page_number":1,"width":595,"height":842,
        "boxes":[
            _box("工作经历",35,77,kind="section-header"),
            _box("教育背景",335,84,kind="section-header"),
            _box("2021.07-2023.02",38,132),
            _box("2018.09-2022.06",337,145),
            _box("合成技术有限公司",38,163),
            _box("某某大学",338,176),
            _box("平台开发工程师",38,190),
            _box("统计专业",338,207),
            _box("2023.03-2024.05",38,247),
            _box("虚构网络有限公司",38,278),
            _box("数据分析师",38,305),
            _box("项目经历",36,375,kind="section-header"),
            _box("2023.05-2024.04",38,410),
            _box("虚构校园项目甲",38,435),
        ]
    }]}


def test_independent_parallel_column_sections_are_not_cross_contaminated():
    source=_layout()
    snapshot=copy.deepcopy(source)
    result=propose_workblocks_from_layout(source)
    assert source==snapshot
    assert result["engine"]=="pymupdf4llm"
    assert result["deployed"] is False
    assert result["automatic_resume_mutation"] is False
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
        assert "某某大学" not in block["source_text"]
        assert "虚构校园项目甲" not in block["source_text"]
        assert block["status"]=="unverified"
        assert block["auto_promote"] is False
        assert "company" not in block and "role" not in block
        assert len(block["bbox"])==4
        assert 0<=block["bbox"][0]<block["bbox"][2]<=1
        assert 0<=block["bbox"][1]<block["bbox"][3]<=1


def test_unknown_layout_section_header_terminates_experience_region():
    doc=_layout()
    doc["pages"][0]["boxes"].insert(9,_box(
        "未分类的下一节",36,235,kind="section-header"
    ))
    result=propose_workblocks_from_layout(doc)
    assert len(result["workblocks"])==1
    assert "虚构网络有限公司" not in result["workblocks"][0]["source_text"]


def test_layout_only_date_without_work_section_must_abstain():
    doc=_layout()
    doc["pages"][0]["boxes"]=[
        box for box in doc["pages"][0]["boxes"]
        if box["textlines"][0]["spans"][0]["text"]!="工作经历"
    ]
    output=propose_workblocks_from_layout(doc)
    assert output["workblocks"]==[]


def test_bad_bbox_or_missing_text_lines_does_not_forge_employment():
    doc=_layout()
    doc["pages"][0]["boxes"][2]["textlines"][0]["bbox"]=[-500,0,2,3]
    result=propose_workblocks_from_layout(doc)
    assert len(result["workblocks"])==1
    assert result["workblocks"][0]["dates"]["start"]=="2023.03"
    with pytest.raises(ValueError):
        propose_workblocks_from_layout({"pages":[{"width":0,"height":842,"boxes":[]}]})


def test_unknown_typographic_heading_policy_is_non_deployed_and_optional():
    fixture=_layout()
    fixture["pages"][0]["boxes"].insert(
        9,_box("未分类的中间标题",36,235,kind="section-header")
    )
    # Existing conservative behavior remains the default, regardless of
    # whether a more exploratory reading-order policy is tried.
    old=propose_workblocks_from_layout(fixture)
    assert len(old["workblocks"])==1
    exploration=propose_workblocks_from_layout(
        fixture,unknown_heading_policy="keep"
    )
    assert exploration["candidate_count"]==2
    assert exploration["deployed"] is False
    assert exploration["automatic_resume_mutation"] is False
    assert exploration["experimental_unknown_heading_policy"]=="keep"
    assert all(x["status"]=="unverified" and x["auto_promote"] is False
               for x in exploration["workblocks"])

    # A *known* different section (project) always cuts the region,
    # regardless of arbitrary font/header classification.
    assert all("虚构校园项目甲" not in x["source_text"]
               for x in exploration["workblocks"])
    with pytest.raises(ValueError,match="policy"):
        propose_workblocks_from_layout(
            fixture,unknown_heading_policy="auto_accept"
        )
