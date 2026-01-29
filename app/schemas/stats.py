from typing import List
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

class StatsResponse(BaseModel):
    map_data: List[CountryStat]
    kpi_data: List[BenefitStat]
