from typing import List
from pydantic import BaseModel

class RefCode(BaseModel):
    code: str
    label: str

    class Config:
        from_attributes = True

class ReferenceDataResponse(BaseModel):
    benefit_types: list[RefCode]
    benefit_units: list[RefCode]
    calculation_types: list[RefCode]
    countries: list[RefCode]
    funding_types: list[RefCode]
    languages: list[RefCode]
    organization_types: list[RefCode]
    sectors: list[RefCode]
    technologies: list[RefCode]
