from typing import List, Optional
from pydantic import BaseModel

class CityStat(BaseModel):
    name: str
    count: int

class CountryStat(BaseModel):
    country_code: str
    country_label: str
    cities: List[CityStat]

class BenefitStat(BaseModel):
    type_code: str
    unit_code: str
    total_value: float

class SectorImpact(BaseModel):
    sector_code: str
    total_value: float

class ScoreboardStats(BaseModel):
    total_net_carbon_impact: float
    breakdown_by_sector: List[SectorImpact]

class StatsResponse(BaseModel):
    map_data: List[CountryStat]
    kpi_data: List[BenefitStat]
    scoreboard: Optional[ScoreboardStats] = None
