"""Fixed user-editable candidate schema. Existing classic Resume is unchanged."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.models import Entry, Education, Resume


class CareerEntry(Entry):
    company: str = ""
    role: str = ""
    start_date: str = ""
    end_date: str = ""


class CandidateResume(Resume):
    experience: list[CareerEntry] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    self_evaluation: str = ""
    source_sha256: str = ""
    source_text: str = ""


class Target(BaseModel):
    role: str = Field(default="", max_length=140)
    company: str = Field(default="", max_length=140)
    job_description: str = Field(default="", max_length=12000)

    @model_validator(mode="after")
    def at_least_one(self):
        if not self.role.strip() and not self.company.strip():
            raise ValueError("请至少填写目标职位或目标公司")
        return self


class DiagnosisRequest(BaseModel):
    resume: CandidateResume
    target: Target
    enabled_sections: list[str] | None = None
    as_of: str | None = None
    use_ai: bool = False
    ai_consent: bool = False
    ai_provider: Literal["deepseek","configured"] = "deepseek"
    api_key: str | None = Field(default=None, repr=False, exclude=True)

    @field_validator("enabled_sections")
    @classmethod
    def validate_enabled(cls, value):
        if value is not None and (
            len(set(value)) != len(value) or
            any(item not in {"match", "experience", "potential", "motivation", "verification"} for item in value)
        ):
            raise ValueError("未知或重复的诊断维度")
        return value


class PasteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)


class SelectionRequest(BaseModel):
    report: dict
    selected_ids: list[str] = Field(max_length=100)
    kind: str = "todo"
    format: str = "txt"
