from fastapi import APIRouter
from app.api.v1.endpoints import case_studies, seed, search, references, stats, organizations

api_router = APIRouter()
api_router.include_router(case_studies.router, prefix="/case-studies", tags=["case-studies"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(references.router, prefix="/reference-data", tags=["references"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(seed.router, tags=["seed"])
