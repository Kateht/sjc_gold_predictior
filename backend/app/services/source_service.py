from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import GoldSourceLink


def list_gold_sources(db: Session, active_only: bool = True) -> list[GoldSourceLink]:
    query = db.query(GoldSourceLink)
    if active_only:
        query = query.filter(GoldSourceLink.is_active.is_(True))
    return query.order_by(GoldSourceLink.sort_order.asc(), GoldSourceLink.id.asc()).all()


def get_gold_source_by_identifier(db: Session, identifier: str | int, active_only: bool = True) -> GoldSourceLink | None:
    query = db.query(GoldSourceLink)
    if active_only:
        query = query.filter(GoldSourceLink.is_active.is_(True))

    identifier_text = str(identifier).strip()
    if identifier_text.isdigit():
        found = query.filter(GoldSourceLink.id == int(identifier_text)).first()
        if found:
            return found
    return query.filter(GoldSourceLink.code == identifier_text).first()