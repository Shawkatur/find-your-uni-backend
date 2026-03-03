from __future__ import annotations
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field


DegreeLevel = Literal["bachelor", "master", "phd", "diploma"]


class ProgramOut(BaseModel):
    id: str
    university_id: str
    name: str
    degree_level: str
    field: str
    tuition_usd_per_year: int | None
    duration_years: float | None
    min_requirements: dict
    application_deadline: date | None
    intake_months: list[int] | None
    is_active: bool


class UniversityOut(BaseModel):
    id: str
    name: str
    country: str
    city: str | None
    ranking_qs: int | None
    ranking_the: int | None
    tuition_usd_per_year: int
    acceptance_rate_overall: float | None
    acceptance_rate_bd: float | None
    min_ielts: float | None
    min_toefl: int | None
    min_gpa_percentage: int | None
    scholarships_available: bool
    max_scholarship_pct: int | None
    website: str | None
    data_source: str
    last_updated: datetime
    programs: list[ProgramOut] = []


class UniversityCreate(BaseModel):
    name: str = Field(min_length=2)
    country: str = Field(min_length=2, max_length=2)
    city: str | None = None
    ranking_qs: int | None = None
    ranking_the: int | None = None
    tuition_usd_per_year: int = Field(ge=0)
    acceptance_rate_overall: float | None = Field(None, ge=0, le=100)
    acceptance_rate_bd: float | None = Field(None, ge=0, le=100)
    min_ielts: float | None = Field(None, ge=0, le=9)
    min_toefl: int | None = None
    min_gpa_percentage: int | None = Field(None, ge=0, le=100)
    scholarships_available: bool = False
    max_scholarship_pct: int | None = Field(None, ge=0, le=100)
    website: str | None = None
    data_source: str = "manual"


class UniversityFilter(BaseModel):
    country: str | None = None
    degree_level: DegreeLevel | None = None
    field: str | None = None
    max_tuition: int | None = None
    min_ielts: float | None = None
    scholarships_only: bool = False
    search: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class MatchResultItem(BaseModel):
    university_id: str
    program_id: str
    university_name: str
    program_name: str
    country: str
    tuition_usd_per_year: int | None
    ranking_qs: int | None
    score: float = Field(ge=0, le=1)
    breakdown: dict                  # {ranking, cost_efficiency, bd_acceptance}
    ai_summary: str | None = None    # GPT-generated personalized fit summary
