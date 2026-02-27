import os
import uuid
import aiofiles
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func, delete
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
from app.models.case_study import CaseStudyStatus
from app.schemas.case_study import CaseStudyCreate, CaseStudyStatusUpdate, CaseStudyStatusUpdate
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
    """Public endpoint — only returns PUBLISHED case studies."""
    offset = (page - 1) * limit

    # Get total count (published only)
    count_query = select(func.count()).select_from(CaseStudy).where(
        CaseStudy.status == CaseStudyStatus.PUBLISHED
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch published case studies only
    query = select(CaseStudy).where(
        CaseStudy.status == CaseStudyStatus.PUBLISHED
    ).options(
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


@router.get("/pending", response_model=PaginatedResponse[CaseStudySummaryRead])
async def read_pending_case_studies(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Custodian dashboard — returns all PENDING_APPROVAL case studies."""
    if current_user.role not in [UserRole.ADMIN, UserRole.CUSTODIAN]:
        raise HTTPException(
            status_code=403,
            detail="Only Custodians and Admins can access the pending review queue."
        )

    offset = (page - 1) * limit

    count_query = select(func.count()).select_from(CaseStudy).where(
        CaseStudy.status == CaseStudyStatus.PENDING_APPROVAL
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    query = select(CaseStudy).where(
        CaseStudy.status == CaseStudyStatus.PENDING_APPROVAL
    ).options(
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
    methodology_language: Optional[str] = Form(None),
    dataset_language: Optional[str] = Form(None),
    additional_document_language: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session)
) -> CaseStudyDetailRead:
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

    # Filter incomplete benefits for preview (BenefitRead requires name)
    for i, b in enumerate(b for b in case_study_data.benefits if b.name and b.unit_code and b.type_code):
        benefit_reads.append(
            BenefitRead(
                id=i,  # Dummy ID
                name=b.name,
                value=b.value,
                functional_unit=b.functional_unit,
                is_net_carbon_impact=b.is_net_carbon_impact,
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
    meth_lang = methodology_language or case_study_data.methodology_language
    if file_methodology or meth_lang:
        meth_read = await create_preview_media(file_methodology, meth_lang, "methodology")
        if meth_read:
            meth_read = MethodologyRead(**meth_read)

    data_read = None
    data_lang = dataset_language or case_study_data.dataset_language
    if file_dataset or data_lang:
        data_read = await create_preview_media(file_dataset, data_lang, "dataset")
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
    add_doc_lang = additional_document_language or case_study_data.additional_document_language
    if file_additional_document or add_doc_lang or case_study_data.additional_document_id:
        if file_additional_document:
            lang = None
            if add_doc_lang:
                lang = await session.get(RefLanguage, add_doc_lang)
            additional_doc_read = DocumentRead(
                id=0,
                name=file_additional_document.filename,
                url=f"/static/uploads/preview_doc_{uuid.uuid4()}",
                language=lang
            )
        elif case_study_data.additional_document_id:
            db_doc = await session.get(Document, case_study_data.additional_document_id)
            if db_doc:
                additional_doc_read = DocumentRead(
                    id=db_doc.id,
                    name=db_doc.name,
                    url=db_doc.url,
                    language=db_doc.language
                )

    # Addresses (filter incomplete for preview - Address model requires admin_unit_l1)
    address_objs = [
        Address(id=i, admin_unit_l1=a.admin_unit_l1, post_name=a.post_name, case_study_id=0)
        for i, a in enumerate(a for a in case_study_data.addresses if a.admin_unit_l1)
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
        funding_programme_url=case_study_data.funding_programme_url,
        
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
    file_methodology: Optional[UploadFile] = File(None),
    file_dataset: Optional[UploadFile] = File(None),
    file_logo: Optional[UploadFile] = File(None),
    file_additional_document: Optional[UploadFile] = File(None),
    methodology_language: Optional[str] = Form(None),
    dataset_language: Optional[str] = Form(None),
    additional_document_language: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> CaseStudyDetailRead:
    # 1. Validation
    case_study_data = validate_case_study_metadata(metadata)
    
    initial_status = CaseStudyStatus.DRAFT
    if case_study_data.status in ["pending_approval", CaseStudyStatus.PENDING_APPROVAL.value]:
        initial_status = CaseStudyStatus.PENDING_APPROVAL
    elif case_study_data.status in ["published", CaseStudyStatus.PUBLISHED.value]:
        if current_user.role in [UserRole.ADMIN, UserRole.CUSTODIAN]:
            initial_status = CaseStudyStatus.PUBLISHED
        else:
            initial_status = CaseStudyStatus.PENDING_APPROVAL
            
    # 1.1 Strict Business Rules Validation
    if initial_status in [CaseStudyStatus.PENDING_APPROVAL, CaseStudyStatus.PUBLISHED]:
        # Check mandatory fields
        if not case_study_data.title or not case_study_data.short_description or not case_study_data.provider_org_id:
            raise HTTPException(
                status_code=422, 
                detail="Title, short description, and provider organization are required for pending approval status."
            )
            
        if not case_study_data.addresses or len(case_study_data.addresses) == 0:
            raise HTTPException(
                status_code=422,
                detail="At least one address is required for pending approval status."
            )

        # Each address must have country (admin_unit_l1) when submitting for approval
        for i, a in enumerate(case_study_data.addresses):
            if not a.admin_unit_l1 or (isinstance(a.admin_unit_l1, str) and not a.admin_unit_l1.strip()):
                raise HTTPException(
                    status_code=422,
                    detail=f"Address at index {i} must have a country (admin_unit_l1) when submitting for approval."
                )

        if not file_methodology or not file_dataset or not file_logo:
             raise HTTPException(
                status_code=422,
                detail="Methodology, Dataset, and Logo files are required for pending approval status."
            )

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

        # All benefits must have required fields when submitting for approval
        for i, b in enumerate(case_study_data.benefits):
            if not b.name or not b.unit_code or not b.type_code:
                raise HTTPException(
                    status_code=422,
                    detail=f"Benefit at index {i} must have name, unit_code, and type_code when submitting for approval."
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
    owner_id = current_user.id
    
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
        meth_lang = methodology_language or case_study_data.methodology_language or "en"
        if media_links.get("methodology"):
            methodology_obj = Methodology(
                name=file_methodology.filename, 
                url=media_links["methodology"],
                language_code=meth_lang
            )
            session.add(methodology_obj)
        
        dataset_obj = None
        data_lang = dataset_language or case_study_data.dataset_language or "en"
        if media_links.get("dataset"):
            dataset_obj = Dataset(
                name=file_dataset.filename, 
                url=media_links["dataset"],
                language_code=data_lang
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
        add_doc_lang = additional_document_language or case_study_data.additional_document_language or "en"
        if media_links.get("additional_document"):
            additional_document_obj = Document(
                name=file_additional_document.filename,
                url=media_links["additional_document"],
                language_code=add_doc_lang
            )
            session.add(additional_document_obj)
        elif case_study_data.additional_document_id:
            # If a separate document ID was sent instead of a file
            additional_document_obj = await session.get(Document, case_study_data.additional_document_id)
            if additional_document_obj and add_doc_lang:
                additional_document_obj.language_code = add_doc_lang
                session.add(additional_document_obj)
            
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
        # Only persist benefits with required fields (draft can have incomplete benefits)
        for b in case_study_data.benefits:
            if b.name and b.unit_code and b.type_code:
                session.add(Benefit(**b.model_dump(), case_study_id=db_case_study.id))
            
        # Only persist addresses with admin_unit_l1 (draft can have incomplete addresses)
        for a in case_study_data.addresses:
            if a.admin_unit_l1:
                session.add(Address(**a.model_dump(), case_study_id=db_case_study.id))
            
        # Links
        if case_study_data.provider_org_id:
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

@router.put("/{id}", response_model=CaseStudyDetailRead)
async def update_case_study(
    id: int,
    metadata: str = Form(...), 
    file_methodology: Optional[UploadFile] = File(None),
    file_dataset: Optional[UploadFile] = File(None),
    file_logo: Optional[UploadFile] = File(None),
    file_additional_document: Optional[UploadFile] = File(None),
    methodology_language: Optional[str] = Form(None),
    dataset_language: Optional[str] = Form(None),
    additional_document_language: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> CaseStudyDetailRead:
    # Fetch existing
    query = select(CaseStudy).where(CaseStudy.id == id).options(
        *get_case_study_loader_options(detailed=True)
    )
    result = await session.execute(query)
    db_case_study = result.scalars().first()
    
    if not db_case_study:
        raise HTTPException(status_code=404, detail="Case study not found")
        
    if db_case_study.created_by != current_user.id and current_user.role not in [UserRole.ADMIN, UserRole.CUSTODIAN]:
        raise HTTPException(status_code=403, detail="Not authorized to edit this case study")
        
    # Validation
    case_study_data = validate_case_study_metadata(metadata)
    
    new_status = CaseStudyStatus.DRAFT
    if case_study_data.status in ["pending_approval", CaseStudyStatus.PENDING_APPROVAL.value]:
        new_status = CaseStudyStatus.PENDING_APPROVAL
    elif case_study_data.status in ["published", CaseStudyStatus.PUBLISHED.value]:
        if current_user.role in [UserRole.ADMIN, UserRole.CUSTODIAN]:
            new_status = CaseStudyStatus.PUBLISHED
        else:
            new_status = CaseStudyStatus.PENDING_APPROVAL
            
    # File logic — must happen BEFORE validation so media_links is available for approval checks
    media_links = {}
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    media_links["methodology"] = await save_file_async(file_methodology, UPLOAD_DIR)
    media_links["dataset"] = await save_file_async(file_dataset, UPLOAD_DIR)
    media_links["logo"] = await save_file_async(file_logo, UPLOAD_DIR)
    media_links["additional_document"] = await save_file_async(file_additional_document, UPLOAD_DIR)

    # Strict validation if submitting for approval
    if new_status in [CaseStudyStatus.PENDING_APPROVAL, CaseStudyStatus.PUBLISHED]:
        if not case_study_data.title or not case_study_data.short_description or not case_study_data.provider_org_id:
            raise HTTPException(
                status_code=422, 
                detail="Title, short description, and provider organization are required for pending approval status."
            )

        if not case_study_data.addresses or len(case_study_data.addresses) == 0:
            raise HTTPException(
                status_code=422,
                detail="At least one address is required for pending approval status."
            )

        # Each address must have country (admin_unit_l1) when submitting for approval
        for i, a in enumerate(case_study_data.addresses):
            if not a.admin_unit_l1 or (isinstance(a.admin_unit_l1, str) and not a.admin_unit_l1.strip()):
                raise HTTPException(
                    status_code=422,
                    detail=f"Address at index {i} must have a country (admin_unit_l1) when submitting for approval."
                )

        net_impact_benefits = [
            b for b in case_study_data.benefits 
            if b.is_net_carbon_impact
        ]
        if len(net_impact_benefits) != 1:
            raise HTTPException(status_code=422, detail="Exactly one benefit must be marked as 'Net Carbon Impact'.")

        # All benefits must have required fields when submitting for approval
        for i, b in enumerate(case_study_data.benefits):
            if not b.name or not b.unit_code or not b.type_code:
                raise HTTPException(
                    status_code=422,
                    detail=f"Benefit at index {i} must have name, unit_code, and type_code when submitting for approval."
                )

        if net_impact_benefits[0].type_code != 'environmental':
            raise HTTPException(status_code=422, detail="The 'Net Carbon Impact' benefit must have type_code='environmental'.")
        if case_study_data.funding_type_code == 'public' and not case_study_data.funding_programme_url:
            raise HTTPException(status_code=422, detail="Funding Programme URL is required when Funding Type is 'public'.")
            
        # Ensure files exist (either in this request or already in DB)
        has_meth = media_links.get("methodology") or db_case_study.methodology_id
        has_data = media_links.get("dataset") or db_case_study.dataset_id
        has_logo = media_links.get("logo") or db_case_study.logo_id
        
        if not has_meth or not has_data or not has_logo:
            raise HTTPException(
                status_code=422,
                detail="Methodology, Dataset, and Logo are required to submit for approval."
            )

    try:
        if media_links.get("methodology"):
            meth_lang = methodology_language or case_study_data.methodology_language or "en"
            meth_obj = Methodology(name=file_methodology.filename, url=media_links["methodology"], language_code=meth_lang)
            session.add(meth_obj)
            await session.flush()
            db_case_study.methodology_id = meth_obj.id

        if media_links.get("dataset"):
            data_lang = dataset_language or case_study_data.dataset_language or "en"
            data_obj = Dataset(name=file_dataset.filename, url=media_links["dataset"], language_code=data_lang)
            session.add(data_obj)
            await session.flush()
            db_case_study.dataset_id = data_obj.id

        if media_links.get("logo"):
            logo_obj = ImageObject(url=media_links["logo"], alt_text=f"Logo for {case_study_data.title}")
            session.add(logo_obj)
            await session.flush()
            db_case_study.logo_id = logo_obj.id

        if media_links.get("additional_document"):
            add_doc_lang = additional_document_language or case_study_data.additional_document_language or "en"
            add_doc_obj = Document(name=file_additional_document.filename, url=media_links["additional_document"], language_code=add_doc_lang)
            session.add(add_doc_obj)
            await session.flush()
            db_case_study.additional_document_id = add_doc_obj.id
        elif case_study_data.additional_document_id:
            add_doc_lang = additional_document_language or case_study_data.additional_document_language
            db_case_study.additional_document_id = case_study_data.additional_document_id
            if add_doc_lang:
                doc_obj = await session.get(Document, case_study_data.additional_document_id)
                if doc_obj:
                    doc_obj.language_code = add_doc_lang
                    session.add(doc_obj)

        # Update metadata
        db_case_study.title = case_study_data.title
        db_case_study.short_description = case_study_data.short_description
        db_case_study.long_description = case_study_data.long_description
        db_case_study.problem_solved = case_study_data.problem_solved
        db_case_study.created_date = case_study_data.created_date
        db_case_study.tech_code = case_study_data.tech_code
        db_case_study.calc_type_code = case_study_data.calc_type_code
        db_case_study.funding_type_code = case_study_data.funding_type_code
        db_case_study.funding_programme_url = case_study_data.funding_programme_url
        
        # Status upgrade processing
        db_case_study.status = new_status
        if new_status in [CaseStudyStatus.PENDING_APPROVAL, CaseStudyStatus.PUBLISHED]:
            db_case_study.rejection_comment = None

        # Overwrite relations (Benefits, Addresses, Links)
        await session.execute(delete(Benefit).where(Benefit.case_study_id == id))
        await session.execute(delete(Address).where(Address.case_study_id == id))
        await session.execute(delete(CaseStudyProviderLink).where(CaseStudyProviderLink.case_study_id == id))
        await session.execute(delete(CaseStudyFunderLink).where(CaseStudyFunderLink.case_study_id == id))
        await session.flush()

        # Only persist benefits with required fields (draft can have incomplete benefits)
        for b in case_study_data.benefits:
            if b.name and b.unit_code and b.type_code:
                session.add(Benefit(**b.model_dump(), case_study_id=id))
            
        # Only persist addresses with admin_unit_l1 (draft can have incomplete addresses)
        for a in case_study_data.addresses:
            if a.admin_unit_l1:
                session.add(Address(**a.model_dump(), case_study_id=id))
            
        if case_study_data.provider_org_id:
            session.add(CaseStudyProviderLink(case_study_id=id, organization_id=case_study_data.provider_org_id))
        
        if case_study_data.funder_org_id:
            session.add(CaseStudyFunderLink(case_study_id=id, organization_id=case_study_data.funder_org_id))

        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    # Return refreshed
    query = select(CaseStudy).where(CaseStudy.id == id).options(*get_case_study_loader_options(detailed=True))
    result = await session.execute(query)
    return result.scalars().first()


@router.patch("/{id}/review", response_model=CaseStudyDetailRead)
async def review_case_study(
    id: int,
    status_update: CaseStudyStatusUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.CUSTODIAN]:
        raise HTTPException(status_code=403, detail="Not authorized to review case studies")
        
    query = select(CaseStudy).where(CaseStudy.id == id).options(*get_case_study_loader_options(detailed=True))
    result = await session.execute(query)
    db_case_study = result.scalars().first()
    
    if not db_case_study:
        raise HTTPException(status_code=404, detail="Case study not found")

    new_status_str = status_update.status
    if new_status_str in ["published", CaseStudyStatus.PUBLISHED.value, "approved"]:
        db_case_study.status = CaseStudyStatus.PUBLISHED
        db_case_study.rejection_comment = None
    elif new_status_str in ["draft", "declined", CaseStudyStatus.DECLINED.value]:
        db_case_study.status = CaseStudyStatus.DRAFT
        db_case_study.rejection_comment = status_update.rejection_comment
    else:
        raise HTTPException(status_code=422, detail="Invalid review status.")

    await session.commit()
    
    query = select(CaseStudy).where(CaseStudy.id == id).options(*get_case_study_loader_options(detailed=True))
    result = await session.execute(query)
    return result.scalars().first()


@router.delete("/{id}", status_code=204)
async def delete_case_study(
    id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a case study by ID.

    - Admin / Custodian: can delete ANY case study.
    - Data Owner: can ONLY delete their OWN case study when it is in 'draft' status.
      Attempting to delete someone else's study, or one in 'pending_approval' /
      'published' status, raises 403.
    """
    # 1. Fetch the case study first so we can enforce ownership rules
    query = select(CaseStudy).where(CaseStudy.id == id)
    result = await session.execute(query)
    case_study = result.scalars().first()

    if not case_study:
        raise HTTPException(status_code=404, detail="Case study not found")

    # 2. RBAC check
    if current_user.role in [UserRole.ADMIN, UserRole.CUSTODIAN]:
        # Privileged roles: no further restrictions
        pass
    elif current_user.role == UserRole.DATA_OWNER:
        # Data Owner: must own the study AND it must still be a draft
        if case_study.created_by != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to delete another user's case study."
            )
        if case_study.status != CaseStudyStatus.DRAFT:
            raise HTTPException(
                status_code=403,
                detail="You can only delete your own case studies while they are in 'draft' status."
            )
    else:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # 3. Cascade-delete children and link rows, then the case study itself
    try:
        await session.execute(delete(Benefit).where(Benefit.case_study_id == id))
        await session.execute(delete(Address).where(Address.case_study_id == id))
        await session.execute(delete(CaseStudyProviderLink).where(CaseStudyProviderLink.case_study_id == id))
        await session.execute(delete(CaseStudyFunderLink).where(CaseStudyFunderLink.case_study_id == id))
        await session.flush()

        await session.delete(case_study)
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return Response(status_code=204)
