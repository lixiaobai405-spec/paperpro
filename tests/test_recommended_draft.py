"""Recommended-draft user contract: complete, non-blocking, opt-in and reversible."""
from __future__ import annotations

import json
from fastapi.testclient import TestClient

from app.diagnosis.schema import CandidateResume, CareerEntry, Target
from app.models import Entry
from app.main import app


client = TestClient(app, raise_server_exceptions=False)


def _resume() -> CandidateResume:
    return CandidateResume(
        name="合成测试用户",
        email="synthetic@example.invalid",
        source_sha256="synthetic-source-sha",
        source_text="合成测试用户；在示例企业做订单接口与 SQL 查询。",
        summary="",
        skills=["Python", "Python", "SQL"],
        experience=[CareerEntry(
            heading="2023.01 - 2025.06 示例企业 ｜ 后端开发",
            company="示例企业", role="后端开发",
            start_date="2023.01", end_date="2025.06",
            bullets=["开发订单 API", "• 与前端联调接口"],
        )],
        projects=[Entry(heading="订单后台", bullets=["使用 Python 开发接口", "使用 Python 开发接口"])],
    )


def _payload():
    return {
        "resume": _resume().model_dump(),
        "target": {"role": "后端工程师", "job_description": "要求 Python SQL"},
    }


def test_local_recommendation_creates_complete_editable_draft_without_any_network(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Local mode must never access the internet")
    monkeypatch.setattr("app.diagnosis.recommendation.httpx.Client", no_network)
    before = _payload()
    response = client.post("/api/diagnosis/recommend", json=before)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "local"
    draft = result["draft"]
    assert draft["summary"].startswith("相关工作与项目实践：")
    assert draft["skills"] == ["Python", "SQL"]
    assert draft["experience"][0]["company"] == "示例企业"
    assert draft["projects"][0]["bullets"] == ["使用 Python 开发接口"]
    assert draft["source_text"] == before["resume"]["source_text"]
    assert draft["source_sha256"] == before["resume"]["source_sha256"]
    assert result["improvements"]
    assert isinstance(result["questions"], list)
    assert before["resume"]["summary"] == ""


def test_candidate_with_missing_sections_still_gets_a_usable_draft():
    draft = CandidateResume(
        source_text="项目做了杂事。",
        additional=["项目做了杂事。"]
    )
    response = client.post("/api/diagnosis/recommend", json={
        "resume": draft.model_dump(), "target": {"company": "示例公司"}
    })
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "local"
    assert "项目做了杂事" in data["draft"]["additional"][0]
    assert data["draft"]["name"] == ""
    assert any(question["id"] == "name" for question in data["questions"])


def test_model_call_requires_explicit_positive_consent():
    response = client.post("/api/diagnosis/recommend", json={
        **_payload(),
        "use_ai": True,
        "ai_consent": False,
        "api_key": "DO_NOT_ECHO_SECRET",
    })
    assert response.status_code == 422
    assert "DO_NOT_ECHO_SECRET" not in response.text


def test_model_can_reorganize_whole_draft_without_overwriting_identity(monkeypatch):
    seen = []
    class FakeReply:
        def raise_for_status(self):
            pass
        def json(self):
            proposal = {"draft": {
                "name": "AI 捏造人物",
                "source_text": "EVIL",
                "source_sha256": "EVIL",
                "summary": "参与订单 API 研发、SQL 查询优化及跨团队接口联调。",
                "skills": ["Python", "SQL"],
                "experience": [{
                    "heading": "AI 虚构企业",
                    "company": "AI 虚构企业",
                    "role": "研发总监",
                    "start_date": "2010.01",
                    "end_date": "2026.12",
                    "bullets": ["参与订单 API 研发和前后端联调"]
                }],
                "projects": [
                    {"heading": "订单后台", "bullets": ["使用 Python 开发订单接口"]}
                ],
                "education": [{"heading": "虚构大学博士", "details": []}],
                "additional": [],
            }}
            return {"choices": [{"message": {"content": json.dumps(proposal, ensure_ascii=False)}}]}
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def post(self,url,**kwargs):
            seen.append((url,kwargs))
            return FakeReply()
    monkeypatch.setattr("app.diagnosis.recommendation.httpx.Client", FakeClient)
    payload = _payload()
    payload.update(use_ai=True,ai_consent=True,api_key="EPHEMERAL_ONLY")
    result = client.post("/api/diagnosis/recommend",json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["mode"] == "ai"
    draft=body["draft"]
    assert draft["name"] == "合成测试用户"
    assert draft["source_sha256"] == "synthetic-source-sha"
    assert draft["source_text"] == payload["resume"]["source_text"]
    assert draft["experience"][0]["company"] == "示例企业"
    assert draft["experience"][0]["role"] == "后端开发"
    assert draft["experience"][0]["start_date"] == "2023.01"
    assert draft["experience"][0]["bullets"] == ["参与订单 API 研发和前后端联调"]
    assert not draft["education"]
    assert draft["projects"][0]["bullets"] == ["使用 Python 开发订单接口"]
    assert len(body["improvements"]) > 0
    assert len(seen) == 1
    assert seen[0][0] == "https://api.deepseek.com/v1/chat/completions"
    assert "EPHEMERAL_ONLY" not in result.text


def test_model_failure_returns_local_draft_not_422(monkeypatch):
    class FakeClient:
        def __init__(self,**kwargs): pass
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def post(self,*args,**kwargs):
            raise RuntimeError("SIMULATED PROVIDER OUTAGE")
    monkeypatch.setattr("app.diagnosis.recommendation.httpx.Client", FakeClient)
    payload=_payload()
    payload.update(use_ai=True,ai_consent=True,api_key="EPHEMERAL_ONLY")
    response=client.post("/api/diagnosis/recommend",json=payload)
    assert response.status_code==200,response.text
    assert response.json()["mode"]=="fallback"
    assert response.json()["draft"]["summary"]
    assert "EPHEMERAL_ONLY" not in response.text


def test_negative_metrics_survive_bullet_cleanup():
    from app.diagnosis.recommendation import _local_recommendation
    original = CandidateResume(
        projects=[Entry(heading="合成案例", bullets=[
            "-20% 净变化，属于原始带负号的数值",
            "- 普通列表项",
        ])]
    )
    draft, _ = _local_recommendation(original, Target(role="后端开发"))
    assert draft.projects[0].bullets[0].startswith("-20%")
    assert draft.projects[0].bullets[1] == "普通列表项"


def test_no_key_fallback_and_resolved_source_are_still_safe(monkeypatch):
    import app.settings as settings
    monkeypatch.setattr(settings,"SETTINGS_DIR",__import__("pathlib").Path("E:/__nonexistent_paperpro_settings_root__"))
    monkeypatch.delenv("PAPERPRO_DEEPSEEK_API_KEY",raising=False)
    payload=_payload()
    payload.update(use_ai=True,ai_consent=True)
    response=client.post("/api/diagnosis/recommend",json=payload)
    assert response.status_code==200,response.text
    assert response.json()["mode"]=="fallback"
    assert response.json()["draft"]["source_sha256"]=="synthetic-source-sha"


def test_model_cannot_blank_all_existing_job_or_project_details():
    from app.diagnosis.recommendation import _local_recommendation, _apply_model_draft
    original = _resume()
    baseline, _ = _local_recommendation(original, Target(role="后端工程师"))
    draft, _ = _apply_model_draft(original, baseline, {
        "experience": [{"bullets": []}],
        "projects": [],
    })
    assert draft.experience[0].bullets
    assert draft.projects[0].heading == "订单后台"
    assert original.experience[0].bullets == ["开发订单 API", "• 与前端联调接口"]


def test_long_source_is_sent_as_valid_bounded_json_with_explicit_consent(monkeypatch):
    seen = []
    class Reply:
        def raise_for_status(self): pass
        def json(self): return {"choices":[{"message":{"content": '{"draft":{"summary":"参与订单 API 开发。"}}'}}]}
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*_):return False
        def post(self, url, **kwargs):
            seen.append(json.loads(kwargs["json"]["messages"][1]["content"]))
            return Reply()
    monkeypatch.setattr("app.diagnosis.recommendation.httpx.Client", FakeClient)
    payload = _payload()
    payload["resume"]["source_text"] += "示例材料" * 16000
    payload.update(use_ai=True, ai_consent=True, api_key="EPHEMERAL_ONLY")
    result = client.post("/api/diagnosis/recommend",json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["mode"] == "ai"
    assert len(seen) == 1
    assert len(seen[0]["source_text"]) <= 18000
    assert result.json()["draft"]["source_text"] == payload["resume"]["source_text"]
