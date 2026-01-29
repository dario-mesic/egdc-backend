from typing import List, Optional
from datetime import date
from sqlmodel import SQLModel, Field, Relationship
from .references import RefBenefitUnit, RefBenefitType, RefSector, RefTechnology, RefCalculationType, RefFundingType, RefLanguage
from .organization import Organization, OrganizationSummaryRead, OrganizationDetailRead

# --- Entities for One-to-One Relationships ---
class ImageObject(SQLModel, table=True):
    __tablename__ = "image_object"
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str
    alt_text: Optional[str] = None

class Methodology(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    url: Optional[str] = None
    language_code: Optional[str] = Field(default=None, foreign_key="ref_language.code")
    language: Optional[RefLanguage] = Relationship()

class MethodologyRead(SQLModel):
    id: int
    name: str
    url: Optional[str] = None
    language: Optional[RefLanguage] = None

class Dataset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    url: Optional[str] = None
    language_code: Optional[str] = Field(default=None, foreign_key="ref_language.code")
    language: Optional[RefLanguage] = Relationship()

class DatasetRead(SQLModel):
    id: int
    name: str
    url: Optional[str] = None
    language: Optional[RefLanguage] = None

# --- Link Tables for CaseStudy <-> Organization ---
class CaseStudyProviderLink(SQLModel, table=True):
    case_study_id: Optional[int] = Field(default=None, foreign_key="case_study.id", primary_key=True)
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id", primary_key=True)

class CaseStudyFunderLink(SQLModel, table=True):
    case_study_id: Optional[int] = Field(default=None, foreign_key="case_study.id", primary_key=True)
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id", primary_key=True)

class CaseStudyUserLink(SQLModel, table=True):
    case_study_id: Optional[int] = Field(default=None, foreign_key="case_study.id", primary_key=True)
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id", primary_key=True)


# --- Base Model (Shared Fields) ---
class CaseStudyBase(SQLModel):
    title: str
    short_description: str
    long_description: Optional[str] = None
    problem_solved: Optional[str] = None
    created_date: Optional[date] = None

    tech_code: Optional[str] = Field(default=None, foreign_key="ref_technology.code")
    calc_type_code: Optional[str] = Field(default=None, foreign_key="ref_calculation_type.code")
    funding_type_code: Optional[str] = Field(default=None, foreign_key="ref_funding_type.code")

    logo_id: Optional[int] = Field(default=None, foreign_key="image_object.id")
    methodology_id: Optional[int] = Field(default=None, foreign_key="methodology.id")
    dataset_id: Optional[int] = Field(default=None, foreign_key="dataset.id")


# --- Core CaseStudy Model (Table) ---
class CaseStudy(CaseStudyBase, table=True):
    __tablename__ = "case_study"
    id: Optional[int] = Field(default=None, primary_key=True)

    # Key differences: Relationships are defined here for SQLAlchemy
    tech: Optional[RefTechnology] = Relationship()
    calc_type: Optional[RefCalculationType] = Relationship()
    funding_type: Optional[RefFundingType] = Relationship()

    logo: Optional[ImageObject] = Relationship()
    methodology: Optional[Methodology] = Relationship()
    dataset: Optional[Dataset] = Relationship()

    addresses: List["Address"] = Relationship(back_populates="case_study")
    benefits: List["Benefit"] = Relationship(back_populates="case_study")

    is_provided_by: List[Organization] = Relationship(link_model=CaseStudyProviderLink)
    is_funded_by: List[Organization] = Relationship(link_model=CaseStudyFunderLink)
    is_used_by: List[Organization] = Relationship(link_model=CaseStudyUserLink)


# --- Child Models (One-to-Many) ---
class Address(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    admin_unit_l1: str
    post_name: Optional[str] = None
    case_study_id: Optional[int] = Field(default=None, foreign_key="case_study.id")
    case_study: Optional[CaseStudy] = Relationship(back_populates="addresses")

class Benefit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    value: int
    unit_code: str = Field(foreign_key="ref_benefit_unit.code")
    type_code: str = Field(foreign_key="ref_benefit_type.code")
    case_study_id: Optional[int] = Field(default=None, foreign_key="case_study.id")
    case_study: Optional[CaseStudy] = Relationship(back_populates="benefits")

    unit: Optional[RefBenefitUnit] = Relationship()
    type: Optional[RefBenefitType] = Relationship()

class BenefitRead(SQLModel):
    id: int
    name: str
    value: int
    unit: Optional[RefBenefitUnit]
    type: Optional[RefBenefitType]

# --- Read Schemas (Pydantic Response) ---
class CaseStudySummaryRead(SQLModel):
    id: int
    title: str
    short_description: str
    benefits: List[BenefitRead] = []
    
    # Organization Info (Name, Sector)
    is_provided_by: List[OrganizationSummaryRead] = []
    is_funded_by: List[OrganizationSummaryRead] = []
    
    # Funding Type
    funding_type: Optional[RefFundingType] = None
    
    # Logo
    logo: Optional[ImageObject] = None
    
    # Addresses (Country, Post Name)
    addresses: List[Address] = []


class CaseStudyDetailRead(CaseStudyBase):
    id: int
    # Implicitly includes all Base fields: title, short/long desc, problem_soled, tech_code etc.
    
    # Explicitly include nested objects for serialization
    tech: Optional[RefTechnology] = None
    calc_type: Optional[RefCalculationType] = None
    funding_type: Optional[RefFundingType] = None
    
    logo: Optional[ImageObject] = None
    methodology: Optional[MethodologyRead] = None
    dataset: Optional[DatasetRead] = None
    
    addresses: List[Address] = []
    benefits: List[BenefitRead] = [] 
    
    # Full Organization Info including Sub-sectors and Contacts
    is_provided_by: List[OrganizationDetailRead] = []
    is_funded_by: List[OrganizationDetailRead] = []
    is_used_by: List[OrganizationDetailRead] = []
