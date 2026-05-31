"""Synchronous-first event bus for the agentvoca pipeline.

Handlers are called in subscription order. Async handlers are wrapped
in a thread executor. No event is dropped silently; unhandled events
are logged at DEBUG level.
"""

import asyncio
import logging
from typing import Any, Callable, Type, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class EventBus:
    """Simple synchronous event bus.

    Modules subscribe to event types and publish events. The bus
    dispatches events to all registered handlers in subscription order.
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """Register a handler for the given event type.

        Args:
            event_type: The dataclass type to subscribe to.
            handler: Callable that accepts an instance of event_type.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def publish(self, event: object) -> None:
        """Publish an event to all registered handlers.

        Synchronous handlers are called immediately. Async handlers are
        scheduled on the running event loop if one exists, otherwise
        executed via asyncio.run().

        Args:
            event: An event dataclass instance.
        """
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])

        if not handlers:
            logger.debug("No handlers registered for %s", event_type.__name__)
            return

        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        # No running loop — run the coroutine synchronously
                        asyncio.run(result)
                    else:
                        # A loop is running — schedule the coroutine
                        loop.create_task(result)
            except Exception:
                logger.exception(
                    "Handler %s failed for event %s",
                    handler.__name__,
                    event_type.__name__,
                )

    def unsubscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """Remove a previously registered handler.

        Args:
            event_type: The event type the handler is registered for.
            handler: The handler to remove.

        Raises:
            ValueError: If the handler is not registered for this event type.
        """
        handlers = self._subscribers.get(event_type, [])
        if handler not in handlers:
            raise ValueError(f"Handler {handler!r} not registered for {event_type.__name__}")
        handlers.remove(handler)
        if not handlers:
            del self._subscribers[event_type]
