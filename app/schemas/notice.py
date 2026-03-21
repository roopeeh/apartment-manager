from pydantic import BaseModel, ConfigDict
from typing import Optional
import uuid
from datetime import datetime, date


class NoticeCreate(BaseModel):
    title: str
    message: str
    priority: str = "medium"
    pinned: bool = False
    expiry_date: Optional[date] = None


class NoticeUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    priority: Optional[str] = None
    pinned: Optional[bool] = None
    expiry_date: Optional[date] = None


class NoticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    title: str
    message: str
    priority: str
    pinned: bool
    posted_by: Optional[str] = None
    posted_date: Optional[date] = None
    expiry_date: Optional[date] = None
    created_at: datetime
