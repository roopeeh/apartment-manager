from pydantic import BaseModel, EmailStr
from typing import List, Optional
import uuid


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RoleInfo(BaseModel):
    society_id: Optional[uuid.UUID] = None
    role: str
    society_name: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: dict
    roles: List[RoleInfo]


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
