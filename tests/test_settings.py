"""Behavior tests for public settings.json + private local override.

No real credentials and no outbound network traffic are used here.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Resume


@pytest.fixture()
def config_dir(monkeypatch, tmp_path):
    import app.settings as settings

    monkeypatch.setattr(settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.delenv("PAPERPRO_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PAPERPRO_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PAPERPRO_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERPRO_OPENAI_MODEL", raising=False)

    (tmp_path / "settings.json").write_text(json.dumps({
        "deepseek": {"api_key": "", "_api_key_comment": "PUBLIC_BLANK"},
        "configured": {
            "api_key": "", "base_url": "https://api.example.test/v1",
            "model": "example-model"
        }
    }), encoding="utf-8")
    return tmp_path


def test_blank_public_json_means_ai_key_unavailable(config_dir):
    from app.settings import resolve_provider
    cfg = resolve_provider("deepseek")
    assert cfg.api_key == ""
    assert cfg.base_url == "https://api.deepseek.com/v1"
    assert cfg.model == "deepseek-flash"
    payload = TestClient(app).get("/api/config").json()
    assert payload["deepseek_ai_available"] is False
    assert payload["ai_available"] is False


def test_public_json_is_read_without_restarting_server(config_dir):
    from app.settings import resolve_provider
    f = config_dir / "settings.json"
    data = json.loads(f.read_text("utf-8"))
    data["deepseek"]["api_key"] = "TEST_PUBLIC_KEY"
    f.write_text(json.dumps(data), encoding="utf-8")
    first = resolve_provider("deepseek")
    assert first.api_key == "TEST_PUBLIC_KEY"
    assert TestClient(app).get("/api/config").json()["deepseek_ai_available"] is True
    data["deepseek"]["api_key"] = ""
    f.write_text(json.dumps(data), encoding="utf-8")
    assert resolve_provider("deepseek").api_key == ""
    assert TestClient(app).get("/api/config").json()["deepseek_ai_available"] is False


def test_private_local_json_overrides_public_but_not_manual_key(config_dir, monkeypatch):
    from app.settings import resolve_provider
    (config_dir / "settings.local.json").write_text(json.dumps({
        "deepseek": {"api_key": "PRIVATE_ONLY_KEY"},
        "configured": {"api_key": "PRIVATE_CUSTOM_KEY",
                       "base_url": "https://private.example.test/v1",
                       "model": "private-model"}
    }), encoding="utf-8")
    monkeypatch.setenv("PAPERPRO_DEEPSEEK_API_KEY", "ENV_DEEPSEEK_KEY")
    monkeypatch.setenv("PAPERPRO_OPENAI_API_KEY", "ENV_CUSTOM_KEY")
    a = resolve_provider("deepseek")
    b = resolve_provider("configured")
    assert a.api_key == "PRIVATE_ONLY_KEY"
    assert b.api_key == "PRIVATE_CUSTOM_KEY"
    assert b.base_url == "https://private.example.test/v1"
    assert b.model == "private-model"
    assert resolve_provider("deepseek", "REQUEST_KEY").api_key == "REQUEST_KEY"
    assert a.model == "deepseek-flash"


def test_environment_is_fallback_and_providers_do_not_cross(config_dir, monkeypatch):
    from app.settings import resolve_provider
    monkeypatch.setenv("PAPERPRO_OPENAI_API_KEY", "CUSTOM_KEY")
    monkeypatch.setenv("PAPERPRO_OPENAI_MODEL", "env-model")
    assert resolve_provider("deepseek").api_key == ""
    assert resolve_provider("configured").api_key == "CUSTOM_KEY"
    assert resolve_provider("configured").model == "env-model"
    result = TestClient(app).post("/api/enhance", json={
        "resume": Resume(name="Demo", summary="Built APIs").model_dump(),
        "use_ai": True, "provider": "deepseek",
    })
    assert result.status_code == 400


def test_real_api_route_reads_key_from_json_and_never_returns_it(config_dir, monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": (
                '{"summary":"Built backend APIs","experience_bullets":[],"project_bullets":[]}'
            )}}]}

    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, url, **kw):
            calls.append((url, kw))
            return Response()

    monkeypatch.setattr("app.enhancer.httpx.Client", FakeClient)
    (config_dir / "settings.local.json").write_text(
        json.dumps({"deepseek": {"api_key": "PRIVATE_TEST_KEY"}}), encoding="utf-8"
    )
    response = TestClient(app).post("/api/enhance", json={
        "resume": Resume(name="Demo", summary="Built APIs").model_dump(),
        "provider": "deepseek", "use_ai": True,
    })
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "ai"
    assert "PRIVATE_TEST_KEY" not in response.text
    assert calls[0][0] == "https://api.deepseek.com/v1/chat/completions"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer PRIVATE_TEST_KEY"


def test_malformed_json_fails_closed_and_does_not_echo_secret(config_dir):
    (config_dir / "settings.local.json").write_text(
        '{"deepseek": {"api_key": "SECRET_THAT_SHOULD_NOT_ECHO", ',
        encoding="utf-8",
    )
    response = TestClient(app).post("/api/enhance", json={
        "resume": Resume(name="Demo", summary="API").model_dump(),
        "provider": "deepseek", "use_ai": True,
    })
    assert response.status_code in {422, 503}
    assert "SECRET_THAT_SHOULD_NOT_ECHO" not in response.text


def test_invalid_provider_config_is_rejected(config_dir):
    (config_dir / "settings.local.json").write_text(
        '{"deepseek":{"api_key":["not","string"]}}', encoding="utf-8"
    )
    response = TestClient(app).post("/api/enhance", json={
        "resume": Resume(name="Demo", summary="API").model_dump(),
        "provider": "deepseek", "use_ai": True,
    })
    assert response.status_code in {422, 503}


def test_shipped_json_has_no_real_key():
    shipped = Path(__file__).resolve().parents[1] / "settings.json"
    data = json.loads(shipped.read_text("utf-8"))
    assert data["deepseek"]["api_key"] == ""
    assert data["configured"]["api_key"] == ""
    assert data["deepseek"]["_api_key_comment"]
    assert data["configured"]["_api_key_comment"]
