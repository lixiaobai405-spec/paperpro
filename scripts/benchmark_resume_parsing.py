"""Offline synthetic resume extraction quality gates.

Examples:
    uv run --python 3.12 python -m scripts.benchmark_resume_parsing
    uv run --python 3.12 python -m scripts.benchmark_resume_parsing --include-ocr

Generates all synthetic DOCX/PDF/PNG/JPEG fixtures in memory, sends them only
to the application's in-process test interface and prints aggregate metrics.
Does not call external APIs, persist documents, or process any real person's CV.
"""
from __future__ import annotations

import argparse
import json

from app.diagnosis.synthetic_parse_bench import synthetic_parse_report
from app.diagnosis.synthetic_ocr_bench import synthetic_ocr_report


def run(*, include_ocr: bool = False) -> dict:
    documents = synthetic_parse_report()
    gate_documents = (
        documents["sample_count"] == 20
        and documents["formats"] == {"docx": 10, "pdf": 10}
        and documents["field_completeness"] >= 0.90
    )
    result = {
        "kind": "controlled_synthetic_resume_extraction_qa",
        "document_benchmark": documents,
        "document_gate_passed": gate_documents,
        "benchmark_scopes": {
            "documents": "20 synthetic in-memory DOCX/native PDF examples; not 20 real CVs",
            "photos": "synthetic sharp photo-like image OCR; not actual iOS/Android photos",
        },
        "real_resume_validation_completed": False,
        "real_photo_accuracy_validated": False,
    }
    if include_ocr:
        images = synthetic_ocr_report()
        result["image_benchmark"] = images
        result["image_gate_passed"] = (
            images["sample_count"] == 4
            and images["field_accuracy_proxy"] >= 0.85
        )
    result["passed"] = gate_documents and (
        not include_ocr or result["image_gate_passed"]
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PaperPro synthetic PDF/DOCX/photo extraction QA.")
    parser.add_argument("--include-ocr", action="store_true",
                        help="Also exercise actual local OCR on four sharp synthetic images.")
    args = parser.parse_args(argv)
    report = run(include_ocr=args.include_ocr)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
