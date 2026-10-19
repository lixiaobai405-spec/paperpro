"""In-memory high-resolution synthetic image OCR QA for the candidate parser.

These screenshots/photo-like examples do not estimate real mobile-camera OCR
accuracy. No personal records, no persistent artifacts, no external OCR API.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from .synthetic_parse_bench import _case, _field_checks, _lines, client


def _scan(sample: dict) -> tuple[str, bytes]:
    canvas = Image.new("RGB", (2000, 1500), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(
        "C:/Windows/Fonts/simhei.ttf" if sample["zh"] else "C:/Windows/Fonts/arial.ttf",
        41 if sample["zh"] else 44,
    )
    for i, line in enumerate(_lines(sample)):
        draw.text((74, 60 + 85 * i), line, font=font, fill=(12, 20, 31))
    # Slight camera tilt for two cases, but keep the text fully legible.
    if sample["index"] in (2, 11):
        canvas = canvas.rotate(0.7, expand=True, fillcolor="white")
    ext = "png" if sample["index"] in (0, 10) else "jpg"
    buffer = BytesIO()
    canvas.save(buffer, "PNG" if ext == "png" else "JPEG", quality=95)
    return ext, buffer.getvalue()


def synthetic_ocr_report() -> dict:
    cases = [_case(i) for i in (0, 2, 10, 11)]
    processed = []
    failures = []
    passed_fields = 0
    for sample in cases:
        ext, data = _scan(sample)
        response = client.post(
            "/api/diagnosis/parse",
            files={"file": (f"mock-photo-{sample['index']:02d}.{ext}", data)},
        )
        if response.status_code != 200:
            processed.append({"case": sample["index"], "format": ext,
                              "http_status": response.status_code})
            failures.append({"case": sample["index"],"category": "ocr_unavailable"})
            continue
        body = response.json()
        checks = _field_checks(sample, body)
        count = sum(checks.values())
        passed_fields += count
        for field, ok in checks.items():
            if not ok:
                failures.append({
                    "case": sample["index"],
                    "category": "field_mismatch", "field": field,
                })
        processed.append({
            "case": sample["index"], "format": ext,
            "parsed_method": body["method"],
            "source_checksum_equal": body["sha256"] == sha256(data).hexdigest(),
            "recognized_field_count": count,
            "expected_field_count": len(checks),
        })
    return {
        "kind": "controlled_clear_synthetic_photo_ocr",
        "sample_count": len(cases),
        "expected_field_cells": 13 * len(cases),
        "passed_field_cells": passed_fields,
        "field_accuracy_proxy": round(passed_fields / (13 * len(cases)), 4),
        "cases": processed,
        "failures": failures,
        "real_mobile_camera_accuracy_verified": False,
    }
