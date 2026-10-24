from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import sys
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pymupdf
import pytest
from PIL import Image

from app import document_converter, parser
from app.pdf_runtime import PDF_LOCK, serialized_pdf


@pytest.mark.parametrize("cpus, expected", [(8, 2), (1, 1)])
def test_container_ocr_limits_backend_threads(monkeypatch, cpus, expected):
    configured, opencv_threads = [], []
    monkeypatch.setenv("PAPERPRO_OCR_THREADS", "2")
    monkeypatch.setattr(parser.os, "cpu_count", lambda: cpus)
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", SimpleNamespace(
        RapidOCR=lambda **options: configured.append(options) or object(),
    ))
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(setNumThreads=opencv_threads.append))
    parser._ocr_engine.cache_clear()
    try:
        parser._ocr_engine()
        assert configured == [{"intra_op_num_threads": expected, "inter_op_num_threads": 1}]
        assert opencv_threads == [expected]
    finally:
        parser._ocr_engine.cache_clear()


def test_concurrent_uploads_do_not_share_mutable_ocr_state(monkeypatch):
    active = maximum = 0
    counter_lock = threading.Lock()

    def inference(image):
        nonlocal active, maximum
        with counter_lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with counter_lock:
            active -= 1
        return "OCR evidence"

    monkeypatch.setattr(parser, "_ocr_image_unlocked", inference)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(parser._ocr_image, [Image.new("RGB", (10, 10))] * 4))
    assert values == ["OCR evidence"] * 4
    assert maximum == 1


def test_pdf_work_is_serialized_across_threads():
    entered = threading.Barrier(4)
    counter_lock = threading.Lock()
    active = maximum = 0

    @serialized_pdf
    def work():
        nonlocal active, maximum
        with counter_lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.01)
        with counter_lock:
            active -= 1

    def request(_):
        entered.wait(timeout=5)
        work()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(request, range(4)))
    assert maximum == 1


def test_uploaded_and_converted_pdf_enter_the_same_lock(monkeypatch):
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((30, 50), "CANDIDATE NATIVE PDF EVIDENCE", fontsize=12)
        data = pdf.tobytes()
    original_open = pymupdf.open
    calls = []

    def checked_open(*args, **kwargs):
        assert PDF_LOCK._is_owned()
        calls.append(1)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(pymupdf, "open", checked_open)
    text, _, method = parser.extract_file("candidate.pdf", data)
    assert "CANDIDATE" in text and method == "pdf-text"
    document_converter._validate_pdf(data)
    assert len(calls) == 2


def test_blocking_upload_does_not_block_health_endpoint(monkeypatch):
    import app.main as main
    entered, release = threading.Event(), threading.Event()

    def slow_extract(name, data):
        entered.set()
        release.wait(timeout=3)
        return "陈晓明\n工作经历\nPython 工程师", [], "docx"

    monkeypatch.setattr(main, "extract_file", slow_extract)
    with TestClient(main.app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/extract", files={"file": ("synthetic.docx", b"synthetic", "application/octet-stream")})
        try:
            assert entered.wait(timeout=2)
            before = time.monotonic()
            assert client.get("/api/health").status_code == 200
            assert time.monotonic() - before < 1
            assert not pending.done()
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 200
