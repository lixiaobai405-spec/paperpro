"""Independent-GT non-target spans: red tests before any parser changes.

A trusted GT name or employment month is O *only with a unique literal
native-PDF source span*. Year-only or "present" GT is too ambiguous; a
name inside a company title must be protected. Nothing is inferred from
unlabeled/background text, and no production source is modified.
"""
from __future__ import annotations

import pymupdf
import pytest

from app.diagnosis.partial_bio import build_partial_bio, summarize_partial_bio
from tests.test_span_supervision import _single_line_doc

FONT="C:/Windows/Fonts/simhei.ttf"
TRAIN=(21,)


def _doc(*, repeat_date=False, name="张三", trailing_date=False,
         company_name=None):
    source=_single_line_doc()
    pdf=pymupdf.open(stream=source,filetype="pdf")
    page=pdf[0]
    page.insert_font(fontname="GTFixtureCN",fontfile=FONT)
    if name:
        page.insert_text((53,165),name,fontsize=12,fontname="GTFixtureCN")
    if repeat_date:
        page.insert_text((53,202),"备忘 2022.07",fontsize=11,fontname="GTFixtureCN")
    if trailing_date:
        page.insert_text((53,238),"2022.07.15",fontsize=11,fontname="GTFixtureCN")
    if company_name:
        page.insert_text((53,271),company_name,fontsize=11,fontname="GTFixtureCN")
    result=pdf.tobytes()
    pdf.close()
    return result


def _gt(**custom):
    baseline={
        "basicInfo":{"name":"张三"},
        "workExperience":[{
            "companyName":"合成科技有限公司",
            "position":"平台运营",
            "employmentPeriod":{"startDate":"2022.07","endDate":"2025.06"},
        }]
    }
    baseline.update(custom)
    return baseline


def _build(pdf,annotation):
    return build_partial_bio(pdf,annotation,source_id=21,
                             allowed_train_ids=TRAIN,forbidden_ids=(41,1))


def test_independent_name_and_start_end_months_create_exact_local_O():
    data=_build(_doc(),_gt())
    assert data["positive_span_count"]==2
    assert data["verified_background_span_count"]==3
    assert data["background_by_type"]=={
        "name":1, "employmentStartDate":1, "employmentEndDate":1
    }
    assert data["observed_O_count"]==len("张三")+len("2022.07")+len("2025.06")
    assert data["negative_background_labels_created"]==0
    assert data["background_provenance"]=="independent_GT_verified_non_target_only"
    observed=[]
    for line in data["lines"]:
        for evidence in line["verified_background_spans"]:
            a,b=evidence["start_char"],evidence["end_char"]
            literal=line["source_line"][a:b]
            assert all(tag=="O" for tag in line["tags"][a:b])
            assert evidence["label_source"] in {
                "independent_gt_identity","independent_gt_employment_date"
            }
            assert evidence["source_path"].startswith(("basicInfo.","workExperience."))
            observed.append(literal)
    assert set(observed)=={"张三","2022.07","2025.06"}
    measured=summarize_partial_bio([data])
    assert measured["observed_O_count"]==data["observed_O_count"]
    assert measured["standard_supervised_BIO_ready"] is False
    assert measured["unknown_characters"]>0


def test_duplicate_independent_date_abstains_but_other_fields_survive():
    data=_build(_doc(repeat_date=True),_gt())
    assert data["background_by_type"].get("employmentStartDate",0)==0
    assert data["background_by_type"]["employmentEndDate"]==1
    assert data["abstained_ambiguous_contact_spans"]==0
    assert data["abstained_ambiguous_non_target_spans"]>=1


def test_year_only_present_and_non_month_formats_never_count_as_O():
    fake=_gt()
    fake["workExperience"][0]["employmentPeriod"]={
        "startDate":"2022","endDate":"至今"
    }
    result=_build(_doc(),fake)
    assert result["background_by_type"].get("employmentStartDate",0)==0
    assert result["background_by_type"].get("employmentEndDate",0)==0
    assert result["abstained_invalid_non_target_fields"]>=2


def test_name_that_is_only_part_of_another_word_is_not_proven():
    doc=_doc(name="",company_name="张三研究中心")
    result=_build(doc,_gt())
    assert result["background_by_type"].get("name",0)==0
    assert result["abstained_missing_non_target_spans"]>=1


def test_non_target_date_cannot_override_target_company_GT_span():
    pdf=_doc()
    gt=_gt()
    gt["workExperience"][0]["companyName"]="2022.07"
    result=_build(pdf,gt)
    assert result["background_by_type"].get("employmentStartDate",0)==0
    assert result["abstained_conflicting_non_target_spans"]>=1
    assert result["observed_O_count"]>=len("2025.06")


def test_date_month_is_not_verified_inside_a_longer_date():
    fake=_gt()
    fake["workExperience"][0]["employmentPeriod"]={
        "startDate":"2022.07","endDate":"2030.09"
    }
    # Ignore the separate original 2022.07 in fixture by checking the
    # source-occurrence gate directly on a single longer date line.
    from app.diagnosis.partial_bio import _literal_verified_occurrences
    lines=[{"source_line":"2022.07.15"}]
    assert _literal_verified_occurrences(lines,"employmentStartDate","2022.07")==[]
    assert _literal_verified_occurrences(lines,"employmentEndDate","2022.07")==[]


def test_verified_background_cannot_be_fake_name_after_summary_mutation():
    import copy
    result=_build(_doc(),_gt())
    corrupted=copy.deepcopy(result)
    span=next(x for l in corrupted["lines"] for x in l["verified_background_spans"]
              if x["field"]=="name")
    span["source_path"]="basicInfo.personalEmail"
    with pytest.raises(ValueError,match="背景|来源"):
        summarize_partial_bio([corrupted])
