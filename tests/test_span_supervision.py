"""Independent GT substring spans on native PDF lines, not whole-line classes."""
from __future__ import annotations

import pymupdf
from tests.test_work_relation_geometry import _pdf

from app.diagnosis.span_supervision import align_gt_char_spans


def _single_line_doc():
    doc=pymupdf.open()
    page=doc.new_page()
    page.insert_font(fontname="CN",fontfile="C:/Windows/Fonts/simhei.ttf")
    page.insert_text(
        (52,85),
        "2022.07—2025.06 合成科技有限公司 | 平台运营",
        fontsize=12,fontname="CN"
    )
    page.insert_text((52,125),"工作经历",fontsize=11,fontname="CN")
    data=doc.tobytes()
    doc.close()
    return data


def test_two_independently_annotated_fields_in_one_line_are_not_discarded():
    raw=_single_line_doc()
    gt={"workExperience":[{
        "companyName":"合成科技有限公司",
        "position":"平台运营",
    }]}
    result=align_gt_char_spans(raw,gt)
    assert result["field_counts"]["work_role"]["found"]==1
    assert result["field_counts"]["employer"]["found"]==1
    assert result["unlabeled_character_negatives_created"]==0
    spans=result["positive_spans"]
    role=next(s for s in spans if s["field"]=="work_role")
    company=next(s for s in spans if s["field"]=="employer")
    assert role["page_index"]==company["page_index"]==0
    assert role["line_bbox"]==company["line_bbox"]
    assert role["start_char"]>=company["end_char"]
    assert role["source_line"][role["start_char"]:role["end_char"]]=="平台运营"
    assert company["source_line"][company["start_char"]:company["end_char"]]=="合成科技有限公司"
    assert role["label_source"]=="independent_gt"
    assert all(s["ready_for_training"] is False for s in spans)


def test_repeated_substring_in_multiple_lines_is_ambiguous_not_negative():
    doc=pymupdf.open(stream=_single_line_doc(),filetype="pdf")
    p=doc[0]
    p.insert_font(fontname="CN",fontfile="C:/Windows/Fonts/simhei.ttf")
    p.insert_text((52,165),"平台运营",fontsize=11,fontname="CN")
    raw=doc.tobytes()
    doc.close()
    result=align_gt_char_spans(raw,{"workExperience":[{"position":"平台运营"}]})
    assert result["positive_spans"]==[]
    assert result["field_counts"]["work_role"]["ambiguous"]==1
    assert result["unlabeled_character_negatives_created"]==0


def test_overlapping_company_and_role_names_cannot_be_both_confirmed():
    doc=pymupdf.open()
    page=doc.new_page()
    page.insert_font(fontname="CN",fontfile="C:/Windows/Fonts/simhei.ttf")
    page.insert_text((52,85),"平台运营有限公司",fontsize=12,fontname="CN")
    raw=doc.tobytes();doc.close()
    result=align_gt_char_spans(raw,{"workExperience":[{
        "companyName":"平台运营有限公司","position":"平台运营"
    }]})
    assert result["positive_spans"]==[]
    assert result["overlapping_span_occurrences"]>=1


def test_missing_values_abstain_without_negative_labels():
    result=align_gt_char_spans(_single_line_doc(),{
        "workExperience":[{"position":"未实际出现的岗位"}]
    })
    assert result["positive_spans"]==[]
    assert result["field_counts"]["work_role"]["missing"]==1
    assert result["unlabeled_character_negatives_created"]==0
