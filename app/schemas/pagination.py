from typing import TypeVar, Generic, List
from pydantic import BaseModel

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    limit: int
    items: List[T]

class SearchPaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    limit: int
    exact_matches: List[T]
    partial_matches: List[T]

