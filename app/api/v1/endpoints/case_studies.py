import os
import uuid
import aiofiles
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func
from app.db.session import get_session
from app.models.case_study import (
    CaseStudy, Benefit, Address, CaseStudySummaryRead, CaseStudyDetailRead,
    CaseStudyProviderLink, CaseStudyFunderLink, ImageObject, Methodology, Dataset,
    MethodologyRead, DatasetRead, BenefitRead, Document, DocumentRead
)
from app.models.organization import Organization, OrganizationDetailRead
from app.models.references import (
    RefTechnology, RefCalculationType, RefFundingType, RefLanguage, 
    RefBenefitUnit, RefBenefitType
)
from app.schemas.case_study import CaseStudyCreate
from app.schemas.pagination import PaginatedResponse
from app.models.user import User, UserRole
from app.api.deps import get_current_user, get_current_active_user

router = APIRouter()

UPLOAD_DIR = "static/uploads"

# --- Helper Functions ---

def get_case_study_loader_options(detailed: bool = False):
    """
    Returns the load options for CaseStudy queries.
    Centralizes the logic to avoid code duplication across endpoints.
    """
    # Base options for all views (Summary & Detail)
    options = [
        selectinload(CaseStudy.benefits).selectinload(Benefit.unit),
        selectinload(CaseStudy.benefits).selectinload(Benefit.type),
        selectinload(CaseStudy.funding_type),
        selectinload(CaseStudy.logo),
        selectinload(CaseStudy.addresses),
        selectinload(CaseStudy.additional_document)
    ]

    if not detailed:
        # Summary view: reduced Org info
        options.extend([
            selectinload(CaseStudy.is_provided_by).options(
                 selectinload(Organization.sector),
                 selectinload(Organization.org_type)
            ),
             selectinload(CaseStudy.is_funded_by).options(
                 selectinload(Organization.sector),
                 selectinload(Organization.org_type)
            ),
        ])
    else:
        # Detail view: Full Org info + Tech/Calc/Links + Method/Dataset
        options.extend([
            selectinload(CaseStudy.tech),
            selectinload(CaseStudy.calc_type),
            selectinload(CaseStudy.methodology).selectinload(Methodology.language),
            selectinload(CaseStudy.dataset).selectinload(Dataset.language),
            # Full Org Trees
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
        ])
    return options

async def fetch_organization_details(session: AsyncSession, org_id: int) -> Optional[Organization]:
    """Helper to fetch a single organization with full details for Preview."""
    if not org_id:
        return None
    query = select(Organization).where(Organization.id == org_id).options(
        selectinload(Organization.sector),
        selectinload(Organization.org_type),
        selectinload(Organization.sub_sectors),
        selectinload(Organization.contact_points)
    )
    res = await session.execute(query)
    return res.scalars().first()

async def save_file_async(file: Optional[UploadFile], upload_dir: str) -> Optional[str]:
    """Helper to save uploaded files asynchronously."""
    if not file or not file.filename:
        return None
    
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(upload_dir, filename)
    
    async with aiofiles.open(file_path, "wb") as out_file:
        while content := await file.read(1024 * 1024):  # 1MB chunks
            await out_file.write(content)
            
    return f"/static/uploads/{filename}"

def validate_case_study_metadata(metadata: str) -> CaseStudyCreate:
    try:
        case_study_data = CaseStudyCreate.model_validate_json(metadata)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON metadata: {str(e)}")

    return case_study_data

# --- Endpoints ---

@router.get("/", response_model=PaginatedResponse[CaseStudySummaryRead])
async def read_case_studies(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session)
):
    offset = (page - 1) * limit

    # Get total count
    count_query = select(func.count()).select_from(CaseStudy)
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Optimized query using helper
    query = select(CaseStudy).options(
        *get_case_study_loader_options(detailed=False)
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
    # Optimized query using helper
    query = select(CaseStudy).where(CaseStudy.id == id).options(
        *get_case_study_loader_options(detailed=True)
    )
    result = await session.execute(query)
    case_study = result.scalars().first()
    if not case_study:
        raise HTTPException(status_code=404, detail="Case study not found")
    return case_study

@router.post("/preview", response_model=CaseStudyDetailRead)
async def preview_case_study(
    metadata: str = Form(...),
    file_methodology: Optional[UploadFile] = File(None),
    file_dataset: Optional[UploadFile] = File(None),
    file_logo: Optional[UploadFile] = File(None),
    file_additional_document: Optional[UploadFile] = File(None),
    session: AsyncSession = Depends(get_session)
):
    # 1. Validation
    case_study_data = validate_case_study_metadata(metadata)

    # 2. Fetch Related Data (Read-Only)
    tech = None
    if case_study_data.tech_code:
        tech = await session.get(RefTechnology, case_study_data.tech_code)
    
    calc_type = None
    if case_study_data.calc_type_code:
        calc_type = await session.get(RefCalculationType, case_study_data.calc_type_code)

    funding_type = None
    if case_study_data.funding_type_code:
        funding_type = await session.get(RefFundingType, case_study_data.funding_type_code)

    # Helper to convert Org ID to List[OrganizationDetailRead]
    async def get_org_read_list(org_id: Optional[int]) -> List[OrganizationDetailRead]:
        if not org_id: return []
        org = await fetch_organization_details(session, org_id)
        return [OrganizationDetailRead.model_validate(org)] if org else []

    provider_orgs = await get_org_read_list(case_study_data.provider_org_id)
    funder_orgs = await get_org_read_list(case_study_data.funder_org_id)

    # Benefits Construction
    benefit_reads = []
    unit_codes = {b.unit_code for b in case_study_data.benefits}
    type_codes = {b.type_code for b in case_study_data.benefits}
    
    units_map = {}
    if unit_codes:
        res = await session.execute(select(RefBenefitUnit).where(RefBenefitUnit.code.in_(unit_codes)))
        units_map = {u.code: u for u in res.scalars().all()}
        
    types_map = {}
    if type_codes:
        res = await session.execute(select(RefBenefitType).where(RefBenefitType.code.in_(type_codes)))
        types_map = {t.code: t for t in res.scalars().all()}

    for i, b in enumerate(case_study_data.benefits):
        benefit_reads.append(
            BenefitRead(
                id=i,  # Dummy ID
                name=b.name,
                value=b.value,
                unit=units_map.get(b.unit_code),
                type=types_map.get(b.type_code)
            )
        )

    # Helper for Preview File Objects
    async def create_preview_media(file_obj, lang_code, name_prefix) -> Tuple[Optional[object], Optional[object]]:
        if not file_obj and not lang_code:
            return None
            
        lang = None
        if lang_code:
            lang = await session.get(RefLanguage, lang_code)
            
        # Create Read model (MethodologyRead/DatasetRead)
        # Note: We return a structure matching the Read schemas
        # Using simple types here as Pydantic will validate
        return {
            "id": 0,
            "name": file_obj.filename if file_obj else f"preview_{name_prefix}.ext",
            "url": f"/static/uploads/preview_{uuid.uuid4()}",
            "language": lang
        }

    meth_read = None
    if file_methodology or case_study_data.methodology_language_code:
        meth_read = await create_preview_media(file_methodology, case_study_data.methodology_language_code, "methodology")
        # Ensure it matches Pydantic model structure if returned as dict, or instantiate object
        if meth_read:
            meth_read = MethodologyRead(**meth_read)

    data_read = None
    if file_dataset or case_study_data.dataset_language_code:
        data_read = await create_preview_media(file_dataset, case_study_data.dataset_language_code, "dataset")
        if data_read:
            data_read = DatasetRead(**data_read)

    logo_obj = None
    if file_logo:
        logo_obj = ImageObject(
            id=0,
            url=f"/static/uploads/preview_logo_{uuid.uuid4()}",
            alt_text=f"Logo for {case_study_data.title}"
        )
    
    additional_doc_read = None
    if file_additional_document or case_study_data.additional_document_id:
        if file_additional_document:
            additional_doc_read = DocumentRead(
                id=0,
                name=file_additional_document.filename,
                url=f"/static/uploads/preview_doc_{uuid.uuid4()}"
            )
        elif case_study_data.additional_document_id:
            db_doc = await session.get(Document, case_study_data.additional_document_id)
            if db_doc:
                additional_doc_read = DocumentRead(
                    id=db_doc.id,
                    name=db_doc.name,
                    url=db_doc.url
                )

    # Addresses
    address_objs = [
        Address(id=i, admin_unit_l1=a.admin_unit_l1, post_name=a.post_name, case_study_id=0)
        for i, a in enumerate(case_study_data.addresses)
    ]

    # Construct Response
    return CaseStudyDetailRead(
        id=0, # Dummy ID
        title=case_study_data.title,
        short_description=case_study_data.short_description,
        long_description=case_study_data.long_description,
        problem_solved=case_study_data.problem_solved,
        created_date=case_study_data.created_date,
        tech_code=case_study_data.tech_code,
        calc_type_code=case_study_data.calc_type_code,
        funding_type_code=case_study_data.funding_type_code,
        
        tech=tech,
        calc_type=calc_type,
        funding_type=funding_type,
        
        logo=logo_obj,
        methodology=meth_read,
        dataset=data_read,
        additional_document=additional_doc_read,
        
        addresses=address_objs,
        benefits=benefit_reads,
        
        is_provided_by=provider_orgs,
        is_funded_by=funder_orgs,
        is_used_by=[]
    )

@router.post("/", response_model=CaseStudyDetailRead)
async def create_case_study(
    metadata: str = Form(...), 
    file_methodology: UploadFile = File(...),
    file_dataset: UploadFile = File(...),
    file_logo: UploadFile = File(...),
    file_additional_document: Optional[UploadFile] = File(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # 1. Validation
    case_study_data = validate_case_study_metadata(metadata)
    
    # 1.1 Strict Business Rules Validation
    
    # Rule 1: Mandatory Net Carbon Impact (Exactly ONE, and type must be environmental)
    net_impact_benefits = [
        b for b in case_study_data.benefits 
        if b.is_net_carbon_impact
    ]
    
    if len(net_impact_benefits) != 1:
        raise HTTPException(
            status_code=422,
            detail="Exactly one benefit must be marked as 'Net Carbon Impact' (is_net_carbon_impact=True)."
        )
        
    if net_impact_benefits[0].type_code != 'environmental':
        raise HTTPException(
            status_code=422,
            detail="The 'Net Carbon Impact' benefit must have type_code='environmental'."
        )

    # Rule 2: Funding URL Validation
    if case_study_data.funding_type_code == 'public' and not case_study_data.funding_programme_url:
        raise HTTPException(
            status_code=422,
            detail="Funding Programme URL is required when Funding Type is 'public'."
        )

    # 1.2 Status & Owner Enforcement
    from app.models.case_study import CaseStudyStatus
    
    initial_status = CaseStudyStatus.DRAFT # Default
    owner_id = current_user.id
    
    if current_user.role == UserRole.DATA_OWNER:
        # Rule 3: Data Owner submission forces Pending Approval
        initial_status = CaseStudyStatus.PENDING_APPROVAL
    
    # 2. File Saving Logic (Async Helper)
    media_links = {}
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    media_links["methodology"] = await save_file_async(file_methodology, UPLOAD_DIR)
    media_links["dataset"] = await save_file_async(file_dataset, UPLOAD_DIR)
    media_links["logo"] = await save_file_async(file_logo, UPLOAD_DIR)
    media_links["additional_document"] = await save_file_async(file_additional_document, UPLOAD_DIR)

    # 3. DB Transaction
    try:
        # Create Media Objects
        methodology_obj = None
        if media_links.get("methodology"):
            methodology_obj = Methodology(
                name=file_methodology.filename, 
                url=media_links["methodology"],
                language_code=case_study_data.methodology_language_code
            )
            session.add(methodology_obj)
        
        dataset_obj = None
        if media_links.get("dataset"):
            dataset_obj = Dataset(
                name=file_dataset.filename, 
                url=media_links["dataset"],
                language_code=case_study_data.dataset_language_code
            )
            session.add(dataset_obj)
            
        logo_obj = None
        if media_links.get("logo"):
            logo_obj = ImageObject(
                url=media_links["logo"], 
                alt_text=f"Logo for {case_study_data.title}"
            )
            session.add(logo_obj)
            
        additional_document_obj = None
        if media_links.get("additional_document"):
            additional_document_obj = Document(
                name=file_additional_document.filename,
                url=media_links["additional_document"]
            )
            session.add(additional_document_obj)
        elif case_study_data.additional_document_id:
            # If a separate document ID was sent instead of a file
            additional_document_obj = await session.get(Document, case_study_data.additional_document_id)
            
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
            funding_programme_url=case_study_data.funding_programme_url,
            methodology_id=methodology_obj.id if methodology_obj else None,
            dataset_id=dataset_obj.id if dataset_obj else None,
            logo_id=logo_obj.id if logo_obj else None,
            additional_document_id=additional_document_obj.id if additional_document_obj else None,
            created_by=owner_id,
            status=initial_status
        )
        session.add(db_case_study)
        await session.flush()

        # Create Children
        for b in case_study_data.benefits:
            session.add(Benefit(**b.model_dump(), case_study_id=db_case_study.id))
            
        for a in case_study_data.addresses:
            session.add(Address(**a.model_dump(), case_study_id=db_case_study.id))
            
        # Links
        session.add(CaseStudyProviderLink(
            case_study_id=db_case_study.id, 
            organization_id=case_study_data.provider_org_id
        ))
        
        if case_study_data.funder_org_id:
            session.add(CaseStudyFunderLink(
                case_study_id=db_case_study.id, 
                organization_id=case_study_data.funder_org_id
            ))

        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    # Re-fetch for response using helper
    query = select(CaseStudy).where(CaseStudy.id == db_case_study.id).options(
        *get_case_study_loader_options(detailed=True)
    )
    result = await session.execute(query)
    return result.scalars().first()