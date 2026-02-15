"""Case and Evidence models for Neo4j persistence."""
from typing import Optional

from pydantic import BaseModel


class CaseCreate(BaseModel):
    """Request body for POST /api/cases."""

    case_id: str
    title: str = ""
    description: str = ""


class CaseOut(BaseModel):
    """Response for case creation."""

    id: str
    case_id: str = ""
    title: str
    description: str
    label: str = ""
    status: str = "active"
    node_count: int = 0
    updated_at: Optional[str] = None
    created_at: Optional[str] = None


class EvidenceCreate(BaseModel):
    """Request body for POST /api/cases/{case_id}/evidence."""

    id: Optional[str] = None  # Auto-generated if not provided
    type: str = "text"  # e.g. 'photo', 'text', 'video'
    content: str = ""
    url: Optional[str] = None
    timestamp: Optional[str] = None


class EvidenceOut(BaseModel):
    """Response for evidence creation."""

    id: str
    type: str
    content: str
    url: str = ""
    timestamp: Optional[str] = None


class EdgeCreate(BaseModel):
    """Request body for POST /api/cases/{case_id}/edges (Red String — link two nodes)."""

    source_id: str
    target_id: str
    type: str = "SUSPECTED_LINK"
    note: Optional[str] = None


class EdgeOut(BaseModel):
    """Response for edge/link creation."""

    source_id: str
    target_id: str
    type: str
    note: Optional[str] = None
    created_at: Optional[str] = None
