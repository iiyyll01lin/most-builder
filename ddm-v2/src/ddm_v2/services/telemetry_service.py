"""telemetry_service.py — Phase 7: IoT MQTT → WebSocket telemetry bridge.

Architecture:
  - ``run_mqtt_listener()`` runs as a long-lived asyncio task inside the FastAPI
    lifespan.  It connects to the Mosquitto broker, subscribes to the factory
    topic wildcard, and forwards every message to all registered WebSocket queues.
  - WebSocket endpoint handlers call ``register_queue`` / ``unregister_queue`` to
    join / leave the broadcast set.  A ``asyncio.Queue`` per connection decouples
    the MQTT receive loop from per-client send latency.

Topic convention:
  ``factory/<line_id>/<station_id>/event``
  Payload (JSON): ``{"event_type": "fasten_ok"|"fasten_timeout"|"error", ...}``
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

try:
    import aiomqtt
except ImportError:  # pragma: no cover — optional at import time for unit tests
    aiomqtt = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ─── Per-connection broadcast queues ─────────────────────────────────────────

# Protected only by GIL; a thread-safe set is not required in a single-threaded
# async context.  maxsize=128 gives a ~5 s buffer at 25 msg/s before dropping.
_ws_queues: set[asyncio.Queue[str]] = set()


def register_queue(q: asyncio.Queue[str]) -> None:
    """Register a WebSocket queue to receive all subsequent MQTT messages."""
    _ws_queues.add(q)


def unregister_queue(q: asyncio.Queue[str]) -> None:
    """Unregister a WebSocket queue on disconnect."""
    _ws_queues.discard(q)


def _broadcast(payload: str) -> None:
    """Fire-and-forget non-blocking push to all WebSocket queues."""
    for q in list(_ws_queues):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Slow WebSocket consumer — drop the oldest item and re-enqueue.
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


# ─── MQTT listener (background task) ─────────────────────────────────────────

async def run_mqtt_listener(broker_host: str, broker_port: int) -> None:
    """
    Connect to the Mosquitto broker and forward telemetry events to all
    registered WebSocket queues.  Automatically reconnects with a fixed back-off
    interval on connection failures.
    """
    if aiomqtt is None:
        logger.error("aiomqtt is not installed; telemetry bridge is disabled")
        return

    reconnect_interval = 5  # seconds

    while True:
        try:
            async with aiomqtt.Client(hostname=broker_host, port=broker_port) as client:
                logger.info("MQTT connected to %s:%d", broker_host, broker_port)
                await client.subscribe("factory/+/+/event")
                async for message in client.messages:
                    _handle_message(str(message.topic), bytes(message.payload))
        except aiomqtt.MqttError as exc:
            logger.warning(
                "MQTT disconnected (%s), reconnecting in %ds …", exc, reconnect_interval
            )
            await asyncio.sleep(reconnect_interval)
        except asyncio.CancelledError:
            logger.info("MQTT listener task cancelled — shutting down cleanly")
            return


def _handle_message(topic: str, raw: bytes) -> None:
    """Parse a raw MQTT message and broadcast a structured JSON payload."""
    # Topic: factory/<line_id>/<station_id>/event
    parts = topic.split("/")
    line_id = parts[1] if len(parts) > 1 else "unknown"
    station_id = parts[2] if len(parts) > 2 else "unknown"

    try:
        body: dict = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        body = {"raw": raw.decode("utf-8", errors="replace")}

    event = {
        "station_id": station_id,
        "line_id": line_id,
        "event_type": body.get("event_type", "unknown"),
        "timestamp": datetime.now(UTC).isoformat(),
        **{k: v for k, v in body.items() if k not in ("event_type",)},
    }
    _broadcast(json.dumps(event))
