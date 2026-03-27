#!/usr/bin/env python3
"""simulate_iot_factory.py — Phase 7: IoT Factory Event Simulator

Publishes random tool events to the MQTT broker every few seconds to simulate
a live factory line.  Useful for local development and manual QA of the
real-time Digital Twin without physical hardware.

Usage:
  python scripts/simulate_iot_factory.py [--host localhost] [--port 1883] \
                                         [--interval 2.0] [--stations ST-1,ST-2,...]

Stop with Ctrl-C; the script exits gracefully.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import signal
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
DEFAULT_INTERVAL = 2.0  # seconds between published events
DEFAULT_LINE = "line_1"
DEFAULT_STATIONS = ["ST-1", "ST-2", "ST-3", "ST-4", "ST-5"]

# Weighted event distribution: most operations succeed
EVENT_TYPES = [
    ("fasten_ok",      0.70),
    ("fasten_timeout", 0.15),
    ("error",          0.10),
    ("warning",        0.05),
]
_POPULATION, _WEIGHTS = zip(*EVENT_TYPES)

# ─── Payload helpers ─────────────────────────────────────────────────────────


def _random_event(station_id: str) -> tuple[str, dict]:
    """Return (topic, payload_dict) for a simulated tool event."""
    event_type = random.choices(_POPULATION, weights=_WEIGHTS, k=1)[0]
    torque_nm = round(random.uniform(8.5, 12.5), 3) if "fasten" in event_type else None
    payload: dict = {"event_type": event_type}
    if torque_nm is not None:
        payload["torque_nm"] = torque_nm
    if event_type == "error":
        payload["error_code"] = random.choice(["E_OVERTORQUE", "E_UNDERTORQUE", "E_TIMEOUT"])
    topic = f"factory/{DEFAULT_LINE}/{station_id}/event"
    return topic, payload


# ─── Main loop ───────────────────────────────────────────────────────────────


def run(host: str, port: int, interval: float, stations: list[str]) -> None:
    try:
        import paho.mqtt.client as mqtt  # type: ignore[import]
    except ImportError:
        logger.error(
            "paho-mqtt is not installed.  Run: pip install paho-mqtt && python %s",
            __file__,
        )
        sys.exit(1)

    client = mqtt.Client(client_id="ddm-factory-simulator", protocol=mqtt.MQTTv5)

    def on_connect(c, userdata, flags, rc, properties):  # noqa: ANN001
        if rc == 0:
            logger.info("Connected to MQTT broker %s:%d", host, port)
        else:
            logger.error("MQTT connect failed: rc=%d", rc)
            sys.exit(1)

    def on_disconnect(c, userdata, rc, properties):  # noqa: ANN001
        if rc != 0:
            logger.warning("MQTT unexpectedly disconnected (rc=%d)", rc)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.connect(host, port, keepalive=60)
    client.loop_start()

    # Graceful shutdown on SIGINT / SIGTERM
    _running = [True]

    def _stop(sig, frame):  # noqa: ANN001
        logger.info("Signal %s received — stopping simulator …", sig)
        _running[0] = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info(
        "Simulating %d stations every %.1fs.  Press Ctrl-C to stop.",
        len(stations),
        interval,
    )

    try:
        while _running[0]:
            station_id = random.choice(stations)
            topic, payload = _random_event(station_id)
            result = client.publish(topic, json.dumps(payload), qos=0)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(
                    "→ %s  %s",
                    topic,
                    json.dumps(payload),
                )
            else:
                logger.warning("Publish failed: rc=%d", result.rc)
            time.sleep(interval)
    finally:
        client.loop_stop()
        client.disconnect()
        logger.info("Simulator shut down cleanly.")


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DDM-v2 IoT Factory Event Simulator")
    parser.add_argument("--host", default=DEFAULT_HOST, help="MQTT broker hostname")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT broker port")
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="Seconds between published events",
    )
    parser.add_argument(
        "--stations",
        default=",".join(DEFAULT_STATIONS),
        help="Comma-separated list of station IDs to simulate",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(
        host=args.host,
        port=args.port,
        interval=args.interval,
        stations=[s.strip() for s in args.stations.split(",") if s.strip()],
    )
