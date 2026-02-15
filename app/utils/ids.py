"""Noir-themed case ID generation."""
import random
import uuid

ADJECTIVES = [
    "Crimson", "Midnight", "Silent", "Shadow", "Obsidian", "Velvet",
    "Phantom", "Smoke", "Iron", "Steel", "Cold", "Deep", "Dark",
    "Alibi", "Cipher", "Code", "Whisper", "Echo", "Ghost",
]

NOUNS = [
    "Alibi", "Cipher", "Code", "Whisper", "Echo", "Ghost",
    "Cipher", "Dossier", "Agent", "Drop", "Signal", "Trace",
    "File", "Case", "Wire", "Source", "Asset", "Cover",
]


def generate_case_id() -> str:
    """Generate noir-themed case ID: CASE-{ADJECTIVE}-{NOUN}-{4digits}."""
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    digits = str(random.randint(1000, 9999))
    return f"CASE-{adj}-{noun}-{digits}"


def generate_report_id() -> str:
    """Generate unique report ID."""
    return f"RPT-{uuid.uuid4().hex[:12].upper()}"


def generate_node_id(prefix: str = "N") -> str:
    """Generate unique graph node ID."""
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def generate_edge_id() -> str:
    """Generate unique graph edge ID."""
    return f"E-{uuid.uuid4().hex[:12].upper()}"


def generate_alert_id() -> str:
    """Generate unique alert ID."""
    return f"ALT-{uuid.uuid4().hex[:12].upper()}"
