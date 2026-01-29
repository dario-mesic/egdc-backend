from typing import List, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_session
from app.models.case_study import CaseStudy, Address, Benefit
from app.models.references import RefCountry
from app.schemas.stats import StatsResponse, CountryStat, BenefitStat, CityStat

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

    return StatsResponse(map_data=map_data, kpi_data=kpi_data)
