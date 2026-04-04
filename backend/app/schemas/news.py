from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NewsCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str | None = None
    sort_order: int
    is_active: bool


class NewsArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None = None
    slug: str
    title: str
    summary: str | None = None
    content: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    is_featured: bool
    is_active: bool


class NewsCategoryCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    sort_order: int = 0
    is_active: bool = True


class NewsArticleCreate(BaseModel):
    category_id: int | None = None
    slug: str = Field(min_length=2, max_length=180)
    title: str = Field(min_length=2, max_length=255)
    summary: str | None = None
    content: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    is_featured: bool = False
    is_active: bool = True


class NewsArticleUpdate(BaseModel):
    category_id: int | None = None
    title: str | None = Field(default=None, min_length=2, max_length=255)
    summary: str | None = None
    content: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    is_featured: bool | None = None
    is_active: bool | None = None