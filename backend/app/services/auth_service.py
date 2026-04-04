from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.db.models import RefreshToken, User


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.strip().lower()).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, name: str, email: str, password: str, role: str = "user") -> User:
    normalized_email = email.strip().lower()
    if get_user_by_email(db, normalized_email):
        raise ConflictError("Email already registered")

    user = User(
        name=name.strip(),
        email=normalized_email,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        raise UnauthorizedError("Invalid email or password")
    if not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")
    return user


def _store_refresh_token(db: Session, user: User, refresh_token: str) -> RefreshToken:
    claims = jwt.get_unverified_claims(refresh_token)
    expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
    record = RefreshToken(
        user_id=user.id,
        token_jti=str(claims["jti"]),
        token_hash=_hash_token(refresh_token),
        expires_at=expires_at,
    )
    db.add(record)
    db.flush()
    return record


def create_token_pair(db: Session, user: User) -> tuple[str, str]:
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    _store_refresh_token(db, user, refresh_token)
    return access_token, refresh_token


def verify_refresh_token(db: Session, refresh_token: str) -> User:
    try:
        payload = jwt.decode(refresh_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise UnauthorizedError("Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token type")

    subject = payload.get("sub")
    token_jti = payload.get("jti")
    if not subject or not token_jti:
        raise UnauthorizedError("Invalid refresh token payload")

    try:
        subject_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Invalid refresh token payload") from exc

    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_jti == str(token_jti), RefreshToken.token_hash == _hash_token(refresh_token))
        .first()
    )
    if not record or record.revoked_at is not None:
        raise UnauthorizedError("Refresh token revoked")

    if record.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("Refresh token expired")

    user = db.get(User, subject_id)
    if not user or not user.is_active:
        raise UnauthorizedError("Inactive or missing user")
    return user


def revoke_refresh_token(db: Session, refresh_token: str) -> None:
    try:
        payload = jwt.decode(refresh_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return

    token_jti = payload.get("jti")
    if not token_jti:
        return

    record = db.query(RefreshToken).filter(RefreshToken.token_jti == str(token_jti)).first()
    if record and record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
        db.flush()


def rotate_token_pair(db: Session, refresh_token: str) -> tuple[str, str, User]:
    user = verify_refresh_token(db, refresh_token)
    revoke_refresh_token(db, refresh_token)
    access_token = create_access_token(str(user.id))
    new_refresh_token = create_refresh_token(str(user.id))
    _store_refresh_token(db, user, new_refresh_token)
    return access_token, new_refresh_token, user