#!/usr/bin/env python3
"""Create a TwelveLabs index for WolfTrace video analysis."""
import asyncio
import httpx
from app.config import settings

BASE_URL = "https://api.twelvelabs.io/v1.3"

async def create_index():
    """Create a new TwelveLabs index with Marengo 2.6 engine."""

    if not settings.twelvelabs_api_key:
        print("❌ Error: TWELVELABS_API_KEY not found in .env")
        return

    headers = {
        "x-api-key": settings.twelvelabs_api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "engine_id": "marengo2.6",
        "index_name": "wolftrace-campus-videos",
        "index_options": ["visual", "conversation", "text_in_video", "logo"],
        "addons": ["thumbnail"]
    }

    print("🔄 Creating TwelveLabs index...")
    print(f"   Engine: marengo2.6")
    print(f"   Name: wolftrace-campus-videos")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}/indexes",
                headers=headers,
                json=payload
            )

            if response.is_success:
                data = response.json()
                index_id = data.get("_id")
                print(f"\n✅ Index created successfully!")
                print(f"   Index ID: {index_id}")
                print(f"\n📝 Add this to your .env file:")
                print(f"   TWELVELABS_INDEX_ID={index_id}")
            else:
                print(f"\n❌ Error: {response.status_code}")
                print(f"   Response: {response.text}")

    except Exception as e:
        print(f"\n❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(create_index())
