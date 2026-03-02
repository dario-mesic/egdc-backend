from typing import Optional
from app.models.user import UserRole
from pydantic import BaseModel, EmailStr

class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: UserRole

    class Config:
        from_attributes = True

class UserRoleUpdate(BaseModel):
    role: UserRole
