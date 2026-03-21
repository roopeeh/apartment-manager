from pydantic import BaseModel, ConfigDict
from typing import Optional
import uuid
from datetime import datetime, date


class ResidentCreate(BaseModel):
    flat_id: uuid.UUID
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    role: str  # Owner | Tenant | Family Member
    move_in_date: Optional[date] = None


class ResidentUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    move_in_date: Optional[date] = None


class ResidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    flat_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    role: str
    active: bool
    move_in_date: Optional[date] = None
    created_at: datetime
