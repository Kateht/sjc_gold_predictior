from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.schemas.news import NewsArticleRead, NewsCategoryRead
from app.services.news_service import get_article_by_slug, list_news_articles, list_news_categories


router = APIRouter(tags=["news"])


@router.get("/news/categories", response_model=list[NewsCategoryRead])
def get_news_categories(db: Session = Depends(get_db)):
    return [NewsCategoryRead.model_validate(category) for category in list_news_categories(db)]


@router.get("/news/articles", response_model=list[NewsArticleRead])
def get_news_articles(
    category: str | None = Query(default=None, description="Category slug"),
    featured: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    articles = list_news_articles(db, category_slug=category, featured_only=featured, limit=limit)
    return [NewsArticleRead.model_validate(article) for article in articles]


@router.get("/news/articles/{slug}", response_model=NewsArticleRead)
def get_news_article(slug: str, db: Session = Depends(get_db)):
    article = get_article_by_slug(db, slug)
    if not article:
        raise NotFoundError("News article not found")
    return NewsArticleRead.model_validate(article)