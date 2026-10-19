"""PaperPro provider settings: public defaults + private local overrides.

Only this module owns disk/environment configuration precedence. Public
settings.json is a *template*, and settings.local.json is gitignored.
Credentials never appear in returned /api/config JSON or error messages.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Literal


SETTINGS_DIR = Path(__file__).resolve().parents[1]
MAX_SETTINGS_BYTES = 64 * 1024
OFFICIAL_DEEPSEEK_URL = "https://api.deepseek.com/v1"
OFFICIAL_DEEPSEEK_MODEL = "deepseek-flash"
DEFAULT_CUSTOM_URL = "https://api.openai.com/v1"
DEFAULT_CUSTOM_MODEL = "gpt-4.1-mini"


class SettingsError(ValueError):
    """A settings file is malformed. Never echo its original text."""


@dataclass(frozen=True, repr=False)
class ProviderSettings:
    provider: Literal["deepseek", "configured"]
    api_key: str
    base_url: str
    model: str

    def __repr__(self) -> str:
        # Avoid accidental credential disclosure when an exception logs the
        # resolved value.
        return (
            f"ProviderSettings(provider={self.provider!r}, api_key=<redacted>, "
            f"base_url={self.base_url!r}, model={self.model!r})"
        )


def _load_file(filename: str) -> dict:
    file = SETTINGS_DIR / filename
    if not file.exists():
        return {}
    try:
        if file.stat().st_size > MAX_SETTINGS_BYTES:
            raise SettingsError(f"{filename} 过大，请精简配置")
        value = json.loads(file.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SettingsError(f"{filename} 格式无效，请检查 JSON 语法") from exc
    if not isinstance(value, dict):
        raise SettingsError(f"{filename} 必须为 JSON 对象")
    return value


def _property(data: dict, section: str, field: str) -> str:
    source = data.get(section, {})
    if not isinstance(source, dict):
        raise SettingsError(f"{section} 配置必须为 JSON 对象")
    value = source.get(field, "")
    if not isinstance(value, str) or len(value) > 1024:
        raise SettingsError(f"{section}.{field} 必须为长度不超过 1024 的字符串")
    return value.strip()


def _first(*choices: str) -> str:
    return next((value for value in choices if value), "")


def resolve_provider(
    provider: Literal["deepseek", "configured"],
    request_api_key: str | None = None,
) -> ProviderSettings:
    if provider not in {"deepseek", "configured"}:
        raise SettingsError("未知的 AI 服务商")

    public = _load_file("settings.json")
    private = _load_file("settings.local.json")

    if request_api_key is not None and (
        not isinstance(request_api_key, str) or len(request_api_key) > 1024
    ):
        raise SettingsError("输入的 API Key 格式无效")
    key_from_request = request_api_key.strip() if request_api_key else ""

    if provider == "deepseek":
        key = _first(
            key_from_request,
            _property(private, "deepseek", "api_key"),
            os.environ.get("PAPERPRO_DEEPSEEK_API_KEY", "").strip(),
            _property(public, "deepseek", "api_key"),
        )
        return ProviderSettings(
            provider="deepseek",
            api_key=key,
            base_url=OFFICIAL_DEEPSEEK_URL,
            model=OFFICIAL_DEEPSEEK_MODEL,
        )

    key = _first(
        key_from_request,
        _property(private, "configured", "api_key"),
        os.environ.get("PAPERPRO_OPENAI_API_KEY", "").strip(),
        _property(public, "configured", "api_key"),
    )
    base_url = _first(
        _property(private, "configured", "base_url"),
        os.environ.get("PAPERPRO_OPENAI_BASE_URL", "").strip(),
        _property(public, "configured", "base_url"),
        DEFAULT_CUSTOM_URL,
    )
    model = _first(
        _property(private, "configured", "model"),
        os.environ.get("PAPERPRO_OPENAI_MODEL", "").strip(),
        _property(public, "configured", "model"),
        DEFAULT_CUSTOM_MODEL,
    )
    return ProviderSettings(
        provider="configured",
        api_key=key,
        base_url=base_url,
        model=model,
    )
