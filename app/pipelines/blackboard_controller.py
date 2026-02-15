"""Blackboard Controller — schedules knowledge sources by priority, with cooldowns and dedup."""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

MAX_RE_TRIGGERS_PER_CASE = 10


class Priority(IntEnum):
    CRITICAL = 0   # Clustering — dedup before wasting compute
    HIGH = 1       # Forensics — evidence analysis
    MEDIUM = 2     # Network — claim extraction, fact-checking
    LOW = 3        # Classifier — role assignment after others finish
    BACKGROUND = 4  # Cleanup


@dataclass
class KnowledgeSource:
    name: str
    priority: Priority
    trigger_types: list[str]
    handler: Callable[..., Awaitable[None]]
    condition: Callable[[dict[str, Any]], bool] | None = None
    cooldown_seconds: float = 1.0
    _last_run: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def can_fire(self, event_type: str, payload: dict[str, Any], active_tasks: set[str]) -> bool:
        if event_type not in self.trigger_types:
            return False
        if self.condition and not self.condition(payload):
            return False
        case_id = payload.get("case_id", "")
        if not case_id:
            return False
        key = f"{self.name}:{case_id}"
        if key in active_tasks:
            return False
        now = time.monotonic()
        if now - self._last_run[case_id] < self.cooldown_seconds:
            return False
        return True

    def mark_run(self, case_id: str) -> None:
        self._last_run[case_id] = time.monotonic()


@dataclass(order=True)
class QueuedTask:
    """Comparable for PriorityQueue: (priority, sequence)."""
    priority: int
    sequence: int
    source_name: str = field(compare=False)
    case_id: str = field(compare=False)
    event_type: str = field(compare=False)
    payload: dict[str, Any] = field(compare=False)
    timestamp: float = field(compare=False, default_factory=time.monotonic)


_task_counter = 0


def _next_sequence() -> int:
    global _task_counter
    _task_counter += 1
    return _task_counter


class BlackboardController:
    """Watches graph mutations, schedules knowledge sources by priority."""

    def __init__(self) -> None:
        self._sources: list[KnowledgeSource] = []
        self._queue: asyncio.PriorityQueue[QueuedTask] = asyncio.PriorityQueue()
        self._active_tasks: set[str] = set()
        self._trigger_counts: dict[str, int] = defaultdict(int)
        self._running = False
        self._task: asyncio.Task | None = None

    def register(
        self,
        name: str,
        priority: Priority,
        trigger_types: list[str],
        handler: Callable[..., Awaitable[None]],
        condition: Callable[[dict[str, Any]], bool] | None = None,
        cooldown_seconds: float = 1.0,
    ) -> None:
        self._sources.append(KnowledgeSource(
            name=name,
            priority=priority,
            trigger_types=trigger_types,
            handler=handler,
            condition=condition,
            cooldown_seconds=cooldown_seconds,
        ))

    async def notify(self, event_type: str, payload: dict[str, Any]) -> None:
        """Called by graph_state on every mutation. Evaluates and enqueues matching sources."""
        case_id = payload.get("case_id", "")
        if not case_id:
            return
        if self._trigger_counts[case_id] >= MAX_RE_TRIGGERS_PER_CASE:
            return
        for src in self._sources:
            if src.can_fire(event_type, payload, self._active_tasks):
                key = f"{src.name}:{case_id}"
                self._active_tasks.add(key)
                self._trigger_counts[case_id] += 1
                task = QueuedTask(
                    priority=int(src.priority),
                    sequence=_next_sequence(),
                    source_name=src.name,
                    case_id=case_id,
                    event_type=event_type,
                    payload=payload,
                )
                await self._queue.put(task)

    async def _execute_task(self, qt: QueuedTask) -> None:
        key = f"{qt.source_name}:{qt.case_id}"
        try:
            src = next((s for s in self._sources if s.name == qt.source_name), None)
            if not src:
                return
            src.mark_run(qt.case_id)
            await src.handler(qt.payload)
        except Exception as e:
            logger.exception("Knowledge source %s failed: %s", qt.source_name, e)
        finally:
            self._active_tasks.discard(key)

    async def run(self) -> None:
        """Main loop — dequeues and executes by priority."""
        self._running = True
        logger.info("Blackboard controller started")
        while self._running:
            try:
                qt = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                await self._execute_task(qt)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Controller loop error: %s", e)
        logger.info("Blackboard controller stopped")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self.run())
        return self._task

    @property
    def source_count(self) -> int:
        return len(self._sources)

    @property
    def running(self) -> bool:
        return self._running
