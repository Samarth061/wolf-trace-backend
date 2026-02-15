"""Seed router: POST /api/seed to populate in-memory state with mock data."""
from fastapi import APIRouter

from app.seed_data import seed_all

router = APIRouter(prefix="/api", tags=["seed"])


@router.post("/seed")
async def seed_mock_data():
    """Populate backend with mock data from frontend for testing. Idempotent."""
    counts = seed_all()
    return {"status": "seeded", **counts}
