from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Entry(BaseModel):
    heading: str = ""
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    heading: str = ""
    details: list[str] = Field(default_factory=list)


class Resume(BaseModel):
    name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Entry] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[Entry] = Field(default_factory=list)
    additional: list[str] = Field(default_factory=list)


class EnhanceRequest(BaseModel):
    resume: Resume
    use_ai: bool = False
    provider: Literal['configured', 'deepseek'] = 'configured'
    api_key: str | None = Field(default=None, repr=False, exclude=True)
    target_role: str = ""
    job_description: str = ""


class ExportRequest(BaseModel):
    resume: Resume
