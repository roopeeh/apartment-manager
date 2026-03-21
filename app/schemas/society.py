from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
import uuid
from datetime import datetime


class SocietyCreate(BaseModel):
    name: str
    address: str
    city: str
    phone: Optional[str] = None
    email: Optional[str] = None
    total_blocks: int = 0
    blocks: List[str] = []
    floors: List[Any] = []
    plan: str = "basic"
    admin: dict  # {name, email, phone, password}


class SocietyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    total_blocks: Optional[int] = None
    blocks: Optional[List[str]] = None
    floors: Optional[List[Any]] = None
    config: Optional[dict] = None
    payment_gateway: Optional[dict] = None
    status: Optional[str] = None
    plan: Optional[str] = None


class SocietyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str
    city: str
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    total_blocks: int
    blocks: List[Any]
    floors: List[Any]
    config: dict
    payment_gateway: dict
    plan: str
    status: str
    created_at: datetime
    updated_at: datetime
