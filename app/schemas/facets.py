from typing import List, Optional
from pydantic import BaseModel

class FacetItem(BaseModel):
    code: str
    count: int

class SearchFacets(BaseModel):
    sectors: List[FacetItem] = []
    technologies: List[FacetItem] = []
    funding_types: List[FacetItem] = []
    calculation_types: List[FacetItem] = []
    countries: List[FacetItem] = []
    organization_types: List[FacetItem] = []
    benefit_units: List[FacetItem] = []
    benefit_types: List[FacetItem] = []
