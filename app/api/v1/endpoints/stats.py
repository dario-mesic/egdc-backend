from typing import List, Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, exists, cast, Float
from app.db.session import get_session
from app.models.case_study import CaseStudy, Address, Benefit, CaseStudyProviderLink
from app.models.references import RefCountry
from app.schemas.stats import StatsResponse, CountryStat, BenefitStat, CityStat, ScoreboardStats, SectorImpact
from app.models.organization import Organization

router = APIRouter()

@router.get("/", response_model=StatsResponse)
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_session),
    sector_code: Optional[str] = Query(None, description="Filter stats by Organization Sector Code")
) -> Any:
    # 1. Map Data: Case studies count per country AND city
    map_query = (
        select(
            Address.admin_unit_l1.label("country_code"),
            RefCountry.label.label("country_label"),
            Address.post_name.label("city_name"),
            func.count(func.distinct(CaseStudy.id)).label("case_study_count")
        )
        .join(CaseStudy, Address.case_study_id == CaseStudy.id)
        .join(RefCountry, Address.admin_unit_l1 == RefCountry.code)
    )

    if sector_code:
        map_query = (
            map_query
            .join(CaseStudyProviderLink, CaseStudy.id == CaseStudyProviderLink.case_study_id)
            .join(Organization, CaseStudyProviderLink.organization_id == Organization.id)
            .where(Organization.sector_code == sector_code)
        )

    map_query = map_query.group_by(Address.admin_unit_l1, RefCountry.label, Address.post_name)
    
    map_result = await session.execute(map_query)
    map_results = map_result.all()
    
    # Aggregation: Group by Country
    country_map = {}
    for row in map_results:
        identifier = row.country_code # aggregation key
        
        if identifier not in country_map:
            country_map[identifier] = {
                "country_code": row.country_code,
                "country_label": row.country_label,
                "cities": []
            }
        
        # Add city if present
        if row.city_name:
            country_map[identifier]["cities"].append(
                {"name": row.city_name, "count": row.case_study_count}
            )

    map_data = [
        CountryStat(
            country_code=val["country_code"],
            country_label=val["country_label"],
            cities=[CityStat(**c) for c in val["cities"]]
        )
        for val in country_map.values()
    ]

    # 2. KPI Data: Sum of benefits grouped by type and unit
    kpi_query = (
        select(
            Benefit.type_code,
            Benefit.unit_code,
            func.sum(Benefit.value).label("total_value")
        )
    )

    if sector_code:
        kpi_query = (
            kpi_query
            .join(CaseStudy, Benefit.case_study_id == CaseStudy.id)
            .join(CaseStudyProviderLink, CaseStudy.id == CaseStudyProviderLink.case_study_id)
            .join(Organization, CaseStudyProviderLink.organization_id == Organization.id)
            .where(Organization.sector_code == sector_code)
        )

    kpi_query = kpi_query.group_by(Benefit.type_code, Benefit.unit_code)

    kpi_result = await session.execute(kpi_query)
    kpi_results = kpi_result.all()
    
    kpi_data = [
        BenefitStat(
            type_code=row.type_code,
            unit_code=row.unit_code,
            total_value=row.total_value
        )
        for row in kpi_results
    ]

    # 3. Scoreboard: Total Net Carbon Impact (value where is_net_carbon_impact=True AND status='published')
    # Assuming 'published' status is required.
    from app.models.case_study import CaseStudyStatus
        
    # Total Impact
    impact_query = (
        select(func.sum(Benefit.value))
        .join(CaseStudy, Benefit.case_study_id == CaseStudy.id)
        .where(
            CaseStudy.status == CaseStudyStatus.PUBLISHED,
            Benefit.is_net_carbon_impact == True
        )
    )

    if sector_code:
        # EXISTS counts each benefit once (joining providers would duplicate rows)
        impact_query = impact_query.where(
            exists(
                select(1)
                .select_from(CaseStudyProviderLink)
                .join(Organization, CaseStudyProviderLink.organization_id == Organization.id)
                .where(
                    CaseStudyProviderLink.case_study_id == CaseStudy.id,
                    Organization.sector_code == sector_code,
                )
            )
        )

    impact_result = await session.execute(impact_query)
    total_impact = impact_result.scalar() or 0.0

    # Impact by sector: split each benefit by provider count so multi-provider case studies
    # do not inflate totals (sum of sectors matches total_net_carbon_impact).
    provider_count_sq = (
        select(
            CaseStudyProviderLink.case_study_id,
            func.count().label("provider_count"),
        )
        .group_by(CaseStudyProviderLink.case_study_id)
        .subquery()
    )
    weighted_value = cast(Benefit.value, Float) / cast(
        func.nullif(provider_count_sq.c.provider_count, 0), Float
    )
    sector_impact_query = (
        select(
            Organization.sector_code,
            func.sum(weighted_value),
        )
        .join(CaseStudyProviderLink, CaseStudyProviderLink.organization_id == Organization.id)
        .join(CaseStudy, CaseStudy.id == CaseStudyProviderLink.case_study_id)
        .join(Benefit, Benefit.case_study_id == CaseStudy.id)
        .join(provider_count_sq, CaseStudy.id == provider_count_sq.c.case_study_id)
        .where(
            CaseStudy.status == CaseStudyStatus.PUBLISHED,
            Benefit.is_net_carbon_impact == True,
        )
        .group_by(Organization.sector_code)
    )

    if sector_code:
        sector_impact_query = sector_impact_query.where(Organization.sector_code == sector_code)

    sector_impact_result = await session.execute(sector_impact_query)
    
    sector_impacts = [
        SectorImpact(sector_code=row[0], total_value=row[1])
        for row in sector_impact_result.all()
        if row[0] is not None
    ]

    # Published case studies with no provider cannot appear in the sector join; attribute here so
    # sum(breakdown_by_sector) matches total_net_carbon_impact (when not filtered by sector).
    if not sector_code:
        orphan_impact_query = (
            select(func.sum(Benefit.value))
            .join(CaseStudy, Benefit.case_study_id == CaseStudy.id)
            .where(
                CaseStudy.status == CaseStudyStatus.PUBLISHED,
                Benefit.is_net_carbon_impact == True,
                ~exists(
                    select(1)
                    .select_from(CaseStudyProviderLink)
                    .where(CaseStudyProviderLink.case_study_id == CaseStudy.id),
                ),
            )
        )
        orphan_total = (await session.execute(orphan_impact_query)).scalar() or 0.0
        if orphan_total:
            sector_impacts.append(
                SectorImpact(sector_code="unassigned", total_value=orphan_total)
            )

    scoreboard_stats = ScoreboardStats(
        total_net_carbon_impact=total_impact,
        breakdown_by_sector=sector_impacts
    )

    return StatsResponse(map_data=map_data, kpi_data=kpi_data, scoreboard=scoreboard_stats)
