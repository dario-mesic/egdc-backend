from typing import List, Optional
from sqlmodel import SQLModel, Field, Relationship
from .references import RefSector, RefOrganizationType

# Link Table for Many-to-Many Organization <-> Sub-Sectors
class OrganizationSectorLink(SQLModel, table=True):
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id", primary_key=True)
    sector_code: Optional[str] = Field(default=None, foreign_key="ref_sector.code", primary_key=True)

class ContactPoint(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    has_email: str  
    
    organization_id: int = Field(foreign_key="organization.id")
    organization: Optional["Organization"] = Relationship(back_populates="contact_points")

class OrganizationBase(SQLModel):
    name: str
    description: Optional[str] = None
    website_url: Optional[str] = None
    sector_code: str = Field(foreign_key="ref_sector.code")
    org_type_code: str = Field(foreign_key="ref_organization_type.code")

class Organization(OrganizationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relationships
    sector: Optional[RefSector] = Relationship()
    org_type: Optional[RefOrganizationType] = Relationship()
    
    sub_sectors: List[RefSector] = Relationship(link_model=OrganizationSectorLink)
    contact_points: List["ContactPoint"] = Relationship(back_populates="organization")

# Schema for Reading (includes nested)
class OrganizationSummaryRead(SQLModel):
    id: int
    name: str
    sector: Optional[RefSector] = None
    org_type: Optional[RefOrganizationType] = None

class OrganizationDetailRead(OrganizationBase):
    id: int
    sector: Optional[RefSector] = None
    org_type: Optional[RefOrganizationType] = None
    sub_sectors: List[RefSector] = []
    contact_points: List[ContactPoint] = []
