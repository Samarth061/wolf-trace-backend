"""In-memory audit log for action tracking."""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AuditEntry:
    actor: str
    action: str
    case_id: Optional[str]
    details: Optional[str]
    timestamp: datetime = field(default_factory=datetime.utcnow)


_audit_log: deque[AuditEntry] = deque(maxlen=10_000)


def log_action(
    actor: str,
    action: str,
    case_id: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """Record an action to the in-memory audit log."""
    _audit_log.append(
        AuditEntry(actor=actor, action=action, case_id=case_id, details=details)
    )


def get_audit_log(limit: int = 100) -> list[AuditEntry]:
    """Retrieve recent audit entries (most recent first)."""
    entries = list(_audit_log)
    return list(reversed(entries[-limit:]))
