from typing import Optional
from app.models.user import UserRole
from pydantic import BaseModel, EmailStr

class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: UserRole

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: Optional[UserRole] = UserRole.DATA_OWNER

class UserRoleUpdate(BaseModel):
    role: UserRole
