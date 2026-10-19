"""Lossless-enough projection from the existing extractor into candidate review."""
from __future__ import annotations

from hashlib import sha256
import re
from app.models import Resume
from app.parser import parse_resume
from .schema import CandidateResume, CareerEntry

# Accept Chinese 年/月 notation and common English or symbolic delimiters.
# Convert into YYYY.MM for the downstream calendar scorer.
YEAR_MONTH = r"(?:19|20)\d{2}(?:[./-]\s*(?:0?[1-9]|1[0-2])|年\s*(?:0?[1-9]|1[0-2])\s*月?)"
DATE_RANGE = re.compile(
    rf"(?P<start>{YEAR_MONTH})\s*(?:-|－|–|—|\u00ad|~|至|到|to)\s*"
    rf"(?P<end>{YEAR_MONTH}|至今|现在|present|current)",
    re.I,
)


def _normalized_month(raw: str) -> str:
    numbers = re.findall(r"\d+", raw)
    if len(numbers) != 2:
        return raw
    return f"{numbers[0]}.{int(numbers[1]):02d}"
CERT = re.compile(r"证书|资格|认证|CET[-\s]?[46]|PMP|CFA|CPA|certificate|certification", re.I)


def convert_resume(source: Resume, *, raw_text: str, fingerprint: str) -> CandidateResume:
    data = source.model_dump()
    converted = []
    for entry in source.experience:
        match = DATE_RANGE.search(entry.heading)
        remaining = entry.heading
        start = end = ""
        if match:
            start = _normalized_month(match.group("start"))
            end = (_normalized_month(match.group("end"))
                   if re.match(r"^(?:19|20)\d{2}", match.group("end"))
                   else match.group("end"))
            remaining = (entry.heading[:match.start()] + entry.heading[match.end():]).strip(" |-–—")
        parts = re.split(r"\s*[|丨｜」]\s*", remaining, maxsplit=1)
        company = parts[0].strip() if parts else ""
        role = parts[1].strip() if len(parts) == 2 else ""
        converted.append(CareerEntry(
            heading=entry.heading, bullets=entry.bullets,
            company=company, role=role, start_date=start, end_date=end,
        ))
    data["experience"] = [entry.model_dump() for entry in converted]
    data["certificates"] = [line for line in source.additional if CERT.search(line)]
    data["self_evaluation"] = source.summary
    data["source_sha256"] = fingerprint
    data["source_text"] = raw_text
    return CandidateResume.model_validate(data)


def from_text(text: str) -> CandidateResume:
    return convert_resume(parse_resume(text), raw_text=text, fingerprint=sha256(text.encode("utf-8")).hexdigest())
