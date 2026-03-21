from pydantic import BaseModel, ConfigDict
from typing import Optional
import uuid
from datetime import datetime
from decimal import Decimal


class FlatCreate(BaseModel):
    flat_number: str
    block: str
    floor: int
    area: Optional[int] = None
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    occupancy: str = "vacant"
    maintenance_amount: Decimal


class FlatUpdate(BaseModel):
    flat_number: Optional[str] = None
    block: Optional[str] = None
    floor: Optional[int] = None
    area: Optional[int] = None
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    occupancy: Optional[str] = None
    maintenance_amount: Optional[Decimal] = None


class FlatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    flat_number: str
    block: str
    floor: int
    area: Optional[int] = None
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    occupancy: str
    maintenance_amount: Decimal
    created_at: datetime
