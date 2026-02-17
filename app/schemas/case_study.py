from typing import List, Optional
from datetime import date
from pydantic import BaseModel

class BenefitCreate(BaseModel):
    name: str
    value: int
    unit_code: str
    type_code: str
    functional_unit: Optional[str] = None
    is_net_carbon_impact: bool = False

class AddressCreate(BaseModel):
    admin_unit_l1: str
    post_name: Optional[str] = None

class CaseStudyCreate(BaseModel):
    title: str
    short_description: str
    long_description: Optional[str] = None
    problem_solved: Optional[str] = None
    created_date: Optional[date] = None
    
    tech_code: Optional[str] = None
    calc_type_code: Optional[str] = None
    funding_type_code: Optional[str] = None
    funding_programme_url: Optional[str] = None
    
    benefits: List[BenefitCreate] = []
    addresses: List[AddressCreate] = []
    
    provider_org_id: int
    funder_org_id: Optional[int] = None
    user_org_id: Optional[int] = None

    methodology_language_code: Optional[str] = None
    dataset_language_code: Optional[str] = None
