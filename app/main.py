"""Shadow Bureau: Dead Drop — FastAPI app."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.event_bus import start_event_bus, stop_event_bus
from app.routers import reports, cases, alerts, ws, seed, files

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start event bus, Backboard assistants, Neo4j, blackboard controller; stop on shutdown."""
    await start_event_bus()
    from app.graph_state import set_controller
    from app.pipelines.orchestrator import register_knowledge_sources
    from app.services.backboard_client import get_or_create_assistants
    from app.services.graph_db import GraphDatabase

    if getattr(settings, "backboard_api_key", ""):
        try:
            assistants = await get_or_create_assistants()
            logger.info("Backboard assistants ready: %d", len(assistants))
        except Exception as e:
            logger.warning("Backboard assistants init failed: %s", e)
    else:
        logger.info("BACKBOARD_API_KEY not set — forensic analysis will use fallback scores")

    # Neo4j AuraDB: connect and verify
    graph_db = GraphDatabase.get_instance()
    if graph_db.driver:
        if graph_db.verify_connection():
            logger.info("Neo4j connection verified (RETURN 1 OK)")
        else:
            logger.warning("Neo4j connection verify failed")

    controller = register_knowledge_sources()
    set_controller(controller)
    controller.start()
    logger.info("Shadow Bureau backend started (blackboard: %d sources)", controller.source_count)
    yield
    graph_db.close()
    await controller.stop()
    await stop_event_bus()
    logger.info("Shadow Bureau backend stopped")


app = FastAPI(
    title="Shadow Bureau: Dead Drop",
    description="Noir-themed campus intelligence platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reports.router)
app.include_router(cases.router)
app.include_router(alerts.router)
app.include_router(ws.router)
app.include_router(seed.router)
app.include_router(files.router)


@app.get("/health")
async def health():
    """Health check."""
    from app.pipelines.orchestrator import _controller as ctrl
    return {
        "status": "ok",
        "knowledge_sources": ctrl.source_count if ctrl else 0,
        "controller_running": ctrl.running if ctrl else False,
    }
