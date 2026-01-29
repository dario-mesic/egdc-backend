from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func
from app.db.session import get_session
from app.models.organization import Organization
from app.models.references import RefSector, RefOrganizationType
from app.schemas.organization import OrganizationCreate, OrganizationRead

router = APIRouter()

@router.get("/", response_model=List[OrganizationRead])
async def read_organizations(
    q: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    query = select(Organization).options(
        selectinload(Organization.sector),
        selectinload(Organization.org_type)
    )
    if q:
        query = query.where(Organization.name.ilike(f"%{q}%"))
    
    result = await session.execute(query)
    return result.scalars().all()

@router.post("/", response_model=OrganizationRead)
async def create_organization(
    org_in: OrganizationCreate,
    session: AsyncSession = Depends(get_session)
):
    # Check if organization with same name exists
    existing_org = await session.execute(
        select(Organization).where(func.lower(Organization.name) == org_in.name.lower())
    )
    if existing_org.scalars().first():
        raise HTTPException(status_code=400, detail="Organization with this name already exists")

    # Validate sector exists
    sector = await session.execute(
        select(RefSector).where(RefSector.code == org_in.sector_code)
    )
    if not sector.scalars().first():
        raise HTTPException(status_code=400, detail=f"Sector with code '{org_in.sector_code}' does not exist")

    # Validate org_type exists if provided
    if org_in.org_type_code:
        org_type = await session.execute(
            select(RefOrganizationType).where(RefOrganizationType.code == org_in.org_type_code)
        )
        if not org_type.scalars().first():
            raise HTTPException(status_code=400, detail=f"Organization type with code '{org_in.org_type_code}' does not exist")

    # Create new organization
    db_org = Organization(**org_in.model_dump())
    session.add(db_org)
    await session.commit()
    await session.refresh(db_org)

    # Reload with relationships
    query = select(Organization).where(Organization.id == db_org.id).options(
        selectinload(Organization.sector),
        selectinload(Organization.org_type)
    )
    result = await session.execute(query)
    return result.scalars().first()
