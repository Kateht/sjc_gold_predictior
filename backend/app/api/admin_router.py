from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.exceptions import NotFoundError
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import MessageResponse, UserRead, UserUpdateRole
from app.schemas.models import ModelCreate, ModelRead, ModelUpdate, PredictionKind
from app.services.auth_service import get_user_by_id
from app.services.model_service import create_model, get_model_by_identifier, list_models, set_default_model, set_model_active, update_model


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/models", response_model=list[ModelRead])
def admin_list_models(
    prediction_kind: PredictionKind | None = Query(default=None),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return [ModelRead.model_validate(model) for model in list_models(db, prediction_kind=prediction_kind, active_only=active_only)]


@router.post("/models", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
def admin_create_model(payload: ModelCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    model = create_model(db, payload, created_by_id=current_user.id)
    db.commit()
    return ModelRead.model_validate(model)


@router.patch("/models/{identifier}", response_model=ModelRead)
def admin_update_model(identifier: str, payload: ModelUpdate, db: Session = Depends(get_db)):
    model = get_model_by_identifier(db, identifier, active_only=False)
    if not model:
        raise NotFoundError("Model not found")
    updated = update_model(db, model, payload)
    db.commit()
    return ModelRead.model_validate(updated)


@router.post("/models/{identifier}/activate", response_model=ModelRead)
def admin_activate_model(identifier: str, db: Session = Depends(get_db)):
    model = get_model_by_identifier(db, identifier, active_only=False)
    if not model:
        raise NotFoundError("Model not found")
    updated = set_model_active(db, model, True)
    db.commit()
    return ModelRead.model_validate(updated)


@router.post("/models/{identifier}/deactivate", response_model=ModelRead)
def admin_deactivate_model(identifier: str, db: Session = Depends(get_db)):
    model = get_model_by_identifier(db, identifier, active_only=False)
    if not model:
        raise NotFoundError("Model not found")
    updated = set_model_active(db, model, False)
    db.commit()
    return ModelRead.model_validate(updated)


@router.post("/models/{identifier}/default", response_model=ModelRead)
def admin_set_default_model(identifier: str, db: Session = Depends(get_db)):
    model = get_model_by_identifier(db, identifier, active_only=False)
    if not model:
        raise NotFoundError("Model not found")
    updated = set_default_model(db, model)
    db.commit()
    return ModelRead.model_validate(updated)


@router.get("/users", response_model=list[UserRead])
def admin_list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [UserRead.model_validate(user) for user in users]


@router.patch("/users/{user_id}/role", response_model=UserRead)
def admin_update_user_role(user_id: int, payload: UserUpdateRole, db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.post("/users/{user_id}/toggle-active", response_model=MessageResponse)
def admin_toggle_user_active(user_id: int, db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found")
    user.is_active = not user.is_active
    db.commit()
    return {"message": f"User {user.email} active={user.is_active}"}