from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid

from app.database import get_db
from app.utils.jwt_utils import decode_token
from app.models.models import User, UserRole, AppRole

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


async def get_current_user_with_roles(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    roles_result = await db.execute(select(UserRole).where(UserRole.user_id == user.id))
    roles = roles_result.scalars().all()

    return {"user": user, "roles": roles, "payload": payload}


def require_super_admin(current: dict = Depends(get_current_user_with_roles)):
    roles = current["roles"]
    if not any(r.role == AppRole.super_admin for r in roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return current


def make_require_society_access(require_admin: bool = False):
    async def dependency(
        society_id: uuid.UUID,
        current: dict = Depends(get_current_user_with_roles),
    ):
        roles = current["roles"]
        user_role = None
        for r in roles:
            if r.role == AppRole.super_admin:
                return {**current, "society_role": AppRole.super_admin}
            if r.society_id == society_id:
                user_role = r
        if not user_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this society")
        if require_admin and user_role.role not in (AppRole.admin, AppRole.super_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
        return {**current, "society_role": user_role.role}
    return dependency


require_society_access = make_require_society_access(require_admin=False)
require_society_admin = make_require_society_access(require_admin=True)
