from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import uuid

from app.database import get_db
from app.models.models import User, UserRole, RefreshToken, AppRole, Society
from app.schemas.auth import (
    RegisterRequest, LoginRequest, RefreshRequest,
    ForgotPasswordRequest, ResetPasswordRequest, LogoutRequest, ChangePasswordRequest
)
from app.utils.password import hash_password, verify_password
from app.utils.jwt_utils import create_access_token, create_refresh_token, decode_token
from app.utils.responses import success_response, error_response
from app.dependencies import get_current_user
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


async def build_token_response(user: User, db: AsyncSession) -> dict:
    roles_result = await db.execute(select(UserRole).where(UserRole.user_id == user.id))
    roles = roles_result.scalars().all()

    role_list = []
    for r in roles:
        society_name = None
        if r.society_id:
            soc = await db.get(Society, r.society_id)
            society_name = soc.name if soc else None
        role_list.append({"society_id": str(r.society_id) if r.society_id else None, "role": r.role.value, "society_name": society_name})

    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "roles": [{"society_id": str(r.society_id) if r.society_id else None, "role": r.role.value} for r in roles],
    }
    access_token = create_access_token(payload)
    refresh_token_str = create_refresh_token()

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    rt = RefreshToken(user_id=user.id, token=refresh_token_str, expires_at=expires_at)
    db.add(rt)
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_str,
        "user": {"id": str(user.id), "name": user.name, "email": user.email},
        "roles": role_list,
    }


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=error_response("CONFLICT", "Email already registered"))

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        phone=body.phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return success_response({
        "user": {"id": str(user.id), "name": user.name, "email": user.email},
        "message": "Account created. Please contact your society admin for role assignment.",
    })


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail=error_response("INVALID_CREDENTIALS", "Invalid email or password"))
    if not user.is_active:
        raise HTTPException(status_code=401, detail=error_response("ACCOUNT_INACTIVE", "Account is inactive"))

    data = await build_token_response(user, db)
    return success_response(data)


@router.post("/refresh")
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == body.refresh_token,
            RefreshToken.revoked == False,
        )
    )
    rt = result.scalar_one_or_none()
    if not rt or rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail=error_response("INVALID_TOKEN", "Invalid or expired refresh token"))

    rt.revoked = True
    await db.commit()

    user = await db.get(User, rt.user_id)
    data = await build_token_response(user, db)
    return success_response(data)


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user:
        reset_token = str(uuid.uuid4())
        user.reset_token = reset_token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.commit()
        # In production, send email here
        print(f"[DEV] Password reset token for {user.email}: {reset_token}")

    return success_response({"message": "If account exists, reset link sent to email"})


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.reset_token == body.token))
    user = result.scalar_one_or_none()
    if not user or not user.reset_token_expires:
        raise HTTPException(status_code=400, detail=error_response("INVALID_TOKEN", "Invalid or expired reset token"))
    if user.reset_token_expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail=error_response("TOKEN_EXPIRED", "Reset token has expired"))

    user.password_hash = hash_password(body.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await db.commit()

    return success_response({"message": "Password updated successfully"})


@router.post("/logout")
async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RefreshToken).where(RefreshToken.token == body.refresh_token))
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked = True
        await db.commit()
    return success_response({"message": "Logged out"})


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail=error_response("INVALID_PASSWORD", "Current password is incorrect"))

    current_user.password_hash = hash_password(body.new_password)
    await db.commit()
    return success_response({"message": "Password changed"})
