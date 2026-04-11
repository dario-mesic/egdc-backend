import re
import logging
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, cast, String, func
from sqlalchemy.orm import selectinload
from app.db.session import get_session
from app.models.case_study import CaseStudy, Address, Benefit, CaseStudySummaryRead, CaseStudyProviderLink, CaseStudyStatus
from app.models.references import (
    RefSector, RefFundingType, RefTechnology, RefCalculationType,
    RefBenefitType, RefBenefitUnit, RefOrganizationType, RefCountry
)
from app.models.organization import Organization, ContactPoint
from app.schemas.pagination import PaginatedResponse, SearchPaginatedResponse
from app.schemas.facets import SearchFacets, FacetItem

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=SearchPaginatedResponse[CaseStudySummaryRead])
async def search_case_studies(
    # Exact Match Filters
    # Multi-select Filters
    sectors: Optional[List[str]] = Query(None, alias="sector"),
    tech_codes: Optional[List[str]] = Query(None, alias="tech_code"),
    funding_type_codes: Optional[List[str]] = Query(None, alias="funding_type_code"),
    calc_type_codes: Optional[List[str]] = Query(None, alias="calc_type_code"),
    countries: Optional[List[str]] = Query(None, alias="country"),
    
    # New Filters
    organization_types: Optional[List[str]] = Query(None),
    benefit_units: Optional[List[str]] = Query(None),
    benefit_types: Optional[List[str]] = Query(None),
    
    # Sorting
    sort_by: Literal['created_date', 'title'] = Query('created_date'),
    sort_order: Literal['asc', 'desc'] = Query('desc'),

    # Free Text Search
    q: Optional[str] = None,
    
    # Pagination
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    
    session: AsyncSession = Depends(get_session)
):
    # Base query for data
    # PUBLIC ENDPOINT RULE: Search only returns PUBLISHED case studies
    data_query = select(CaseStudy).where(CaseStudy.status == CaseStudyStatus.PUBLISHED)

    # Track which joins have already been applied to prevent "duplicate table" errors
    # when a filter and the free-text `q` block both need the same table.
    _joined_providers = False   # Organization via CaseStudy.is_provided_by
    _joined_ref_sector = False  # RefSector (via sub_sectors M2M or direct FK)
    _joined_addresses = False   # Address via CaseStudy.addresses
    _joined_benefits = False    # Benefit via CaseStudy.benefits

    # --- Exact Filters (Multi-select) ---

    if sectors:
        data_query = data_query.join(CaseStudy.is_provided_by).outerjoin(Organization.sub_sectors).where(
            or_(
                Organization.sector_code.in_(sectors),
                RefSector.code.in_(sectors)
            )
        )
        _joined_providers = True
        _joined_ref_sector = True  # RefSector joined transitively via sub_sectors M2M

    if tech_codes:
        data_query = data_query.where(CaseStudy.tech_code.in_(tech_codes))

    if funding_type_codes:
        data_query = data_query.where(CaseStudy.funding_type_code.in_(funding_type_codes))

    if calc_type_codes:
        data_query = data_query.where(CaseStudy.calc_type_code.in_(calc_type_codes))

    if countries:
        data_query = data_query.join(CaseStudy.addresses).where(Address.admin_unit_l1.in_(countries))
        _joined_addresses = True

    # --- New Multi-select Filters ---

    if organization_types:
        if not _joined_providers:
            data_query = data_query.join(CaseStudy.is_provided_by)
            _joined_providers = True
        data_query = data_query.where(Organization.org_type_code.in_(organization_types))

    if benefit_units:
        data_query = data_query.join(CaseStudy.benefits).where(Benefit.unit_code.in_(benefit_units))
        _joined_benefits = True

    if benefit_types:
        if not _joined_benefits:
            data_query = data_query.join(CaseStudy.benefits)
            _joined_benefits = True
        data_query = data_query.where(Benefit.type_code.in_(benefit_types))

    # --- Free Text Search (q) ---
    if q:
        # Only add joins for tables not already in the FROM clause via a filter above.
        # Mixing a prior INNER JOIN with a duplicate OUTER JOIN on the same table causes
        # a SQLAlchemy "Ambiguous column / duplicate table" error.
        if not _joined_providers:
            data_query = data_query.outerjoin(CaseStudy.is_provided_by, full=False)

        # These join FROM Organization → always safe since Organization is now in scope
        data_query = data_query \
            .outerjoin(Organization.org_type, full=False) \
            .outerjoin(Organization.contact_points, full=False)

        # RefSector via direct FK — skip if already joined transitively via sub_sectors
        if not _joined_ref_sector:
            data_query = data_query.outerjoin(Organization.sector, full=False)

        if not _joined_benefits:
            data_query = data_query.outerjoin(CaseStudy.benefits, full=False)

        # These join FROM Benefit → always safe since Benefit is now in scope
        data_query = data_query \
            .outerjoin(Benefit.type, full=False) \
            .outerjoin(Benefit.unit, full=False) \
            .outerjoin(CaseStudy.funding_type, full=False) \
            .outerjoin(CaseStudy.tech, full=False) \
            .outerjoin(CaseStudy.calc_type, full=False)

        if not _joined_addresses:
            data_query = data_query.outerjoin(CaseStudy.addresses, full=False)

        data_query = data_query.outerjoin(
            RefCountry, Address.admin_unit_l1 == RefCountry.code, full=False
        )

        q_safe = re.escape(q)
        search_regex = f"\\y{q_safe}\\y"
        q_lower = q.lower()
        search_term = f"%{q}%"
        fuzzy_threshold = 0.3

        exact_cond = or_(
            # --- Free-text fields (word-boundary regex, case-insensitive) ---
            CaseStudy.title.op("~*")(search_regex),
            CaseStudy.short_description.op("~*")(search_regex),
            CaseStudy.long_description.op("~*")(search_regex),
            CaseStudy.problem_solved.op("~*")(search_regex),
            Benefit.name.op("~*")(search_regex),

            # --- Exact label / name / code matches (trimmed and case-insensitive for labels) ---
            func.lower(func.trim(Organization.name)) == q_lower,
            func.lower(func.trim(Benefit.name)) == q_lower,
            func.lower(func.trim(ContactPoint.has_email)) == q_lower,

            # Sector label & code
            func.lower(func.trim(RefSector.label)) == q_lower,
            RefSector.code == q,

            # Benefit type & unit labels & codes
            func.lower(func.trim(RefBenefitType.label)) == q_lower,
            RefBenefitType.code == q,
            func.lower(func.trim(RefBenefitUnit.label)) == q_lower,
            RefBenefitUnit.code == q,

            # Technology label & code
            func.lower(func.trim(RefTechnology.label)) == q_lower,
            RefTechnology.code == q,

            # Calculation & Funding type labels & codes
            func.lower(func.trim(RefCalculationType.label)) == q_lower,
            RefCalculationType.code == q,
            func.lower(func.trim(RefFundingType.label)) == q_lower,
            RefFundingType.code == q,

            # Organisation type label & code
            func.lower(func.trim(RefOrganizationType.label)) == q_lower,
            RefOrganizationType.code == q,

            # Address / country
            func.trim(Address.admin_unit_l1) == q,
            func.lower(func.trim(RefCountry.label)) == q_lower,
            func.lower(func.trim(Address.post_name)) == q_lower,
        )

        partial_cond = or_(
            # 1. Standard Partial Match (Robust substring search)
            CaseStudy.title.ilike(search_term),
            CaseStudy.short_description.ilike(search_term),
            CaseStudy.long_description.ilike(search_term),
            CaseStudy.problem_solved.ilike(search_term),
            cast(CaseStudy.created_date, String).ilike(search_term),
            Benefit.name.ilike(search_term),
            Benefit.type_code.ilike(search_term),
            RefBenefitType.label.ilike(search_term),
            Benefit.unit_code.ilike(search_term),
            RefBenefitUnit.label.ilike(search_term),
            Organization.name.ilike(search_term),
            Organization.sector_code.ilike(search_term),
            ContactPoint.has_email.ilike(search_term),
            RefSector.label.ilike(search_term),
            RefOrganizationType.label.ilike(search_term),
            RefFundingType.label.ilike(search_term),
            Address.admin_unit_l1.ilike(search_term),
            RefCountry.label.ilike(search_term),
            Address.post_name.ilike(search_term),
            RefTechnology.label.ilike(search_term),
            RefCalculationType.label.ilike(search_term),

            # 2. Fuzzy Match (Trigram Similarity)
            func.similarity(CaseStudy.title, q) > fuzzy_threshold,
            func.similarity(Organization.name, q) > fuzzy_threshold,
            func.similarity(RefSector.label, q) > fuzzy_threshold,
            func.similarity(Address.post_name, q) > fuzzy_threshold,
            func.similarity(RefCountry.label, q) > fuzzy_threshold
        )

        data_query = data_query.where(or_(exact_cond, partial_cond))

    # Calculate Total BEFORE applying limit/offset.
    # Use a subquery of distinct IDs to prevent inflated counts from multi-joins.
    try:
        count_subquery = data_query.with_only_columns(CaseStudy.id).distinct().subquery()
        count_query = select(func.count()).select_from(count_subquery)
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0
    except Exception as exc:
        logger.exception(
            "Search count query failed. params=q=%r sectors=%r countries=%r error=%s",
            q, sectors, countries, exc,
        )
        raise HTTPException(status_code=500, detail=f"Search query failed: {exc}") from exc

    # Calculate offset
    offset = (page - 1) * limit

    # Get distinct CaseStudy IDs that match all filters, then fetch full objects
    # cleanly (without the filter joins) to avoid duplicate rows from M2M joins.
    if q:
        distinct_ids_subquery = data_query.with_only_columns(
            CaseStudy.id,
            func.bool_or(exact_cond).label('is_exact')
        ).group_by(CaseStudy.id).subquery()
    else:
        from sqlalchemy import true
        distinct_ids_subquery = data_query.with_only_columns(
            CaseStudy.id,
            true().label('is_exact')
        ).distinct().subquery()
    
    # 1. Define the primary sort column dynamically
    if sort_by == 'created_date':
        primary_sort = CaseStudy.created_date
    else:
        # For title, use lowercase to ensure Case-Insensitive sorting (A vs a)
        primary_sort = func.lower(CaseStudy.title)

    ids_query = (
        select(CaseStudy, distinct_ids_subquery.c.is_exact)
        .join(distinct_ids_subquery, CaseStudy.id == distinct_ids_subquery.c.id)
        .options(
            selectinload(CaseStudy.benefits).selectinload(Benefit.unit),
            selectinload(CaseStudy.benefits).selectinload(Benefit.type),
            selectinload(CaseStudy.funding_type),
            selectinload(CaseStudy.is_provided_by).options(
                 selectinload(Organization.sector),
                 selectinload(Organization.org_type)
            ),
            selectinload(CaseStudy.is_funded_by).options(
                 selectinload(Organization.sector),
                 selectinload(Organization.org_type)
            ),
            selectinload(CaseStudy.logo),
            selectinload(CaseStudy.addresses),
            selectinload(CaseStudy.language)
        )
    )
    
    # order by exactness first if q is provided
    if q:
        ids_query = ids_query.order_by(distinct_ids_subquery.c.is_exact.desc())

    # 2. Apply sorting using the dynamic 'primary_sort' variable
    if sort_order == "desc":
        ids_query = ids_query.order_by(
            primary_sort.desc(),
            CaseStudy.id.desc()  # Always use ID as a tie-breaker for stability
        )
    else:
        ids_query = ids_query.order_by(
            primary_sort.asc(),
            CaseStudy.id.asc()
        )
    
    # Apply pagination
    ids_query = ids_query.offset(offset).limit(limit)

    try:
        result = await session.execute(ids_query)
        rows = result.all()
    except Exception as exc:
        logger.exception(
            "Search fetch query failed. params=q=%r sectors=%r countries=%r error=%s",
            q, sectors, countries, exc,
        )
        raise HTTPException(status_code=500, detail=f"Search query failed: {exc}") from exc

    exact_matches = []
    partial_matches = []
    
    for row in rows:
        case_study = row[0]
        is_exact = row[1]
        if is_exact:
            exact_matches.append(case_study)
        else:
            partial_matches.append(case_study)

    return SearchPaginatedResponse(
        total=total,
        page=page,
        limit=limit,
        exact_matches=exact_matches,
        partial_matches=partial_matches
    )


@router.get("/facets", response_model=SearchFacets)
async def get_search_facets(session: AsyncSession = Depends(get_session)):
    """
    Returns codes and counts that exist in the whole dataset.
    Fixed to count UNIQUE case studies per facet code.
    """
    
    async def get_counts(query):
        res = await session.execute(query)
        return [FacetItem(code=row[0], count=row[1]) for row in res.all() if row[0] is not None]

    # 1. Sector Facets
    # Fix: Count distinct CaseStudy.id to avoid double-counting if a CS has 2 providers in same sector
    sector_query = (
        select(Organization.sector_code, func.count(func.distinct(CaseStudy.id)))
        .join(CaseStudyProviderLink, CaseStudyProviderLink.organization_id == Organization.id)
        .join(CaseStudy, CaseStudy.id == CaseStudyProviderLink.case_study_id)
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .group_by(Organization.sector_code)
    )
    sector_facets = await get_counts(sector_query)

    # 2. Tech facets (Usually 1:1, but distinct is safer)
    tech_query = (
        select(CaseStudy.tech_code, func.count(func.distinct(CaseStudy.id)))
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .group_by(CaseStudy.tech_code)
    )
    tech_facets = await get_counts(tech_query)

    # 3. Funding Type facets
    funding_query = (
        select(CaseStudy.funding_type_code, func.count(func.distinct(CaseStudy.id)))
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .group_by(CaseStudy.funding_type_code)
    )
    funding_facets = await get_counts(funding_query)

    # 4. Calculation Type facets
    calc_query = (
        select(CaseStudy.calc_type_code, func.count(func.distinct(CaseStudy.id)))
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .group_by(CaseStudy.calc_type_code)
    )
    calc_facets = await get_counts(calc_query)

    # 5. Country facets
    # Fix: Count distinct CS IDs. If a CS has 2 addresses in "SWE", it should count as 1 for "SWE".
    country_query = (
        select(Address.admin_unit_l1, func.count(func.distinct(CaseStudy.id)))
        .join(CaseStudy, CaseStudy.id == Address.case_study_id)
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .group_by(Address.admin_unit_l1)
    )
    country_facets = await get_counts(country_query)

    # 6. Organization Type facets
    org_type_query = (
        select(Organization.org_type_code, func.count(func.distinct(CaseStudy.id)))
        .join(CaseStudyProviderLink, CaseStudyProviderLink.organization_id == Organization.id)
        .join(CaseStudy, CaseStudy.id == CaseStudyProviderLink.case_study_id)
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .group_by(Organization.org_type_code)
    )
    org_type_facets = await get_counts(org_type_query)

    # 7. Benefit Unit facets
    # Fix: This was the biggest issue. 
    # Example: If CS #1 has 3 benefits in 'tco2', it should count as 1 case study for 'tco2'.
    unit_query = (
        select(Benefit.unit_code, func.count(func.distinct(CaseStudy.id)))
        .join(CaseStudy, CaseStudy.id == Benefit.case_study_id)
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .group_by(Benefit.unit_code)
    )
    unit_facets = await get_counts(unit_query)

    # 8. Benefit Type facets
    type_query = (
        select(Benefit.type_code, func.count(func.distinct(CaseStudy.id)))
        .join(CaseStudy, CaseStudy.id == Benefit.case_study_id)
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .group_by(Benefit.type_code)
    )
    type_facets = await get_counts(type_query)

    return SearchFacets(
        sectors=sector_facets,
        technologies=tech_facets,
        funding_types=funding_facets,
        calculation_types=calc_facets,
        countries=country_facets,
        organization_types=org_type_facets,
        benefit_units=unit_facets,
        benefit_types=type_facets
    )