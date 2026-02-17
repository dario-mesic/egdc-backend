from typing import List, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_session
from app.models.case_study import CaseStudy, Address, Benefit, CaseStudyProviderLink
from app.models.references import RefCountry
from app.schemas.stats import StatsResponse, CountryStat, BenefitStat, CityStat, ScoreboardStats, SectorImpact
from app.models.organization import Organization

router = APIRouter()

@router.get("/", response_model=StatsResponse)
async def get_dashboard_stats(session: AsyncSession = Depends(get_session)) -> Any:
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
        .group_by(Address.admin_unit_l1, RefCountry.label, Address.post_name)
    )
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
        .group_by(Benefit.type_code, Benefit.unit_code)
    )
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
    
    scoreboard_base_query = (
        select(CaseStudy.id)
        .where(CaseStudy.status == CaseStudyStatus.PUBLISHED)
        .subquery()
    )
    
    # Total Impact
    impact_query = (
        select(func.sum(Benefit.value))
        .join(CaseStudy, Benefit.case_study_id == CaseStudy.id)
        .where(
            CaseStudy.status == CaseStudyStatus.PUBLISHED,
            Benefit.is_net_carbon_impact == True
        )
    )
    impact_result = await session.execute(impact_query)
    total_impact = impact_result.scalar() or 0.0

    # Impact by Sector
    sector_impact_query = (
        select(
            Organization.sector_code,
            func.sum(Benefit.value)
        )
        .join(CaseStudyProviderLink, CaseStudyProviderLink.organization_id == Organization.id)
        .join(CaseStudy, CaseStudy.id == CaseStudyProviderLink.case_study_id)
        .join(Benefit, Benefit.case_study_id == CaseStudy.id)
        .where(
            CaseStudy.status == CaseStudyStatus.PUBLISHED,
            Benefit.is_net_carbon_impact == True
        )
        .group_by(Organization.sector_code)
    )
    sector_impact_result = await session.execute(sector_impact_query)
    
    sector_impacts = [
        SectorImpact(sector_code=row[0], total_value=row[1]) 
        for row in sector_impact_result.all() 
        if row[0] is not None
    ]

    scoreboard_stats = ScoreboardStats(
        total_net_carbon_impact=total_impact,
        breakdown_by_sector=sector_impacts
    )

    return StatsResponse(map_data=map_data, kpi_data=kpi_data, scoreboard=scoreboard_stats)
