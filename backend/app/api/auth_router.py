from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.auth import MessageResponse, RefreshTokenRequest, TokenPair, UserCreate, UserLogin, UserRead
from app.services.auth_service import authenticate_user, create_token_pair, create_user, revoke_refresh_token, rotate_token_pair


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    user = create_user(db, payload.name, payload.email, payload.password)
    access_token, refresh_token = create_token_pair(db, user)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserRead.model_validate(user),
    }


@router.post("/login", response_model=TokenPair)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    access_token, refresh_token = create_token_pair(db, user)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserRead.model_validate(user),
    }


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    access_token, refresh_token, user = rotate_token_pair(db, payload.refresh_token)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserRead.model_validate(user),
    }


@router.post("/logout", response_model=MessageResponse)
def logout(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    revoke_refresh_token(db, payload.refresh_token)
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserRead)
def me(current_user=Depends(get_current_user)):
    return UserRead.model_validate(current_user)