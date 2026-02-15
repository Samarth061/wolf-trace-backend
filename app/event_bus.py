"""Async event bus using asyncio.Queue."""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

EventPayload = dict[str, Any]
EventHandler = Callable[[EventPayload], Coroutine[Any, Any, None]]

_handlers: dict[str, list[EventHandler]] = defaultdict(list)
_queue: asyncio.Queue[tuple[str, EventPayload]] | None = None
_dispatcher_task: asyncio.Task | None = None


def on(event_name: str) -> Callable[[EventHandler], EventHandler]:
    """Decorator to register an event handler."""

    def decorator(handler: EventHandler) -> EventHandler:
        _handlers[event_name].append(handler)
        return handler

    return decorator


async def emit(event_name: str, payload: EventPayload) -> None:
    """Emit an event to the bus. Non-blocking."""
    if _queue is not None:
        await _queue.put((event_name, payload))


async def _dispatch_loop() -> None:
    """Process events from queue and invoke handlers."""
    assert _queue is not None
    while True:
        try:
            event_name, payload = await _queue.get()
            handlers = _handlers.get(event_name, [])
            for h in handlers:
                try:
                    await h(payload)
                except Exception as e:
                    logger.exception("Event handler %s failed for %s: %s", h.__name__, event_name, e)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Dispatch loop error")


async def start_event_bus() -> None:
    """Start the event bus dispatcher."""
    global _queue, _dispatcher_task
    _queue = asyncio.Queue()
    _dispatcher_task = asyncio.create_task(_dispatch_loop())
    logger.info("Event bus started")


async def stop_event_bus() -> None:
    """Stop the event bus dispatcher."""
    global _dispatcher_task
    if _dispatcher_task:
        _dispatcher_task.cancel()
        try:
            await _dispatcher_task
        except asyncio.CancelledError:
            pass
        _dispatcher_task = None
    logger.info("Event bus stopped")
