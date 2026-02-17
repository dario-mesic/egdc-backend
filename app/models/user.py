from typing import Optional
from enum import Enum
from sqlmodel import SQLModel, Field

class UserRole(str, Enum):
    ADMIN = "admin"
    CUSTODIAN = "custodian"
    DATA_OWNER = "data_owner"

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    role: UserRole = Field(default=UserRole.DATA_OWNER)

class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str = Field(nullable=False)
