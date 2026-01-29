from typing import Optional
from pydantic import BaseModel
from .references import RefCode

class OrganizationBase(BaseModel):
    name: str
    description: Optional[str] = None
    website_url: Optional[str] = None

    class Config:
        from_attributes = True

class OrganizationCreate(OrganizationBase):
    sector_code: str
    org_type_code: Optional[str] = None

class OrganizationRead(OrganizationBase):
    id: int
    sector: Optional[RefCode] = None
    org_type: Optional[RefCode] = None
