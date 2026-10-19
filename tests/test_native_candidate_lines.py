"""Unlabeled PDF field discovery: GT must not enter the proposer.

These are synthetic documents, not real applicants or HR labels. The proposer
must abstain rather than infer work facts from contacts and section headings.
"""
from __future__ import annotations

from tests.test_work_relation_geometry import _pdf
from app.diagnosis.native_candidate_lines import propose_pdf_field_lines


def _by_field(rows, field):
    return [item for item in rows if item["field"] == field]


def test_independent_role_and_employer_native_lines_are_found_without_gt():
    pdf = _pdf()
    candidates = propose_pdf_field_lines(pdf)
    company = _by_field(candidates, "employer")
    role = _by_field(candidates, "work_role")
    assert any("虚构技术有限公司" in x["source_line"] for x in company)
    assert any("平台运营" in x["source_line"] for x in role)
    assert all(item["status"] == "unverified" for item in candidates)
    assert all(item["confidence"]["calibrated"] is False
               and item["confidence"]["tier"] == "low" for item in candidates)
    assert all(item["source_kind"] == "native_pdf_text" for item in candidates)
    assert all(item["automatic_resume_mutation"] is False for item in candidates)
    assert all(item["ready_for_training"] is False for item in candidates)
    assert all(item["page_index"] == 0 for item in candidates)
    assert all(len(item["line_bbox"]) == 4 and
               0 <= item["line_bbox"][0] < item["line_bbox"][2] <= 1 and
               0 <= item["line_bbox"][1] < item["line_bbox"][3] <= 1
               for item in candidates)


def test_unknown_hobby_or_phone_does_not_turn_into_role_or_employer():
    rows = propose_pdf_field_lines(_pdf(organization="陶艺兴趣小组", role="陶艺爱好"))
    assert all("陶艺爱好" not in item["source_line"]
               for item in _by_field(rows,"work_role"))
    assert all("陶艺兴趣小组" not in item["source_line"]
               for item in _by_field(rows,"employer"))
    rows2 = propose_pdf_field_lines(_pdf(role="13800138000"))
    assert all("13800138000" not in item["source_line"] for item in rows2)


def test_extra_work_row_stays_separate_and_never_creates_job_record():
    rows = propose_pdf_field_lines(_pdf(extra_row=True))
    roles = _by_field(rows,"work_role")
    assert any("平台运营" in row["source_line"] for row in roles)
    assert any("业务分析" in row["source_line"] for row in roles)
    assert len({(row["page_index"],tuple(row["line_bbox"])) for row in roles}) == len(roles)
    assert all("resume" not in row and "experience" not in row for row in rows)


def test_proposals_deterministic_and_capped():
    raw = _pdf(extra_row=True)
    assert propose_pdf_field_lines(raw) == propose_pdf_field_lines(raw)
    assert propose_pdf_field_lines(raw, max_candidates_per_field=1)
    assert sum(x["field"]=="work_role" for x in propose_pdf_field_lines(
        raw, max_candidates_per_field=1)) <= 1
    assert sum(x["field"]=="employer" for x in propose_pdf_field_lines(
        raw, max_candidates_per_field=1)) <= 1
