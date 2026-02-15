"""Graph node/edge models for case board."""
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    REPORT = "report"
    EXTERNAL_SOURCE = "external_source"
    FACT_CHECK = "fact_check"
    MEDIA_VARIANT = "media_variant"


class EdgeType(str, Enum):
    SIMILAR_TO = "similar_to"
    REPOST_OF = "repost_of"
    MUTATION_OF = "mutation_of"
    DEBUNKED_BY = "debunked_by"
    AMPLIFIED_BY = "amplified_by"


class NodeRole(str, Enum):
    """Structural role for edge endpoints."""
    SOURCE = "source"
    TARGET = "target"


class NodeSemanticRole(str, Enum):
    """Semantic role for report nodes (assigned by classifier)."""
    ORIGINATOR = "originator"       # Earliest in timeline
    AMPLIFIER = "amplifier"        # Connected via REPOST_OF
    MUTATOR = "mutator"            # Connected via MUTATION_OF
    UNWITTING_SHARER = "unwitting_sharer"  # No outgoing edges to external sources


class GraphNode(BaseModel):
    id: str
    node_type: NodeType
    case_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GraphEdge(BaseModel):
    id: str
    edge_type: EdgeType
    source_id: str
    target_id: str
    case_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GraphUpdate(BaseModel):
    type: str = "graph_update"
    action: str  # add_node | add_edge | update_node
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
