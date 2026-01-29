from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

class RefBase(SQLModel):
    code: str = Field(primary_key=True)
    label: str

class RefSector(RefBase, table=True):
    __tablename__ = "ref_sector"

class RefOrganizationType(RefBase, table=True):
    __tablename__ = "ref_organization_type"

class RefFundingType(RefBase, table=True):
    __tablename__ = "ref_funding_type"

class RefCalculationType(RefBase, table=True):
    __tablename__ = "ref_calculation_type"

class RefBenefitUnit(RefBase, table=True):
    __tablename__ = "ref_benefit_unit"

class RefBenefitType(RefBase, table=True):
    __tablename__ = "ref_benefit_type"

class RefTechnology(RefBase, table=True):
    __tablename__ = "ref_technology"

class RefCountry(RefBase, table=True):
    __tablename__ = "ref_country"

class RefLanguage(RefBase, table=True):
    __tablename__ = "ref_language"
