"""R7 geometry: proposals need *explicit human acceptance* before scoring.

The same three visible PDF spans can mean employer/title/date or unrelated
labels. So this test forbids any automatic mutation, even if geometry aligns.
"""
from __future__ import annotations

from hashlib import sha256
import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.parser import extract_file,parse_resume
from app.diagnosis.adapter import convert_resume

client=TestClient(app,raise_server_exceptions=False)
FONT="C:/Windows/Fonts/simhei.ttf"


def _pdf(*, organization="虚构技术有限公司", role="平台运营",
         extra_row=False, include_date=True) -> bytes:
    doc=pymupdf.open()
    page=doc.new_page(width=595,height=842)
    page.insert_font(fontname="SyntheticCN",fontfile=FONT)
    def put(x,y,text):
        page.insert_text((x,y),text,fontsize=11,fontname="SyntheticCN")
    put(40,80,"演示求职者")
    put(40,150,"工作经历")
    if include_date:
        put(45,211,"2021.07-2023.12")
    put(178,211,organization)
    put(398,211,role)
    put(44,256,"维护客户运营平台，并交付培训材料。")
    if extra_row:
        put(45,320,"2023.12-2024.09")
        put(178,320,"合成软件有限公司")
        put(398,320,"业务分析")
    data=doc.tobytes()
    doc.close()
    return data


def _upload(data: bytes) -> dict:
    response=client.post("/api/diagnosis/parse",files={
        "file":("synthetic-geometry.pdf",data,"application/pdf")
    })
    assert response.status_code==200,response.text[:300]
    assert response.json()["sha256"]==sha256(data).hexdigest()
    return response.json()


def _baseline(data: bytes):
    text,_,mode=extract_file("cv.pdf",data)
    return convert_resume(parse_resume(text),raw_text=text,fingerprint=sha256(data).hexdigest())


def test_geometric_evidence_generates_only_unverified_review_hint():
    data=_pdf()
    original=_baseline(data)
    assert len(original.experience)==1
    assert original.experience[0].role==""
    output=_upload(data)
    assert output["resume"]==original.model_dump()
    assert output["source_text"]==original.source_text
    hints=output["review_hints"]
    assert len(hints)==1
    h=hints[0]
    assert h["experience_index"]==0
    assert h["source_path"]=="experience.0.heading"
    assert h["source_heading"]==original.experience[0].heading
    assert h["suggested_company"]=="虚构技术有限公司"
    assert h["suggested_role"]=="平台运营"
    assert h["status"]=="unverified"
    assert "人工" in h["note"]
    assert any("未经核实" in line for line in output["warnings"])


def test_missing_employer_evidence_does_not_propose():
    data=_pdf(organization="陶艺兴趣小组")
    response=_upload(data)
    assert response["review_hints"]==[]
    assert response["resume"]==_baseline(data).model_dump()


def test_contact_is_never_a_proposed_job_title():
    data=_pdf(role="13800138000")
    response=_upload(data)
    assert response["review_hints"]==[]
    assert response["resume"]==_baseline(data).model_dump()


def test_no_date_never_creates_employment_or_hint():
    data=_pdf(include_date=False)
    response=_upload(data)
    assert response["review_hints"]==[]
    assert response["resume"]==_baseline(data).model_dump()


def test_two_work_periods_produce_distinct_hints_but_no_edits():
    data=_pdf(extra_row=True)
    response=_upload(data)
    assert response["resume"]==_baseline(data).model_dump()
    assert len(response["review_hints"])==2
    assert [h["experience_index"] for h in response["review_hints"]]==[0,1]
    assert [h["suggested_role"] for h in response["review_hints"]]==[
        "平台运营","业务分析"
    ]


def test_semantically_false_but_geometrically_plausible_title_needs_review():
    data=_pdf(role="陶艺爱好")
    response=_upload(data)
    # Geometry alone cannot distinguish a hobby from a real position.
    assert response["review_hints"][0]["suggested_role"]=="陶艺爱好"
    assert response["resume"]==_baseline(data).model_dump()
    assert response["resume"]["experience"][0]["role"]==""



def test_hint_has_field_target_page_bbox_and_uncalibrated_evidence_contract():
    hint = _upload(_pdf())["review_hints"][0]
    assert hint["field_path"] == "experience.0.role"
    assert hint["source_path"] == "experience.0.heading"
    assert hint["evidence"]["page_index"] == 0
    assert hint["evidence"]["page_number"] == 1
    assert hint["evidence"]["source_kind"] == "native_pdf_text"
    assert set(hint["evidence"]["boxes"]) == {"date", "employer", "role"}
    for box in hint["evidence"]["boxes"].values():
        assert len(box) == 4
        assert 0 <= box[0] < box[2] <= 1
        assert 0 <= box[1] < box[3] <= 1
    assert hint["confidence"]["calibrated"] is False
    assert hint["confidence"]["tier"] == "low"
    assert "horizontal_alignment" in hint["confidence"]["signals"]
    assert "existing_dated_experience" in hint["confidence"]["signals"]
    assert "independent_role_confirmation" in hint["confidence"]["missing"]
    assert hint["status"] == "unverified"


def test_plausible_but_semantically_false_hobby_is_never_high_confidence():
    hint = _upload(_pdf(role="陶艺爱好"))["review_hints"][0]
    assert hint["confidence"]["calibrated"] is False
    assert hint["confidence"]["tier"] == "low"
    assert hint["confidence"]["semantic_check"] == "not_verified"
    assert hint["suggested_role"] == "陶艺爱好"


def test_existing_roles_have_no_invasive_suggestions_or_provenance_changes():
    data = _pdf()
    baseline = _baseline(data).model_dump()
    assert baseline["source_sha256"] == sha256(data).hexdigest()
    result = _upload(data)
    assert result["resume"] == baseline
    assert result["sha256"] == sha256(data).hexdigest()
    assert all(h["status"] == "unverified" for h in result["review_hints"])



def test_second_pdf_page_coordinates_reference_correct_page():
    source = _pdf()
    doc = pymupdf.open(stream=source, filetype="pdf")
    cover = doc.new_page(pno=0, width=595, height=842)
    cover.insert_text((48, 50), "COVER PAGE FOR PDF GEOMETRY TEST", fontsize=11)
    data = doc.tobytes()
    doc.close()
    hints = _upload(data)["review_hints"]
    assert len(hints) == 1
    assert hints[0]["evidence"]["page_index"] == 1
    assert hints[0]["evidence"]["page_number"] == 2
    assert hints[0]["evidence"]["boxes"]["role"][0] > 0


def test_invalid_or_mismatched_anchor_cannot_pass_the_response_schema():
    import copy
    import pytest
    from pydantic import ValidationError
    from app.diagnosis.schema import WorkRelationHint

    valid = _upload(_pdf())["review_hints"][0]
    WorkRelationHint.model_validate(valid)
    mutations = [
        ("field_path", "experience.3.role"),
        ("status", "confirmed"),
    ]
    for key, bad in mutations:
        modified = {**valid, key:bad}
        with pytest.raises(ValidationError):
            WorkRelationHint.model_validate(modified)

    modified = copy.deepcopy(valid)
    modified["evidence"]["page_number"] = 13
    with pytest.raises(ValidationError):
        WorkRelationHint.model_validate(modified)

    modified = copy.deepcopy(valid)
    modified["evidence"]["boxes"]["role"] = [-0.1, 0.2, 1.1, 0.4]
    with pytest.raises(ValidationError):
        WorkRelationHint.model_validate(modified)

    modified = copy.deepcopy(valid)
    modified["confidence"]["calibrated"] = True
    with pytest.raises(ValidationError):
        WorkRelationHint.model_validate(modified)
