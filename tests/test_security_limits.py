from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

import pymupdf
from fastapi.testclient import TestClient

from app.main import app


def test_docx_zip_bomb_expansion_is_rejected_before_parsing():
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "x" * (58 * 1024 * 1024))
        archive.writestr("[Content_Types].xml", "not an actual docx")
    assert len(buffer.getvalue()) < 12 * 1024 * 1024
    response = TestClient(app).post("/api/extract", files={
        "file": ("compressed.docx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    })
    assert response.status_code == 422
    assert "解压" in response.json()["detail"] or "压缩" in response.json()["detail"]


def test_huge_pdf_page_does_not_allocate_large_ocr_bitmap():
    document = pymupdf.open()
    document.new_page(width=5500, height=5500).insert_text((30, 40), "Hi")
    response = TestClient(app).post("/api/extract", files={
        "file": ("giant.pdf", document.tobytes(), "application/pdf"),
    })
    assert response.status_code == 422
    assert "尺寸" in response.json()["detail"] or "像素" in response.json()["detail"]
