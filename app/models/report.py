"""Report models for tip submissions."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float
    lng: float
    building: Optional[str] = None


class ReportCreate(BaseModel):
    text_body: str
    location: Optional[Location] = None
    timestamp: Optional[datetime] = None
    media_url: Optional[str] = None
    anonymous: bool = True
    contact: Optional[str] = None


class ReportStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    TRIAGED = "triaged"


class ReportOut(BaseModel):
    case_id: str
    report_id: str
    text_body: str
    location: Optional[Location] = None
    timestamp: Optional[datetime] = None
    media_url: Optional[str] = None
    anonymous: bool = True
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
