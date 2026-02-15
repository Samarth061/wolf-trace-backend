"""Alert models for officer-verified alerts."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AlertStatus(str, Enum):
    CONFIRMED = "Confirmed"
    INVESTIGATING = "Investigating"
    ALL_CLEAR = "All Clear"


class AlertDraftRequest(BaseModel):
    case_id: str
    officer_notes: Optional[str] = None


class AlertDraftResponse(BaseModel):
    case_id: str
    draft_text: str
    status: str = "draft"
    location_summary: Optional[str] = None


class AlertApproveRequest(BaseModel):
    case_id: str
    final_text: str
    status: AlertStatus = AlertStatus.CONFIRMED


class AlertOut(BaseModel):
    id: str
    case_id: str
    text: str
    status: str
    location_summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    audio_url: Optional[str] = None
