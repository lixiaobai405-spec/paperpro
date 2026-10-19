"""Read-only, offline validation of PaperPro job-fit scores against HR ratings.

Usage:
  uv run --python 3.12 python -m scripts.evaluate_hr_dataset --input evaluation_private/hr_labels.json

The input may contain sensitive employment details: store it ONLY on an
authorized local computer. This tool prints aggregate metrics, never records.
It never calls a model or modifies rule weights.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.diagnosis.calibration import evaluate_human_labels
from app.diagnosis.scoring import load_rules

MAX_INPUT_BYTES = 20 * 1024 * 1024


def evaluate_file(path: Path) -> dict:
    """Return only aggregate, privacy-safe evaluation metrics.

    The input is a JSON object with a cases array. Each case must contain
    a stable synthetic ID (not a person's name), a reviewed structured resume,
    the actual target role/JD, two independent HR match scores (0–100), and a
    preassigned train/test split. At least 20 cases are required.
    """
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("标注集不存在或超过 20 MB 上限")
    try:
        body = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, OSError, json.JSONDecodeError) as exc:
        raise ValueError("标注集不是有效 UTF-8 JSON") from exc
    if not isinstance(body, dict) or not isinstance(body.get("cases"), list):
        raise ValueError("顶层必须是包含 cases 数组的 JSON 对象")
    records = body["cases"]
    evaluation = evaluate_human_labels(records)
    evaluation["dataset"] = {
        "case_count": len(records),
        "split_train": sum(case["split"] == "train" for case in records),
        "split_test": sum(case["split"] == "test" for case in records),
        "rules_version": load_rules()["version"],
        "label_type": "human_job_fit_ratings",
    }
    return evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline assessment of PaperPro scoring, without writing or uploading personal data."
    )
    parser.add_argument("--input", type=Path, required=True, help="本机保密的 HR 标注 JSON 文件")
    args = parser.parse_args(argv)
    try:
        result = evaluate_file(args.input)
    except (ValueError, TypeError, KeyError, OSError):
        # Never expose raw JSON, résumé contents, provider keys or filenames
        # through tracebacks. Errors stay concise and locally actionable.
        print("VALIDATION_FAILED: 数据集未满足格式、规模、标注或独立性要求。")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
