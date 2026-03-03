from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


DegreeLevel = Literal["bachelor", "master", "phd", "diploma"]


class AcademicHistory(BaseModel):
    ssc_gpa: float | None = None
    hsc_gpa: float | None = None
    bachelor_cgpa: float | None = None
    bachelor_subject: str | None = None
    gpa_percentage: int | None = Field(None, ge=0, le=100)


class TestScores(BaseModel):
    ielts: float | None = Field(None, ge=0, le=9)
    toefl: int | None = Field(None, ge=0, le=120)
    gre: int | None = Field(None, ge=260, le=340)
    gmat: int | None = Field(None, ge=200, le=800)
    sat: int | None = Field(None, ge=400, le=1600)


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = None
    academic_history: AcademicHistory
    test_scores: TestScores = TestScores()
    budget_usd_per_year: int = Field(gt=0)
    preferred_countries: list[str] = Field(default_factory=list, max_length=10)
    preferred_degree: DegreeLevel | None = None
    preferred_fields: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("preferred_countries")
    @classmethod
    def uppercase_countries(cls, v: list[str]) -> list[str]:
        return [c.upper() for c in v]


class StudentUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    academic_history: AcademicHistory | None = None
    test_scores: TestScores | None = None
    budget_usd_per_year: int | None = Field(None, gt=0)
    preferred_countries: list[str] | None = None
    preferred_degree: DegreeLevel | None = None
    preferred_fields: list[str] | None = None


class StudentOut(BaseModel):
    id: str
    user_id: str
    full_name: str
    phone: str | None
    academic_history: dict
    test_scores: dict
    budget_usd_per_year: int
    preferred_countries: list[str]
    preferred_degree: str | None
    preferred_fields: list[str]
    created_at: datetime
    updated_at: datetime
