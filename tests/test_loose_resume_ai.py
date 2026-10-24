"""Loose resume AI structuring is optional, explicit and never an automatic writer."""
from __future__ import annotations

import json
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)
LOOSE = (
    "陈楠\n去年在星河公司做后端，负责 Python 接口和订单服务。\n"
    "做了库存项目，处理订单同步和接口重试。\n"
    "目前希望找开发岗，擅长 SQL。"
)


def _draft():
    response = client.post("/api/diagnosis/paste", json={"text": LOOSE})
    assert response.status_code == 200
    return response.json()["resume"]


def _payload():
    return {
        "resume": _draft(),
        "ai_consent": True,
        "ai_provider": "deepseek",
        "api_key": "TEST_EPHEMERAL_KEY",
    }


def test_loose_source_remains_usable_without_any_model_connection(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Default local path must not send network requests")

    monkeypatch.setattr("app.diagnosis.narrative.httpx.Client", forbidden)
    source = _draft()
    assert source["source_text"] == LOOSE
    report = client.post("/api/diagnosis/report", json={
        "resume": source, "target": {"role": "后端开发"}
    })
    assert report.status_code == 200
    assert "dimensions" in report.json()


def test_ai_structuring_requires_distinct_positive_consent_no_secret_echo():
    payload = _payload()
    payload["ai_consent"] = False
    response = client.post("/api/diagnosis/ai-structure", json=payload)
    assert response.status_code == 422
    assert "TEST_EPHEMERAL_KEY" not in response.text


def test_structured_model_draft_is_proposal_only_and_cannot_replace_source_metadata(monkeypatch):
    captured = []
    class FakeResponse:
        def raise_for_status(self): return None
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({
                "name": "陈楠",
                "experience": [{
                    "heading": "星河公司",
                    "company": "星河公司",
                    "role": "后端开发",
                    "start_date": "",
                    "end_date": "",
                    "bullets": ["负责 Python API 接口和订单服务"]
                }],
                "projects": [{"heading": "库存同步", "bullets": ["处理订单同步和接口重试"]}],
                "skills": ["Python", "SQL"],
                "source_text": "MALICIOUS REPLACEMENT",
                "source_sha256": "MALICIOUS REPLACEMENT",
                "extra": "unauthorized",
            }, ensure_ascii=False)}}]}
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, url, **kwargs):
            captured.append((url, kwargs))
            return FakeResponse()
    monkeypatch.setattr("app.diagnosis.narrative.httpx.Client", FakeClient)

    initial = _draft()
    response = client.post("/api/diagnosis/ai-structure", json=_payload())
    assert response.status_code == 200, response.text
    data = response.json()
    suggested = data["resume"]
    assert data["status"] == "proposal"
    assert suggested["source_text"] == LOOSE
    assert suggested["source_sha256"] == initial["source_sha256"]
    assert suggested["experience"][0]["company"] == "星河公司"
    assert suggested["projects"][0]["heading"] == "库存同步"
    assert suggested["additional"] == initial["additional"]  # raw leftovers are never lost
    assert len(captured) == 1
    assert captured[0][0] == "https://api.deepseek.com/v1/chat/completions"
    assert captured[0][1]["json"]["model"] == "deepseek-flash"
    assert json.loads(captured[0][1]["json"]["messages"][1]["content"])["source_text"] == LOOSE
    assert "TEST_EPHEMERAL_KEY" not in response.text


def test_malformed_model_output_does_not_erase_local_resume(monkeypatch):
    class FakeResponse:
        def raise_for_status(self): return None
        def json(self): return {"choices": [{"message": {"content": "invalid output"}}]}
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, *args, **kwargs): return FakeResponse()
    monkeypatch.setattr("app.diagnosis.narrative.httpx.Client", FakeClient)
    result = client.post("/api/diagnosis/ai-structure", json=_payload())
    assert result.status_code in {422, 502}
    assert "TEST_EPHEMERAL_KEY" not in result.text
    assert _draft()["source_text"] == LOOSE


def test_user_can_export_a_contentful_unnamed_draft_without_fabricating_a_name():
    result = client.post("/api/export?format=docx", json={
        "resume": {
            "name": "",
            "summary": "参与 API 维护、处理任务和测试。",
            "skills": ["Python"],
        }
    })
    assert result.status_code == 200, result.text[:300]
    assert result.content[:2] == b"PK"


def test_truly_empty_resume_does_not_generate_misleading_blank_export():
    result = client.post("/api/export?format=docx", json={
        "resume": {"name": "", "summary": ""}
    })
    assert result.status_code == 422


def test_missing_source_text_cannot_fabricate_a_complete_resume():
    payload = _payload()
    payload["resume"]["source_text"] = ""
    response = client.post("/api/diagnosis/ai-structure", json=payload)
    assert response.status_code == 422
