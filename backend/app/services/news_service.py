from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.orm import Session

from app.db.models import NewsArticle, NewsCategory


logger = logging.getLogger(__name__)
_GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_NEWS_SYNC_TTL = timedelta(minutes=30)
_GDELT_MIN_REQUEST_INTERVAL = timedelta(seconds=10)
_GDELT_RETRY_COUNT = 3
_GDELT_RATE_LIMIT_WAIT = timedelta(seconds=10)
_NEWS_SYNC_LOCK = threading.Lock()
_GDELT_REQUEST_LOCK = threading.Lock()
_LAST_SYNC_AT: datetime | None = None
_LAST_GDELT_REQUEST_AT: datetime | None = None

_CATEGORY_QUERIES: dict[str, str] = {
    "economy": "gold inflation rates economy",
    "politics": "central bank fed rates policy gold",
    "gold": "gold bullion sjc pnj precious metals",
    "related": "usd vnd commodities yields dollar gold",
}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "news-item"


def _parse_seen_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _gdelt_rate_limited(response: requests.Response) -> bool:
    if response.status_code == 429:
        return True

    body = (getattr(response, "text", "") or "").lower()
    return "limit requests to one every 5 seconds" in body or "contact kalev.leetaru5@gmail.com" in body


def _wait_for_gdelt_slot() -> None:
    global _LAST_GDELT_REQUEST_AT

    now = datetime.now(timezone.utc)
    if _LAST_GDELT_REQUEST_AT is not None:
        elapsed = now - _LAST_GDELT_REQUEST_AT
        remaining = _GDELT_MIN_REQUEST_INTERVAL - elapsed
        if remaining > timedelta(0):
            time.sleep(remaining.total_seconds())

    _LAST_GDELT_REQUEST_AT = datetime.now(timezone.utc)


def _fetch_gdelt_articles(query: str, limit: int = 8) -> list[dict[str, object]]:
    last_error: Exception | None = None

    for attempt in range(1, _GDELT_RETRY_COUNT + 1):
        with _GDELT_REQUEST_LOCK:
            _wait_for_gdelt_slot()
            response = requests.get(
                _GDELT_ENDPOINT,
                params={
                    "query": query,
                    "mode": "artlist",
                    "format": "json",
                    "sort": "datedesc",
                    "maxrecords": limit,
                },
                timeout=12,
            )

        if _gdelt_rate_limited(response):
            last_error = RuntimeError((getattr(response, "text", "") or "GDELT rate limit reached").strip())
            if attempt < _GDELT_RETRY_COUNT:
                time.sleep(_GDELT_RATE_LIMIT_WAIT.total_seconds())
                continue
            raise last_error

        try:
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            last_error = exc
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {429, 500, 502, 503, 504} and attempt < _GDELT_RETRY_COUNT:
                time.sleep(_GDELT_RATE_LIMIT_WAIT.total_seconds())
                continue
            raise

        articles = payload.get("articles") if isinstance(payload, dict) else None
        if not isinstance(articles, list):
            return []
        return [article for article in articles if isinstance(article, dict)]

    if last_error is not None:
        raise last_error
    return []


def _upsert_news_article(db: Session, category: NewsCategory, payload: dict[str, object], rank: int) -> None:
    source_url = str(payload.get("url") or payload.get("url_mobile") or "").strip()
    if not source_url:
        return

    title = str(payload.get("title") or "").strip()
    if not title:
        return

    source_name = str(payload.get("domain") or payload.get("sourcecountry") or "GDELT").strip() or "GDELT"
    summary = f"{source_name} · {str(payload.get('sourcecountry') or 'Global').strip()}"
    published_at = _parse_seen_date(str(payload.get("seendate") or ""))
    image_url = str(payload.get("socialimage") or "").strip() or None
    slug = f"{_slugify(title)}-{hashlib.sha1(source_url.encode('utf-8')).hexdigest()[:10]}"

    existing = db.query(NewsArticle).filter(NewsArticle.source_url == source_url).first()
    if existing is None:
        existing = db.query(NewsArticle).filter(NewsArticle.slug == slug).first()

    if existing:
        existing.category_id = existing.category_id or category.id
        existing.slug = slug
        existing.title = title
        existing.summary = summary
        existing.content = title
        existing.source_name = source_name
        existing.source_url = source_url
        existing.image_url = image_url
        existing.published_at = published_at
        existing.is_featured = rank < 2 or existing.is_featured
        existing.is_active = True
        return

    db.add(
        NewsArticle(
            category_id=category.id,
            slug=slug,
            title=title,
            summary=summary,
            content=title,
            source_name=source_name,
            source_url=source_url,
            image_url=image_url,
            published_at=published_at,
            is_featured=rank < 2,
            is_active=True,
        )
    )


def _sync_external_news(db: Session) -> None:
    global _LAST_SYNC_AT

    now = datetime.now(timezone.utc)
    if _LAST_SYNC_AT and now - _LAST_SYNC_AT < _NEWS_SYNC_TTL:
        return

    with _NEWS_SYNC_LOCK:
        if _LAST_SYNC_AT and now - _LAST_SYNC_AT < _NEWS_SYNC_TTL:
            return

        categories = db.query(NewsCategory).filter(NewsCategory.is_active.is_(True)).order_by(NewsCategory.sort_order.asc(), NewsCategory.id.asc()).all()
        changed = False
        for category in categories:
            query = _CATEGORY_QUERIES.get(category.slug, f"gold {category.name}")
            try:
                for rank, article in enumerate(_fetch_gdelt_articles(query, limit=8)):
                    _upsert_news_article(db, category, article, rank)
                    changed = True
            except Exception as exc:  # pragma: no cover - best effort live feed
                logger.warning("Failed to sync news category %s: %s", category.slug, exc)

        if changed:
            db.commit()
        _LAST_SYNC_AT = now


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
    _sync_external_news(db)

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
    _sync_external_news(db)
    query = db.query(NewsArticle).filter(NewsArticle.slug == slug)
    if active_only:
        query = query.filter(NewsArticle.is_active.is_(True))
    return query.first()


def get_category_by_slug(db: Session, slug: str, active_only: bool = True) -> NewsCategory | None:
    query = db.query(NewsCategory).filter(NewsCategory.slug == slug)
    if active_only:
        query = query.filter(NewsCategory.is_active.is_(True))
    return query.first()