from typing import List, Optional
from datetime import date
from pydantic import BaseModel, field_validator


def _empty_str_to_none(v: Optional[str]) -> Optional[str]:
    """Coerce empty strings to None so FK-backed code fields store NULL, not ''."""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class BenefitCreate(BaseModel):
    """All fields optional for draft; required when status is pending_approval/published."""
    name: Optional[str] = None
    value: Optional[int] = None
    unit_code: Optional[str] = None
    type_code: Optional[str] = None
    functional_unit: Optional[str] = None
    is_net_carbon_impact: bool = False

    @field_validator("functional_unit", "value", "unit_code", "type_code", "name", mode="before")
    @classmethod
    def coerce_empty_str(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class AddressCreate(BaseModel):
    """All fields optional for draft; admin_unit_l1 required when status is pending_approval/published."""
    admin_unit_l1: Optional[str] = None
    post_name: Optional[str] = None

    @field_validator("post_name", "admin_unit_l1", mode="before")
    @classmethod
    def coerce_empty_str(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class CaseStudyCreate(BaseModel):
    title: Optional[str] = None
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    problem_solved: Optional[str] = None
    created_date: Optional[date] = None

    status: Optional[str] = "draft"

    tech_code: Optional[str] = None
    calc_type_code: Optional[str] = None
    funding_type_code: Optional[str] = None
    funding_programme_url: Optional[str] = None

    benefits: List[BenefitCreate] = []
    addresses: List[AddressCreate] = []

    provider_org_id: Optional[int] = None
    funder_org_id: Optional[int] = None
    user_org_id: Optional[int] = None

    methodology_language: Optional[str] = None
    dataset_language: Optional[str] = None
    additional_document_language: Optional[str] = None
    additional_document_id: Optional[int] = None

    # Coerce "" → None for every Optional field so the DB receives NULL
    # instead of an empty string that would violate FK constraints or cause type errors.
    @field_validator(
        "title", "short_description", "long_description", "problem_solved",
        "status", "tech_code", "calc_type_code", "funding_type_code",
        "funding_programme_url", "methodology_language", "dataset_language",
        "additional_document_language", "provider_org_id", "funder_org_id",
        "user_org_id", "additional_document_id", "created_date",
        mode="before",
    )
    @classmethod
    def coerce_empty_str(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class CaseStudyStatusUpdate(BaseModel):
    status: str
    rejection_comment: Optional[str] = None

