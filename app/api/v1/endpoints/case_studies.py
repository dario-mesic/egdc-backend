import os
import shutil
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from pydantic import Json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func
from app.db.session import get_session
from app.models.case_study import (
    CaseStudy, Benefit, Address, CaseStudySummaryRead, CaseStudyDetailRead,
    CaseStudyProviderLink, CaseStudyFunderLink, ImageObject, Methodology, Dataset
)
from app.models.organization import Organization
from app.schemas.case_study import CaseStudyCreate

router = APIRouter()

from app.schemas.pagination import PaginatedResponse

@router.get("/", response_model=PaginatedResponse[CaseStudySummaryRead])
async def read_case_studies(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session)
):
    # Calculate offset
    offset = (page - 1) * limit

    # Get total count
    count_query = select(func.count()).select_from(CaseStudy)
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Optimized query for Summary View
    query = select(CaseStudy).options(
        selectinload(CaseStudy.benefits).selectinload(Benefit.unit),
        selectinload(CaseStudy.benefits).selectinload(Benefit.type),
        selectinload(CaseStudy.funding_type),
        # Load Providers with reduced Org info
        selectinload(CaseStudy.is_provided_by).options(
             selectinload(Organization.sector),
             selectinload(Organization.org_type)
        ),
         selectinload(CaseStudy.is_funded_by).options(
             selectinload(Organization.sector),
             selectinload(Organization.org_type)
        ),
        selectinload(CaseStudy.logo),
        selectinload(CaseStudy.addresses)
    ).offset(offset).limit(limit)
    
    result = await session.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )

@router.get("/{id}", response_model=CaseStudyDetailRead)
async def read_case_study(id: int, session: AsyncSession = Depends(get_session)):
    query = select(CaseStudy).where(CaseStudy.id == id).options(
        selectinload(CaseStudy.benefits).selectinload(Benefit.unit),
        selectinload(CaseStudy.benefits).selectinload(Benefit.type),
        selectinload(CaseStudy.addresses),
        selectinload(CaseStudy.tech),
        selectinload(CaseStudy.calc_type),
        selectinload(CaseStudy.funding_type),
        selectinload(CaseStudy.logo),
        selectinload(CaseStudy.methodology).selectinload(Methodology.language),
        selectinload(CaseStudy.dataset).selectinload(Dataset.language),
        # Full deep load for Detail View
        selectinload(CaseStudy.is_provided_by).options(
            selectinload(Organization.sector),
            selectinload(Organization.org_type),
            selectinload(Organization.sub_sectors),
            selectinload(Organization.contact_points)
        ),
        selectinload(CaseStudy.is_funded_by).options(
            selectinload(Organization.sector),
            selectinload(Organization.org_type),
            selectinload(Organization.sub_sectors),
            selectinload(Organization.contact_points)
        ),
        selectinload(CaseStudy.is_used_by).options(
            selectinload(Organization.sector),
            selectinload(Organization.org_type),
            selectinload(Organization.sub_sectors),
            selectinload(Organization.contact_points)
        )
    )
    result = await session.execute(query)
    case_study = result.scalars().first()
    if not case_study:
        raise HTTPException(status_code=404, detail="Case study not found")
    return case_study

# Note: Full POST implementation would require complex input Pydantic models.
# For this task, strict typing is requested. I will implement a simplified creation
# assuming the user sends a structure matching the model.
# In a real app, strict Pydantic CreateSchemas are preferred.

UPLOAD_DIR = "static/uploads"

@router.post("/", response_model=CaseStudyDetailRead)
async def create_case_study(
    metadata: str = Form(...), 
    file_methodology: UploadFile = File(...),
    file_dataset: UploadFile = File(...),
    file_logo: UploadFile = File(...),
    session: AsyncSession = Depends(get_session)
):
    # 1. Validation: Environmental Benefit
    try:
        # For Pydantic V2 use: model_validate_json
        # For Pydantic V1 use: parse_raw
        case_study_data = CaseStudyCreate.model_validate_json(metadata)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON metadata: {str(e)}")
    
    has_environmental = any(b.type_code == "environmental" for b in case_study_data.benefits)
    if not has_environmental:
        raise HTTPException(
            status_code=400, 
            detail="At least one benefit must be of type 'environmental'"
        )

    # 2. File Saving Logic
    media_links = {}
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    files_to_process = [
        ("methodology", file_methodology),
        ("dataset", file_dataset),
        ("logo", file_logo)
    ]
    
    for field_name, file in files_to_process:
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4()}{ext}"
            file_path = os.path.join(UPLOAD_DIR, filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            media_links[field_name] = f"/static/uploads/{filename}"

    # 3. DB Transaction
    async with session.begin():
        # Create Media Objects
        methodology_obj = None
        if "methodology" in media_links:
            methodology_obj = Methodology(
                name=file_methodology.filename, 
                url=media_links["methodology"],
                language_code=case_study_data.methodology_language_code
            )
            session.add(methodology_obj)
        
        dataset_obj = None
        if "dataset" in media_links:
            dataset_obj = Dataset(
                name=file_dataset.filename, 
                url=media_links["dataset"],
                language_code=case_study_data.dataset_language_code
            )
            session.add(dataset_obj)
            
        logo_obj = None
        if "logo" in media_links:
            logo_obj = ImageObject(url=media_links["logo"], alt_text=f"Logo for {case_study_data.title}")
            session.add(logo_obj)
            
        # Flush to get IDs for media objects
        await session.flush()

        # Create Case Study
        db_case_study = CaseStudy(
            title=case_study_data.title,
            short_description=case_study_data.short_description,
            long_description=case_study_data.long_description,
            problem_solved=case_study_data.problem_solved,
            created_date=case_study_data.created_date,
            tech_code=case_study_data.tech_code,
            calc_type_code=case_study_data.calc_type_code,
            funding_type_code=case_study_data.funding_type_code,
            methodology_id=methodology_obj.id if methodology_obj else None,
            dataset_id=dataset_obj.id if dataset_obj else None,
            logo_id=logo_obj.id if logo_obj else None,
        )
        session.add(db_case_study)
        await session.flush()

        # Create Benefits
        for b in case_study_data.benefits:
            benefit = Benefit(**b.model_dump(), case_study_id=db_case_study.id)
            session.add(benefit)
            
        # Create Addresses
        for a in case_study_data.addresses:
            addr = Address(**a.model_dump(), case_study_id=db_case_study.id)
            session.add(addr)
            
        # Create Organization Links
        provider_link = CaseStudyProviderLink(
            case_study_id=db_case_study.id, 
            organization_id=case_study_data.provider_org_id
        )
        session.add(provider_link)
        
        if case_study_data.funder_org_id:
            funder_link = CaseStudyFunderLink(
                case_study_id=db_case_study.id, 
                organization_id=case_study_data.funder_org_id
            )
            session.add(funder_link)

    # Note: session.begin() automatically commits on exit.
    
    # Reload with all relationships for the response_model (CaseStudyDetailRead)
    query = select(CaseStudy).where(CaseStudy.id == db_case_study.id).options(
        selectinload(CaseStudy.benefits).selectinload(Benefit.unit),
        selectinload(CaseStudy.benefits).selectinload(Benefit.type),
        selectinload(CaseStudy.addresses),
        selectinload(CaseStudy.tech),
        selectinload(CaseStudy.calc_type),
        selectinload(CaseStudy.funding_type),
        selectinload(CaseStudy.logo),
        selectinload(CaseStudy.methodology).selectinload(Methodology.language),
        selectinload(CaseStudy.dataset).selectinload(Dataset.language),
        selectinload(CaseStudy.is_provided_by).options(
            selectinload(Organization.sector),
            selectinload(Organization.org_type),
            selectinload(Organization.sub_sectors),
            selectinload(Organization.contact_points)
        ),
        selectinload(CaseStudy.is_funded_by).options(
            selectinload(Organization.sector),
            selectinload(Organization.org_type),
            selectinload(Organization.sub_sectors),
            selectinload(Organization.contact_points)
        ),
        selectinload(CaseStudy.is_used_by).options(
            selectinload(Organization.sector),
            selectinload(Organization.org_type),
            selectinload(Organization.sub_sectors),
            selectinload(Organization.contact_points)
        )
    )
    result = await session.execute(query)
    return result.scalars().first()
