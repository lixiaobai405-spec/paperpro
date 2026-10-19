"""One-off external-source PDF resume acceptance benchmark (no artifact writes).

Source: jijunhao/SyntheticResumeData, Apache-2.0.
2,994 *synthetic*, diverse-layout PDFs with independent structured GT.
This does not contain genuine job applicants or HR interview outcome labels.

Run (uses a pinned external Git object checkout when present; falls back to API):
    uv run --python 3.12 python -m scripts.benchmark_external_resume_corpus

The benchmark streams PDF + JSON into RAM using a pinned repo commit.
The output contains only aggregated accuracy and anonymized source IDs; no
names, phones, e-mail addresses, raw résumé sentences or PDF bytes.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

import httpx
from fastapi.testclient import TestClient

from app.main import app

COMMIT = "3ecd09129f65955e743aacf67f2785fcee10d461"
DATASET = "jijunhao/SyntheticResumeData"
SOURCE = "https://github.com/" + DATASET
ROOT = "https://api.github.com/repos/" + DATASET + "/contents/"
IDS = tuple([*range(1, 11), *range(101, 106), *range(201, 206)])
FIELDS = ("name", "phone", "email", "company", "position", "start", "end", "school")
GIT_CACHE = Path(tempfile.gettempdir()) / "paperpro-public-resume-source"


def normalized(value: str) -> str:
    # No semantic rewriting of facts; normalize typography only.
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _fetch(client: httpx.Client, object_name: str) -> bytes:
    # Reading blobs via Git avoids unauthenticated GitHub API rate limits.
    # The blobless checkout lives under the OS temporary directory, outside
    # PaperPro; raw resumes or annotations never enter the product repository.
    if (GIT_CACHE / ".git").is_dir():
        commit = subprocess.run(
            ["git", "-C", str(GIT_CACHE), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if commit.returncode != 0 or commit.stdout.strip() != COMMIT:
            raise ValueError("External Git fixture checkout not pinned to expected commit")
        blob_result = subprocess.run(
            ["git", "-C", str(GIT_CACHE), "show", COMMIT + ":" + object_name],
            capture_output=True, timeout=45, check=False,
        )
        if blob_result.returncode != 0:
            raise ValueError("Cannot read pinned external Git object")
        blob = blob_result.stdout
    else:
        response = client.get(ROOT + object_name, params={"ref": COMMIT})
        response.raise_for_status()
        data = response.json()
        if data.get("encoding") != "base64":
            raise ValueError("GitHub did not return embedded base64 data")
        blob = base64.b64decode(data["content"], validate=False)
    if len(blob) > 10 * 1024 * 1024:
        raise ValueError("External PDF exceeds PaperPro upload allowance")
    return blob


def _truth(gt: dict) -> dict[str, list[str]]:
    basic = gt.get("basicInfo") or {}
    work = gt.get("workExperience") or []
    education = gt.get("education") or []
    result = {
        "name": [basic.get("name", "")],
        "phone": [basic.get("phoneNumber", "")],
        "email": [basic.get("personalEmail", "")],
        "company": [item.get("companyName", "") for item in work],
        "position": [item.get("position", "") for item in work],
        "start": [(item.get("employmentPeriod") or {}).get("startDate", "")
                  for item in work],
        "end": [(item.get("employmentPeriod") or {}).get("endDate", "")
                for item in work],
        "school": [item.get("school", "") for item in education],
    }
    return {k: [str(v).strip() for v in values
                if isinstance(v, str) and v.strip()]
            for k, values in result.items()}


def _actual(doc: dict) -> dict[str, list[str]]:
    resume = doc["resume"]
    work = resume.get("experience") or []
    education = resume.get("education") or []
    return {
        "name": [resume.get("name") or ""],
        "phone": [resume.get("phone") or ""],
        "email": [resume.get("email") or ""],
        "company": [(x.get("company") or "") for x in work],
        "position": [(x.get("role") or "") for x in work],
        "start": [(x.get("start_date") or "") for x in work],
        "end": [(x.get("end_date") or "") for x in work],
        "school": [(x.get("heading") or "") for x in education],
    }


def assess(truth: list[str], actual: list[str]) -> tuple[int, int]:
    """Per-field-item recall: every expected entity is assessed separately."""
    actual_strings = [normalized(x) for x in actual if x]
    total = len(truth)
    passed = 0
    for item in truth:
        target = normalized(item)
        if target and any(target in value for value in actual_strings):
            passed += 1
    return passed, total


def run(ids: tuple[int, ...] = IDS) -> dict:
    records: list[dict] = []
    aggregate: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    parsed_ok = 0
    source_bytes_total = 0
    failures = []
    with httpx.Client(
        timeout=25, follow_redirects=False,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "PaperPro-open-benchmark"},
    ) as http, TestClient(app, raise_server_exceptions=False) as api:
        for id_ in ids:
            started = time.monotonic()
            try:
                pdf = _fetch(http, f"resume_list_pdf/{id_}.pdf")
                gt = json.loads(_fetch(http, f"result_gt/{id_}.json"))
                response = api.post("/api/diagnosis/parse", files={
                    "file":(f"external-synthetic-{id_}.pdf",pdf,"application/pdf"),
                })
                if response.status_code != 200:
                    raise ValueError("Parser rejected PDF")
                parsed = response.json()
                if parsed["sha256"] != sha256(pdf).hexdigest():
                    raise ValueError("Source SHA mismatch")
                truth = _truth(gt)
                actual = _actual(parsed)
                raw_text = normalized(parsed.get("source_text",""))
                for category in FIELDS:
                    expected = truth[category]
                    matched, n = assess(expected, actual[category])
                    text_matched = sum(
                        bool(normalized(x)) and normalized(x) in raw_text
                        for x in expected
                    )
                    aggregate[category][0] += matched
                    aggregate[category][1] += n
                    aggregate[category][2] += text_matched
                parsed_ok += 1
                source_bytes_total += len(pdf)
                records.append({
                    "synthetic_id": id_, "status":"ok",
                    "mode":parsed.get("method"),
                    "pages":len(gt.get("pages") or []),
                    "has_images":any(p.get("has_image") for p in gt.get("pages") or []),
                    "duration_seconds":round(time.monotonic()-started,2),
                })
            except (httpx.HTTPError, ValueError, KeyError, TypeError,
                    json.JSONDecodeError) as error:
                failures.append({
                    "synthetic_id": id_, "status":"not_processed",
                    "error_type":type(error).__name__,
                })
    n_struct=sum(entry[0] for entry in aggregate.values())
    n_gt=sum(entry[1] for entry in aggregate.values())
    n_text=sum(entry[2] for entry in aggregate.values())
    return {
        "type":"independent_source_synthetic_pdf_ground_truth_benchmark",
        "source":SOURCE,"source_license":"Apache-2.0",
        "source_commit":COMMIT,
        "transport":("external_pinned_git_objects" if (GIT_CACHE/".git").is_dir()
                     else "github_contents_api"),
        "requested_pdfs":len(ids), "parsed_pdfs":parsed_ok,
        "raw_pdf_bytes_processed_in_memory":source_bytes_total,
        "ground_truth_type":"semi-automated with manual verification, per upstream dataset",
        "structured_entity_recall":round(n_struct/n_gt,4) if n_gt else None,
        "raw_text_entity_recall":round(n_text/n_gt,4) if n_gt else None,
        "ground_truth_items":n_gt,
        "structured_hits":n_struct,"raw_text_hits":n_text,
        "by_field":{
            field:{
                "structured_hits":aggregate[field][0],
                "ground_truth_items":aggregate[field][1],
                "raw_text_hits":aggregate[field][2],
                "structured_recall":round(aggregate[field][0]/aggregate[field][1],4)
                if aggregate[field][1] else None,
            } for field in FIELDS
        },
        "case_metadata":records,
        "failures":failures,
        "real_applicant_resume_corpus":False,
        "real_hr_scoring_validation":False,
        "external_source_to_engine_coverage":True,
        "claim_boundary":"Externally published synthetic PDFs and GT only. No real candidate selection labels.",
    }


def main() -> None:
    print(json.dumps(run(),ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
