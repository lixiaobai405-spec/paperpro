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




class PdfRowEvidence(BaseModel):
    """Non-authoritative, bounded PDF coordinate proof for a review hint."""

    source_kind: Literal["native_pdf_text"] = "native_pdf_text"
    page_index: int = Field(ge=0)
    page_number: int = Field(ge=1)
    boxes: dict[str, tuple[float, float, float, float]]

    @model_validator(mode="after")
    def geometry_is_normalized(self):
        if self.page_number != self.page_index + 1 or set(self.boxes) != {
            "date", "employer", "role"
        }:
            raise ValueError("PDF 提示的页码或定位框不一致")
        for coords in self.boxes.values():
            x0, y0, x1, y1 = coords
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError("PDF 坐标必须为有效的 0–1 归一化边界框")
        return self


class HintConfidence(BaseModel):
    """A structural evidence tier, explicitly NOT calibrated probability."""

    tier: Literal["low"] = "low"
    calibrated: Literal[False] = False
    semantic_check: Literal["not_verified"] = "not_verified"
    signals: list[str] = Field(min_length=1)
    missing: list[str] = Field(default_factory=lambda: [
        "independent_role_confirmation"
    ])


class WorkRelationHint(BaseModel):
    """One existing entry, one candidate field, human acceptance required."""

    id: str = Field(min_length=1, max_length=80)
    experience_index: int = Field(ge=0)
    field_path: str
    source_path: str
    source_heading: str = Field(min_length=1, max_length=1024)
    suggested_company: str = Field(min_length=1, max_length=200)
    suggested_role: str = Field(min_length=1, max_length=200)
    status: Literal["unverified"] = "unverified"
    note: str
    evidence: PdfRowEvidence
    confidence: HintConfidence

    @model_validator(mode="after")
    def bound_to_one_existing_field(self):
        if (
            self.field_path != f"experience.{self.experience_index}.role"
            or self.source_path != f"experience.{self.experience_index}.heading"
        ):
            raise ValueError("候选提示必须绑定已存在经历的职位字段")
        return self

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


class RecommendationRequest(BaseModel):
    resume: CandidateResume
    target: Target
    use_ai: bool = False
    ai_consent: bool = False
    ai_provider: Literal["deepseek", "configured"] = "deepseek"
    api_key: str | None = Field(default=None, repr=False, exclude=True)


class StructureRequest(BaseModel):
    resume: CandidateResume
    ai_consent: bool = False
    ai_provider: Literal["deepseek", "configured"] = "deepseek"
    api_key: str | None = Field(default=None, repr=False, exclude=True)


class SelectionRequest(BaseModel):
    report: dict
    selected_ids: list[str] = Field(max_length=100)
    kind: str = "todo"
    format: str = "txt"
