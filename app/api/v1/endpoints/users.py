from typing import List, Any
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.db.session import get_session
from app.models.user import User
from app.models.case_study import CaseStudy, CaseStudySummaryRead, CaseStudyStatus
from app.api.v1.endpoints.case_studies import get_case_study_loader_options

router = APIRouter()

@router.get("/me/case-studies", response_model=List[CaseStudySummaryRead])
async def read_user_case_studies(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get case studies created by current user.
    """
    query = select(CaseStudy).where(
        CaseStudy.created_by == current_user.id
    ).options(
        *get_case_study_loader_options(detailed=False)
    )
    result = await session.execute(query)
    case_studies = result.scalars().all()
    return case_studies
