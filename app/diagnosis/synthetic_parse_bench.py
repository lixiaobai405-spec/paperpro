"""20 synthetic, in-memory PDF/DOCX resumes; never a claim about real OCR accuracy.

The expected fields are authored before invoking PaperPro. Variants exercise
different date notations, table-based work records, wrapped bullets and the
difference between English native-PDF and Chinese DOCX extraction.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pymupdf
from docx import Document
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def _case(index: int) -> dict:
    zh = index < 10
    role = "后端开发工程师" if zh else "Backend Developer"
    name = f"模拟候选者{index:02d}" if zh else f"Avery Example{index:02d}"
    company = f"示例科技{index:02d}" if zh else f"Example Labs {index:02d}"
    project = f"示例数据平台{index:02d}" if zh else f"Sample Service {index:02d}"
    school = f"示例大学{index:02d}" if zh else f"Example University {index:02d}"
    start, end = ("2022.01", "2025.06")
    variant = index % 5
    if variant == 1:
        period = f"2022/01 – 2025/06"
    elif variant == 2 and zh:
        period = "2022年01月—2025年06月"
    elif variant == 3:
        period = "2022.01至2025.06" if zh else "2022.01 to 2025.06"
    else:
        period = f"{start} - {end}"
    bullet = (
        f"使用 Python 和 SQL 开发业务 API；任务标识 C{index:02d}。"
        if zh else f"Developed Python SQL backend API for demo account C{index:02d}."
    )
    return {
        "index": index, "zh": zh, "name": name, "role": role,
        "email": f"synthetic{index:02d}@example.invalid",
        "company": company, "project": project, "school": school,
        "start_date": start, "end_date": end,
        "period": period, "bullet": bullet,
        "skills": ["Python", "SQL"],
        "certificate": "CET-6" if zh else "PMP",
        "summary": "本人有真实可核对的示例经历" if zh else "Built software and maintained internal tools.",
    }


def _lines(sample: dict) -> list[str]:
    if sample["zh"]:
        headings = [
            sample["name"], sample["email"],
            "求职意向：" + sample["role"],
            "个人简介", sample["summary"],
            "专业技能", "Python、SQL、Git",
            "工作经历", sample["period"] + " " + sample["company"] + " | " + sample["role"],
            "- " + sample["bullet"],
            "项目经历", sample["project"],
            "- 在项目中使用 Python SQL API。",
            "教育背景", "2018.09 - 2022.06 " + sample["school"] + " | 计算机本科学士",
            "证书", "CET-6",
        ]
    else:
        headings = [
            sample["name"], sample["email"],
            "Target Role: " + sample["role"],
            "Professional Summary", sample["summary"],
            "Skills", "Python, SQL, Git",
            "Work Experience",
            sample["period"] + " " + sample["company"] + " | " + sample["role"],
            "- " + sample["bullet"],
            "Projects", sample["project"],
            "- Built Python SQL API service.",
            "Education", "2018.09 - 2022.06 " + sample["school"] + " | Bachelor",
            "Certifications", "PMP",
        ]
    return headings


def _render_docx(sample: dict) -> bytes:
    doc = Document()
    lines = _lines(sample)
    table_layout = sample["index"] % 2 == 0
    for offset, line in enumerate(lines):
        if table_layout and offset == 8:
            table = doc.add_table(rows=1, cols=2)
            left, right = line.split(" | ", maxsplit=1)
            table.cell(0, 0).text = left
            table.cell(0, 1).text = right
        else:
            doc.add_paragraph(line)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _render_pdf(sample: dict) -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    lines = _lines(sample)
    # Embed the exact font so an en dash survives round-trip extraction;
    # the built-in Helvetica font replaces some glyphs with middle dots.
    page.insert_font(fontname="FixtureArial", fontfile="C:/Windows/Fonts/arial.ttf")
    for index, text in enumerate(lines):
        page.insert_text((42, 55 + 34 * index), text, fontsize=11,
                         fontname="FixtureArial")
    content = document.tobytes(garbage=3, deflate=True)
    document.close()
    return content


def build_cases() -> list[tuple[dict, str, bytes]]:
    result = []
    for i in range(20):
        sample = _case(i)
        ext = "docx" if sample["zh"] else "pdf"
        content = _render_docx(sample) if ext == "docx" else _render_pdf(sample)
        result.append((sample, ext, content))
    return result


def _field_checks(sample: dict, data: dict) -> dict[str, bool]:
    resume = data.get("resume", {})
    experiences = resume.get("experience") or []
    projects = resume.get("projects") or []
    education = resume.get("education") or []
    experience = experiences[0] if experiences else {}
    project = projects[0] if projects else {}
    school = education[0] if education else {}
    return {
        "name": resume.get("name") == sample["name"],
        "email": resume.get("email") == sample["email"],
        "target_role": resume.get("title") == sample["role"],
        "summary": sample["summary"] in resume.get("summary", ""),
        "skills": all(skill in resume.get("skills", []) for skill in sample["skills"]),
        "company": sample["company"] in experience.get("company", ""),
        "work_role": sample["role"] in experience.get("role", ""),
        "work_start": experience.get("start_date") == sample["start_date"],
        "work_end": experience.get("end_date") == sample["end_date"],
        "work_bullet": f"C{sample['index']:02d}" in " ".join(experience.get("bullets", [])),
        "project": sample["project"] in project.get("heading", ""),
        "education": sample["school"] in school.get("heading", ""),
        "certificate": sample["certificate"] in resume.get("certificates", []),
    }


def synthetic_parse_report() -> dict:
    checks: dict[str, dict[str, bool]] = {}
    status: dict[str, int] = {}
    failures = []
    for sample, ext, original in build_cases():
        response = client.post(
            "/api/diagnosis/parse",
            files={"file": (f"synthetic-{sample['index']:02d}.{ext}", original)},
        )
        if response.status_code != 200:
            failures.append({"case": sample["index"], "format": ext,
                             "http_status": response.status_code,
                             "category": "parse_error"})
            continue
        data = response.json()
        if data["sha256"] != sha256(original).hexdigest():
            failures.append({"case": sample["index"],"format": ext,
                             "category": "raw_file_hash_changed"})
        fields = _field_checks(sample, data)
        checks[str(sample["index"])] = fields
        status[ext] = status.get(ext, 0) + 1
        for key, passed in fields.items():
            if not passed:
                failures.append({
                    "case": sample["index"], "format": ext,
                    "field": key, "category": "field_mismatch",
                })
    total = 20 * 13
    passed = sum(sum(one.values()) for one in checks.values())
    per_field = {
        field: {
            "checked": len(checks),
            "passed": sum(items[field] for items in checks.values()),
        }
        for field in next(iter(checks.values())) if checks
    }
    return {
        "kind": "in_memory_synthetic_pdf_docx_extraction_benchmark",
        "sample_count": 20, "formats": status,
        "fields_per_sample": 13, "expected_field_cells": total,
        "field_pass_count": passed, "field_completeness": round(passed / total, 4),
        "per_field": per_field,
        "failures": failures,
        "real_user_accuracy_verified": False,
    }
