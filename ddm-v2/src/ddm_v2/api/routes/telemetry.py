"""telemetry.py — Phase 7: WebSocket endpoint for real-time IoT telemetry.

Endpoint:
  ``GET /api/v1/telemetry/stream``  (WebSocket upgrade)

Protocol:
  - Client connects with a valid Bearer token in the ``Authorization`` query
    parameter or header (same token as the REST API).
  - Server streams newline-delimited JSON messages as they arrive from MQTT.
  - Message shape:
      {
        "station_id": "ST-1",
        "line_id": "line_1",
        "event_type": "fasten_ok" | "fasten_timeout" | "error",
        "timestamp": "<ISO-8601>",
        ... (any extra fields published by the IoT device)
      }
  - Client may send a text frame at any time (treated as a keep-alive ping;
    the server echoes ``{"pong": true}``).

Authentication is intentionally lightweight for the WebSocket upgrade because
standard HTTP headers are not always available during the WS handshake in all
browser environments.  The token is accepted as a query parameter ``token=``
OR in the ``Authorization: Bearer …`` header.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ddm_v2.services.auth_service import decode_access_token
from ddm_v2.services.telemetry_service import register_queue, unregister_queue

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])
logger = logging.getLogger(__name__)


@router.websocket("/stream")
async def telemetry_stream(
    websocket: WebSocket,
    token: str | None = Query(default=None, description="JWT bearer token for authentication"),
) -> None:
    """
    WebSocket stream that forwards live MQTT telemetry events to the frontend.

    Accepts the JWT via ``?token=<jwt>`` query param (browser WebSocket API
    does not support custom headers) OR ``Authorization: Bearer <jwt>`` header.
    """
    # ── Authenticate ──────────────────────────────────────────────────────────
    raw_token = token
    if raw_token is None:
        auth_header = websocket.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[len("Bearer "):]

    if raw_token is None or decode_access_token(raw_token) is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    logger.info("Telemetry WS client connected from %s", websocket.client)

    q: asyncio.Queue[str] = asyncio.Queue(maxsize=128)
    register_queue(q)

    try:
        # Run two concurrent tasks:
        #  1. forward MQTT messages from queue → client
        #  2. receive keep-alive pings from client (prevents idle timeout)
        async def _send_loop() -> None:
            while True:
                payload = await q.get()
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(payload)

        async def _receive_loop() -> None:
            while True:
                text = await websocket.receive_text()
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text('{"pong":true}')

        send_task = asyncio.create_task(_send_loop())
        recv_task = asyncio.create_task(_receive_loop())
        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for t in pending:
            t.cancel()
        # Re-raise any unexpected exception for visibility in logs
        for t in done:
            exc = t.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.warning("Telemetry WS task raised: %s", exc)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Telemetry WS unexpected error: %s", exc)
    finally:
        unregister_queue(q)
        logger.info("Telemetry WS client disconnected")
