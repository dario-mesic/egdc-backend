import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_session
from app.models.references import (
    RefSector, RefTechnology, RefFundingType, RefCalculationType,
    RefBenefitType, RefBenefitUnit, RefOrganizationType, RefCountry, RefLanguage
)
from app.schemas.references import ReferenceDataResponse, RefCode

router = APIRouter()

@router.get("/", response_model=ReferenceDataResponse)
async def get_reference_data(session: AsyncSession = Depends(get_session)):
    """
    Fetch all reference data for frontend dropdowns in a single request.
    Returns all filters alphabetically sorted with their values also sorted alphabetically.
    """
    # Execute queries sequentially to avoid IllegalStateChangeError 
    # (AsyncSession is not designed for concurrent execute calls)
    benefit_types = await session.execute(select(RefBenefitType))
    benefit_units = await session.execute(select(RefBenefitUnit))
    calculation_types = await session.execute(select(RefCalculationType))
    countries = await session.execute(select(RefCountry))
    funding_types = await session.execute(select(RefFundingType))
    languages = await session.execute(select(RefLanguage))
    organization_types = await session.execute(select(RefOrganizationType))
    sectors = await session.execute(select(RefSector))
    technologies = await session.execute(select(RefTechnology))
    
    # Convert to RefCode and sort alphabetically by label
    def sort_ref_codes(rows):
        codes = [RefCode.model_validate(row) for row in rows.scalars().all()]
        return sorted(codes, key=lambda x: x.label.lower())
    
    return ReferenceDataResponse(
        benefit_types=sort_ref_codes(benefit_types),
        benefit_units=sort_ref_codes(benefit_units),
        calculation_types=sort_ref_codes(calculation_types),
        countries=sort_ref_codes(countries),
        funding_types=sort_ref_codes(funding_types),
        languages=sort_ref_codes(languages),
        organization_types=sort_ref_codes(organization_types),
        sectors=sort_ref_codes(sectors),
        technologies=sort_ref_codes(technologies),
    )
