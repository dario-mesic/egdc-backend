from typing import List, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.db.session import get_session
from app.models.user import User, UserRole
from app.models.case_study import CaseStudy, CaseStudySummaryRead, CaseStudyStatus
from app.api.v1.endpoints.case_studies import get_case_study_loader_options
from app.schemas.pagination import PaginatedResponse
from app.schemas.user import UserOut, UserCreate, UserRoleUpdate
from app.core.security import get_password_hash

router = APIRouter()

@router.get("/me/case-studies", response_model=PaginatedResponse[CaseStudySummaryRead])
async def read_user_case_studies(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get case studies created by current user with pagination.
    """
    offset = (page - 1) * limit

    # Total count for current user
    count_query = select(func.count()).select_from(CaseStudy).where(
        CaseStudy.created_by == current_user.id
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Paginated query
    query = select(CaseStudy).where(
        CaseStudy.created_by == current_user.id
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

@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new user (Signup)."""
    # NOTE: this is logic for now and later will be different with mail system.
    

    # Check if user already exists
    query = select(User).where(User.email == user_in.email)
    result = await session.execute(query)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role=user_in.role
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user

# --- Admin User Management ---

@router.get("/", response_model=PaginatedResponse[UserOut])
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """Admin only: List all users."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")

    offset = (page - 1) * limit

    # Count all users
    count_query = select(func.count()).select_from(User)
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch users
    query = select(User).offset(offset).limit(limit)
    result = await session.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )

@router.patch("/{id}/role", response_model=UserOut)
async def update_user_role(
    id: int,
    user_update: UserRoleUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """Admin only: Update a user's role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")

    if id == current_user.id:
        raise HTTPException(status_code=400, detail="Admins cannot change their own role")

    user = await session.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = user_update.role
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """Admin only: Delete a user."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")

    if id == current_user.id:
        raise HTTPException(status_code=400, detail="Admins cannot delete themselves")

    user = await session.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await session.delete(user)
    await session.commit()
    return None
