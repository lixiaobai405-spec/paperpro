"""Opt-in real DeepSeek smoke test.

No credential storage. Start this script and provide the key on stdin only.
Uses invented resume facts, validates the application's real /api/enhance path,
and exports the returned draft in memory. At most one paid API request.
"""
from __future__ import annotations

from io import BytesIO
import json
import os
import sys
import time

import pymupdf
from docx import Document
from fastapi.testclient import TestClient

from app.enhancer import _numbers
from app.exporter import make_docx, make_pdf
from app.main import app
from app.models import Entry, Resume


def main() -> int:
    # Set an invalid custom endpoint to verify that the explicit provider
    # selection, not a hidden custom environment override, selects DeepSeek.
    os.environ["PAPERPRO_OPENAI_BASE_URL"] = "https://configured-route-must-not-run.invalid/v1"
    os.environ["PAPERPRO_OPENAI_MODEL"] = "unused-custom-model"
    print("READY_FOR_KEY", flush=True)
    key = sys.stdin.readline().strip()
    if not key:
        print(json.dumps({"status": "NO_KEY"}), flush=True)
        return 2

    # Fully invented material. No real resume or user data is sent to DeepSeek.
    source = Resume(
        name="测试候选人",
        title="后端开发工程师",
        email="example@example.invalid",
        summary="我做过Python后端和测试，写过接口，也帮忙维护过系统。",
        skills=["Python", "FastAPI", "MySQL"],
        experience=[
            Entry(
                heading="2024—2025 示例科技 | 后端开发",
                bullets=["我搞了一个内部API，通过调整数据库索引让响应时间缩短20%。"],
            ),
        ],
        projects=[
            Entry(
                heading="示例报表工具",
                bullets=["写了脚本生成内部数据报表。"],
            ),
        ],
    )
    started = time.monotonic()
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/enhance",
        json={
            "resume": source.model_dump(),
            "use_ai": True,
            "provider": "deepseek",
            "api_key": key,
            "target_role": "后端开发工程师",
        },
    )
    key = ""
    elapsed = round(time.monotonic() - started, 2)
    if response.status_code != 200:
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        detail = data.get("detail", "") if isinstance(data, dict) else ""
        print(json.dumps({
            "status": "API_REJECTED",
            "http_status": response.status_code,
            "elapsed_seconds": elapsed,
            "error_category": str(detail)[:160] or "not_json",
        }, ensure_ascii=False), flush=True)
        return 1

    body = response.json()
    candidate = Resume.model_validate(body["resume"])
    identity_safe = all(getattr(candidate, k) == getattr(source, k)
                        for k in ("name", "title", "email", "skills", "phone", "location"))
    shape_safe = (len(candidate.experience) == len(source.experience)
                  and len(candidate.projects) == len(source.projects)
                  and candidate.experience[0].heading == source.experience[0].heading
                  and candidate.projects[0].heading == source.projects[0].heading)
    metrics_safe = (
        _numbers(candidate.summary) == _numbers(source.summary)
        and _numbers(candidate.experience[0].bullets[0]) == _numbers(source.experience[0].bullets[0])
        and _numbers(candidate.projects[0].bullets[0]) == _numbers(source.projects[0].bullets[0])
    )
    docx = make_docx(candidate)
    pdf = make_pdf(candidate, docx)
    word = Document(BytesIO(docx))
    word_text = "\n".join(p.text for p in word.paragraphs)
    pdf_file = pymupdf.open(stream=pdf, filetype="pdf")
    pdf_text = "\n".join(page.get_text() for page in pdf_file)
    export_safe = all(name in text for name in ("测试候选人", "示例科技")
                      for text in (word_text, pdf_text))
    print(json.dumps({
        "status": "PASS" if all((identity_safe, shape_safe, metrics_safe, export_safe)) else "CHECK_FAILED",
        "model": "deepseek-flash",
        "provider": "DeepSeek",
        "elapsed_seconds": elapsed,
        "http_status": response.status_code,
        "ai_mode": body.get("mode"),
        "change_count": len(body.get("changes", [])),
        "sample_rewrite": candidate.summary[:170],
        "identity_protected": identity_safe,
        "section_shape_protected": shape_safe,
        "number_claims_protected": metrics_safe,
        "word_and_pdf_integrity": export_safe,
        "docx_size": len(docx),
        "pdf_size": len(pdf),
        "pdf_pages": len(pdf_file),
    }, ensure_ascii=False), flush=True)
    return 0 if all((identity_safe, shape_safe, metrics_safe, export_safe)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
