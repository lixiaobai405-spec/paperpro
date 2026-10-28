"""Bind F10 exports to the exact report issued by this running service.

This is a stateless, process-local integrity seal, NOT user authentication or
evidence of the real-world truthfulness of a candidate's statements.

Reports issued before a service restart need to be regenerated, unless a
shared PAPERPRO_REPORT_SIGNING_KEY (at least 32 bytes) is configured for all
workers. The secret is never returned to the client.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
import os
import secrets


_configured_key = os.environ.get("PAPERPRO_REPORT_SIGNING_KEY", "").encode("utf-8")
_KEY = _configured_key if len(_configured_key) >= 32 else secrets.token_bytes(32)
_FIELD = "export_signature"


def _normalize_json(value):
    # JSON has one Number type. Browser JSON.stringify round-trips 1.0 to 1
    # and -0.0 to 0, while Python serializes them differently. Normalizing
    # these equivalent numeric values avoids rejecting genuine UI exports.
    if isinstance(value, dict):
        return {key: _normalize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _canonical(report: dict) -> bytes:
    if not isinstance(report, dict):
        raise ValueError("不是有效诊断报告")
    meta = report.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("诊断报告缺少元数据")
    snapshot = {**report, "meta": {key: val for key, val in meta.items() if key != _FIELD}}
    return json.dumps(
        _normalize_json(snapshot), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def issue_report(report: dict) -> dict:
    """Server-only issuance after all analysis/optional AI additions complete."""
    mac = hmac.new(_KEY, _canonical(report), sha256).hexdigest()
    report["meta"][_FIELD] = mac
    return report


def is_issued_report(report: dict) -> bool:
    if not isinstance(report, dict) or not isinstance(report.get("meta"), dict):
        return False
    signature = report["meta"].get(_FIELD)
    if not isinstance(signature, str) or len(signature) != 64:
        return False
    try:
        computed = hmac.new(_KEY, _canonical(report), sha256).hexdigest()
    except (ValueError, TypeError, OverflowError):
        return False
    return hmac.compare_digest(signature, computed)
