"""Recipe-related Pydantic schemas."""

from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, HttpUrl

from schemas.enums import Category, Cuisine

class RecipeBase(BaseModel):
    """Base schema with common recipe fields."""
    name: str = Field(..., max_length=255)
    preparation_time: Optional[int] = Field(None, ge=0)
    cooking_time: Optional[int] = Field(None, ge=0)
    category: List[Category] = Field(..., min_items=1)
    ingredients: List[str] = Field(..., min_items=1)
    ingredients_raw: List[str] = Field(..., min_items=1)
    instructions: str = Field(..., max_length=6000)
    cooking_methods: List[str] = Field(default_factory=list)
    implements: List[str] = Field(default_factory=list)
    nutrition: Optional[Dict[str, Any]] = None
    cuisine: Cuisine
    number_of_steps: Optional[int] = Field(None, ge=0)
    url: Optional[HttpUrl] = Field(None, max_length=500)


class RecipeCreate(RecipeBase):
    """Schema for creating a recipe (POST /add)."""
    pass


class RecipeUpdate(BaseModel):
    """Schema for partial updates (PATCH /recipes/{id})."""
    name: Optional[str] = Field(None, max_length=255)
    preparation_time: Optional[int] = Field(None, ge=0)
    cooking_time: Optional[int] = Field(None, ge=0)
    category: Optional[List[Category]] = None
    ingredients: Optional[List[str]] = None
    ingredients_raw: Optional[List[str]] = None
    instructions: Optional[str] = Field(None, max_length=6000)
    cooking_methods: Optional[List[str]] = None
    implements: Optional[List[str]] = None
    nutrition: Optional[Dict[str, Any]] = None
    cuisine: Optional[Cuisine] = None
    number_of_steps: Optional[int] = Field(None, ge=0)
    url: Optional[HttpUrl] = Field(None, max_length=500)


class RecipeResponse(RecipeBase):
    """Schema for recipe responses (includes ID and timestamps)."""
    id: int
    created_at: Optional[datetime] = None
    rating_value: Optional[float] = None
    rating_count: int = 0

    class Config:
        from_attributes = True
