"""Neo4j AuraDB connection — singleton driver with FastAPI dependency."""
import logging
from typing import Generator

from neo4j import GraphDatabase as Neo4j
from neo4j import Session as Neo4jSession

from app.config import settings

logger = logging.getLogger(__name__)

_instance: "GraphDatabase | None" = None


class GraphDatabase:
    """Singleton Neo4j driver for AuraDB. Connect on startup, close on shutdown."""

    def __init__(self) -> None:
        self._driver = None
        if settings.neo4j_uri and settings.neo4j_username and settings.neo4j_password:
            self._driver = Neo4j.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
            )
            logger.info("Neo4j driver initialized for %s", settings.neo4j_uri)
        else:
            logger.warning(
                "Neo4j not configured: set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD"
            )

    @property
    def driver(self):
        return self._driver

    @classmethod
    def get_instance(cls) -> "GraphDatabase":
        """Return the singleton instance."""
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    def verify_connection(self) -> bool:
        """Run a simple query to verify the connection. Returns True if OK."""
        if not self._driver:
            return False
        try:
            with self._driver.session() as session:
                result = session.run("RETURN 1 AS n")
                record = result.single()
                return record is not None and record["n"] == 1
        except Exception as e:
            logger.exception("Neo4j connection verify failed: %s", e)
            return False

    @classmethod
    def get_session(cls) -> Generator[Neo4jSession, None, None]:
        """FastAPI dependency: yields a Neo4j session, closes when done."""
        db = cls.get_instance()
        if not db._driver:
            raise RuntimeError("Neo4j driver not initialized")
        with db._driver.session() as session:
            yield session

    def close(self) -> None:
        """Shut down the driver. Call on application shutdown."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j driver closed")
