from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import NewsArticle, NewsCategory


def list_news_categories(db: Session, active_only: bool = True) -> list[NewsCategory]:
    query = db.query(NewsCategory)
    if active_only:
        query = query.filter(NewsCategory.is_active.is_(True))
    return query.order_by(NewsCategory.sort_order.asc(), NewsCategory.id.asc()).all()


def list_news_articles(
    db: Session,
    *,
    category_slug: str | None = None,
    featured_only: bool = False,
    active_only: bool = True,
    limit: int | None = None,
) -> list[NewsArticle]:
    query = db.query(NewsArticle).join(NewsCategory, NewsArticle.category_id == NewsCategory.id, isouter=True)
    if category_slug:
        query = query.filter(NewsCategory.slug == category_slug)
    if featured_only:
        query = query.filter(NewsArticle.is_featured.is_(True))
    if active_only:
        query = query.filter(NewsArticle.is_active.is_(True))
    query = query.order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.id.desc())
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def get_article_by_slug(db: Session, slug: str, active_only: bool = True) -> NewsArticle | None:
    query = db.query(NewsArticle).filter(NewsArticle.slug == slug)
    if active_only:
        query = query.filter(NewsArticle.is_active.is_(True))
    return query.first()


def get_category_by_slug(db: Session, slug: str, active_only: bool = True) -> NewsCategory | None:
    query = db.query(NewsCategory).filter(NewsCategory.slug == slug)
    if active_only:
        query = query.filter(NewsCategory.is_active.is_(True))
    return query.first()