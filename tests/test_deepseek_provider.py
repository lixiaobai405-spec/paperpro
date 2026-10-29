from fastapi.testclient import TestClient

from app.main import app
from app.models import Entry, Resume


def test_deepseek_provider_routes_only_to_official_endpoint(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {"message": {"content": (
                        '{"summary":"负责内部 API 开发与接口测试",'
                        '"experience_bullets":[["开发内部 API，优化查询使响应时间降低20%"]],'
                        '"project_bullets":[]}'
                    )}},
                ],
            }

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr("app.enhancer.httpx.Client", FakeClient)
    monkeypatch.setenv("PAPERPRO_OPENAI_BASE_URL", "https://custom.invalid/v1")
    monkeypatch.setenv("PAPERPRO_OPENAI_MODEL", "custom")
    resume = Resume(
        name="虚构候选人",
        summary="负责内部 API 和测试",
        experience=[
            Entry(
                heading="2024—2025 测试企业 | 软件工程师",
                bullets=["开发内部 API，优化查询使响应时间降低20%"],
            ),
        ],
    )
    response = TestClient(app).post("/api/enhance", json={
        "resume": resume.model_dump(),
        "use_ai": True,
        "provider": "deepseek",
        "api_key": "EPHEMERAL_TEST_TOKEN",
    })
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "ai"
    assert response.json()["resume"]["name"] == resume.name
    assert len(calls) == 1
    assert calls[0][0] == "https://api.deepseek.com/v1/chat/completions"
    assert calls[0][1]["json"]["model"] == "deepseek-flash"
    assert calls[0][1]["json"]["response_format"] == {"type": "json_object"}


def test_job_description_cannot_become_unverified_candidate_skill(monkeypatch):
    """An untrusted JD mentions Kubernetes, but only Python is reviewed."""
    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"choices": [{"message": {"content": (
                '{"summary":"熟悉 Python 开发",'
                '"experience_bullets":[["使用 Python 与 Kubernetes 开发 API"]],'
                '"project_bullets":[]}'
            )}}]}

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr("app.enhancer.httpx.Client", Client)
    original = Resume(
        name="虚构候选人",
        summary="熟悉 Python 开发",
        experience=[Entry(heading="已确认单位｜开发", bullets=["使用 Python 开发 API"])]
    )
    response = TestClient(app).post("/api/enhance", json={
        "resume": original.model_dump(), "use_ai": True,
        "provider": "deepseek", "api_key": "EPHEMERAL_TEST_TOKEN",
        "target_role": "后端开发",
        "job_description": "要求 Kubernetes 和 Docker 实战经验",
    })
    assert response.status_code == 422
    assert "新增了" in response.json()["detail"]
    assert "EPHEMERAL_TEST_TOKEN" not in response.text


def test_deepseek_never_uses_a_different_provider_key(monkeypatch):
    monkeypatch.setenv("PAPERPRO_OPENAI_API_KEY", "OPENAI_ONLY_SECRET")
    monkeypatch.delenv("PAPERPRO_DEEPSEEK_API_KEY", raising=False)
    result = TestClient(app).post("/api/enhance", json={
        "resume": Resume(name="Test", summary="work").model_dump(),
        "use_ai": True,
        "provider": "deepseek",
    })
    assert result.status_code == 400
    assert "OPENAI_ONLY_SECRET" not in result.text


def test_provider_name_is_allowlisted():
    result = TestClient(app).post("/api/enhance", json={
        "resume": Resume(name="Test", summary="work").model_dump(),
        "use_ai": True,
        "provider": "http://attacker.example/v1",
        "api_key": "SENSITIVE_TEST_KEY",
    })
    assert result.status_code == 422
    assert "SENSITIVE_TEST_KEY" not in result.text
