#!/usr/bin/env python3
"""demo_orchestrator.py — Phase 10: IoT Demo Orchestrator

Publishes scripted MQTT telemetry events that represent a complete
"Project Alpha: Smart Speaker Assembly" line cycle.

Narrative highlights
--------------------
• Follows the exact SOP V1.0 station order: ST-1 → ST-2A/ST-2B → ST-3 → ST-4 → ST-5
• 1P2M moment: events for ST-2A and ST-2B are fired 300 ms apart → the 3D
  Digital Twin flashes BOTH nodes nearly simultaneously, demonstrating that
  a single operator drives two machines in parallel.
• Each station's console line shows: station ID, action label, event type,
  and a live cycle-time counter so observers can see throughput in real-time.
• The loop is infinite — each pass represents one finished Smart Speaker unit.
  Press Ctrl-C to exit cleanly.

Usage:
  pip install paho-mqtt
  python scripts/demo_orchestrator.py [--host localhost] [--port 1883]
  python scripts/demo_orchestrator.py --host localhost --port 1883 --cycle-time 6.0
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import signal
import sys
import time

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

MQTT_LINE = "line_alpha"

# Each station beat: (station_id, action_label, event_type, hold_seconds)
# hold_seconds = how long to pause before the next beat (simulates operation time)
# 1P2M pairs are identified by having the same operator (ALPHA-ST-2a / ALPHA-ST-2b).
_STATION_BEATS: list[dict] = [
    # ── Station 1: Chassis Prep (1P1M) ───────────────────────────────────────
    {
        "station_id":   "ALPHA-ST-1",
        "action":       "Grab Chassis from bin",
        "event_type":   "pick_ok",
        "hold":         1.4,
        "annotation":   "",
        "is_ctq":       False,
    },
    {
        "station_id":   "ALPHA-ST-1",
        "action":       "Place Chassis on fixture",
        "event_type":   "place_ok",
        "hold":         1.8,
        "annotation":   "",
        "is_ctq":       False,
    },
    {
        "station_id":   "ALPHA-ST-1",
        "action":       "Inspect Chassis orientation",
        "event_type":   "scan_ok",
        "hold":         0.9,
        "annotation":   "",
        "is_ctq":       False,
    },
    # ── Station 2A + 2B: Speaker Driver Install (1P2M) ───────────────────────
    # Beat fires on ST-2A; immediately after, a second beat fires on ST-2B
    # (separated by 1P2M_GAP_S).  The 3D Twin flashes both nodes together.
    {
        "station_id":   "ALPHA-ST-2a",
        "action":       "Grab Driver ×2 (Machine A)",
        "event_type":   "pick_ok",
        "hold":         0.0,   # no hold — immediately cross to Machine B
        "annotation":   "↔ 1P2M",
        "is_ctq":       True,
        "1p2m_peer": {
            "station_id":   "ALPHA-ST-2b",
            "action":       "Grab Driver ×2 (Machine B)",
            "event_type":   "pick_ok",
        },
    },
    {
        "station_id":   "ALPHA-ST-2a",
        "action":       "Place Driver into enclosure (Machine A)",
        "event_type":   "place_ok",
        "hold":         0.0,
        "annotation":   "↔ 1P2M",
        "is_ctq":       True,
        "1p2m_peer": {
            "station_id":   "ALPHA-ST-2b",
            "action":       "Place Driver into enclosure (Machine B)",
            "event_type":   "place_ok",
        },
    },
    {
        "station_id":   "ALPHA-ST-2a",
        "action":       "Fasten M3×4 screws — CTQ torque 0.6 Nm (Machine A)",
        "event_type":   "fasten_ok",
        "hold":         2.6,   # machine A runs torque verify while op is at B
        "annotation":   "↔ 1P2M  ★ CTQ",
        "is_ctq":       True,
        "torque_nm":    0.6,
        "1p2m_peer": {
            "station_id":   "ALPHA-ST-2b",
            "action":       "Fasten M3×4 screws — CTQ torque 0.6 Nm (Machine B)",
            "event_type":   "fasten_ok",
            "torque_nm":    0.6,
        },
    },
    # ST-2A autonomous torque-verify completes while op is still at ST-2B
    {
        "station_id":   "ALPHA-ST-2a",
        "action":       "Torque verify complete — autonomous (Machine A idle)",
        "event_type":   "fasten_ok",
        "hold":         0.8,
        "annotation":   "↔ 1P2M  (Machine A auto-verify while op at B)",
        "is_ctq":       True,
        "torque_nm":    0.6,
    },
    # ── Station 3: PCB Assembly — CTQ + ESD skill gate ───────────────────────
    {
        "station_id":   "ALPHA-ST-3",
        "action":       "Grab PCB Audio Module [ION FAN ON, anti-static gloves]",
        "event_type":   "pick_ok",
        "hold":         1.4,
        "annotation":   "★ CTQ  ⚡ ESD",
        "is_ctq":       True,
    },
    {
        "station_id":   "ALPHA-ST-3",
        "action":       "Seat PCB into chassis ZIF connector",
        "event_type":   "place_ok",
        "hold":         1.8,
        "annotation":   "★ CTQ  ⚡ ESD  [FATP07 skill required]",
        "is_ctq":       True,
    },
    {
        "station_id":   "ALPHA-ST-3",
        "action":       "Scan PCB barcode — traceability record",
        "event_type":   "scan_ok",
        "hold":         0.4,
        "annotation":   "",
        "is_ctq":       False,
    },
    # ── Station 4: Cable Routing ──────────────────────────────────────────────
    {
        "station_id":   "ALPHA-ST-4",
        "action":       "Grab cable harness",
        "event_type":   "pick_ok",
        "hold":         1.4,
        "annotation":   "",
        "is_ctq":       False,
    },
    {
        "station_id":   "ALPHA-ST-4",
        "action":       "Route cable through chassis guide clips",
        "event_type":   "place_ok",
        "hold":         2.2,
        "annotation":   "",
        "is_ctq":       False,
    },
    # ── Station 5: Final QA & Barcode Scan ───────────────────────────────────
    {
        "station_id":   "ALPHA-ST-5",
        "action":       "Inspect completed assembly (visual + tactile)",
        "event_type":   "scan_ok",
        "hold":         0.9,
        "annotation":   "",
        "is_ctq":       False,
    },
    {
        "station_id":   "ALPHA-ST-5",
        "action":       "Scan finished product RFID label — PASS",
        "event_type":   "scan_ok",
        "hold":         0.4,
        "annotation":   "✓ UNIT COMPLETE",
        "is_ctq":       False,
    },
]

# 1P2M inter-machine gap — fires the peer event this many seconds after primary
_1P2M_GAP_S = 0.30

# ─── MQTT helpers ────────────────────────────────────────────────────────────


def _make_payload(beat: dict, unit_no: int) -> dict:
    payload: dict = {
        "event_type": beat["event_type"],
        "unit_no":    unit_no,
        "station_id": beat["station_id"],
        "action":     beat["action"],
        "is_ctq":     beat.get("is_ctq", False),
    }
    if "torque_nm" in beat:
        # Add ±2 % realistic measurement noise
        meas = beat["torque_nm"] * (1.0 + random.uniform(-0.02, 0.02))
        payload["torque_nm"] = round(meas, 4)
    return payload


def _publish(client, topic: str, payload: dict) -> None:
    msg = json.dumps(payload)
    result = client.publish(topic, msg, qos=0)

    # Soft-import mqtt constants
    import paho.mqtt.client as mqtt  # type: ignore[import]
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        pass  # success handled by caller's console output
    else:
        logger.warning("Publish failed rc=%d  topic=%s", result.rc, topic)


# ─── Console formatting ───────────────────────────────────────────────────────

_STATION_COLORS = {
    "ALPHA-ST-1":  "\033[36m",  # cyan
    "ALPHA-ST-2a": "\033[35m",  # magenta
    "ALPHA-ST-2b": "\033[35m",  # magenta (same — 1P2M pair)
    "ALPHA-ST-3":  "\033[33m",  # yellow
    "ALPHA-ST-4":  "\033[34m",  # blue
    "ALPHA-ST-5":  "\033[32m",  # green
}
_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_RED   = "\033[31m"


def _banner() -> None:
    print()
    print(f"{_BOLD}{'═' * 72}{_RESET}")
    print(f"{_BOLD}  DDM v2  ·  Phase 10 Demo Orchestrator{_RESET}")
    print(f"{_BOLD}  Project Alpha: Smart Speaker Assembly{_RESET}")
    print(f"{_DIM}  Watch the 3D Digital Twin respond at  http://localhost:8000{_RESET}")
    print(f"{_BOLD}{'═' * 72}{_RESET}")
    print()
    print(f"  Station layout  (1P2M stations in {_BOLD}bold{_RESET}):")
    print(f"    ST-1   Chassis Prep              ─── 1P1M")
    print(f"    {_BOLD}ST-2A  Driver Install  ─┐{_RESET}")
    print(f"    {_BOLD}ST-2B  Driver Install  ─┘  1P2M  (1 operator × 2 machines){_RESET}")
    print(f"    ST-3   PCB & Audio Module  ★ CTQ ─── 1P1M")
    print(f"    ST-4   Cable Routing              ─── 1P1M")
    print(f"    ST-5   Final QA & Barcode         ─── 1P1M")
    print()
    print(f"  {_DIM}Press Ctrl-C to stop the orchestrator.{_RESET}")
    print()


def _log_beat(beat: dict, unit_no: int, cycle_idx: int) -> None:
    color  = _STATION_COLORS.get(beat["station_id"], "")
    ann    = f"  {_BOLD}{beat['annotation']}{_RESET}" if beat.get("annotation") else ""
    prefix = f"{color}▶ {beat['station_id']:<14}{_RESET}"
    evtype = f"{_DIM}{beat['event_type']:<14}{_RESET}"
    action = beat["action"][:55]
    print(f"  {prefix}  {evtype}  {action}{ann}")


def _log_1p2m_peer(peer: dict, unit_no: int) -> None:
    color = _STATION_COLORS.get(peer["station_id"], "")
    print(
        f"  {color}▶ {peer['station_id']:<14}{_RESET}"
        f"  {_DIM}{peer['event_type']:<14}{_RESET}"
        f"  {peer['action'][:55]}"
        f"  {_BOLD}↔ 1P2M  (parallel){_RESET}"
    )


def _log_unit_complete(unit_no: int, elapsed: float, beats: int) -> None:
    print()
    print(
        f"  {_BOLD}\033[32m✓ Unit #{unit_no:04d} complete{_RESET}"
        f"  cycle={elapsed:.1f}s   beats={beats}"
    )
    print(f"  {'─' * 68}")
    print()


# ─── Main run loop ────────────────────────────────────────────────────────────


def run(host: str, port: int, cycle_time: float) -> None:
    try:
        import paho.mqtt.client as mqtt  # type: ignore[import]
    except ImportError:
        logger.error(
            "paho-mqtt is not installed.  Run:  pip install paho-mqtt"
        )
        sys.exit(1)

    client = mqtt.Client(client_id="ddm-demo-orchestrator", protocol=mqtt.MQTTv5)

    connected = [False]

    def on_connect(c, userdata, flags, rc, properties):  # noqa: ANN001
        if rc == 0:
            connected[0] = True
            logger.info("✅  Connected to MQTT broker  %s:%d", host, port)
        else:
            logger.error("MQTT connect failed  rc=%d", rc)
            sys.exit(1)

    def on_disconnect(c, userdata, rc, properties):  # noqa: ANN001
        if rc != 0:
            logger.warning("MQTT disconnected unexpectedly  rc=%d", rc)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
        client.connect(host, port, keepalive=60)
    except ConnectionRefusedError:
        logger.error(
            "Could not connect to MQTT broker at %s:%d  "
            "(Is the stack running?  Run `make demo` first.)",
            host, port,
        )
        sys.exit(1)

    client.loop_start()

    # Brief wait for the on_connect callback
    deadline = time.monotonic() + 5.0
    while not connected[0] and time.monotonic() < deadline:
        time.sleep(0.1)
    if not connected[0]:
        logger.error("MQTT connection timed out after 5 s")
        sys.exit(1)

    # Graceful shutdown
    _running = [True]

    def _stop(sig, frame):  # noqa: ANN001
        print()
        logger.info("Signal %s received — stopping orchestrator …", sig)
        _running[0] = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    _banner()

    unit_no   = 1
    total_beats = 0

    # Compute the natural cycle time from beat holds to auto-scale
    natural_ct = sum(b["hold"] for b in _STATION_BEATS)
    # speed_factor compresses or stretches holds to match the requested cycle_time
    speed_factor = cycle_time / natural_ct if natural_ct > 0 else 1.0

    while _running[0]:
        cycle_start = time.monotonic()
        print(f"  {_BOLD}Unit #{unit_no:04d}{_RESET}  ──  Project Alpha · Smart Speaker Assembly")

        for beat in _STATION_BEATS:
            if not _running[0]:
                break

            topic   = f"factory/{MQTT_LINE}/{beat['station_id']}/event"
            payload = _make_payload(beat, unit_no)
            _publish(client, topic, payload)
            _log_beat(beat, unit_no, total_beats)
            total_beats += 1

            # 1P2M peer event: fires _1P2M_GAP_S after the primary
            peer = beat.get("1p2m_peer")
            if peer:
                time.sleep(_1P2M_GAP_S * speed_factor)
                peer_topic   = f"factory/{MQTT_LINE}/{peer['station_id']}/event"
                peer_payload = {
                    "event_type": peer["event_type"],
                    "unit_no":    unit_no,
                    "station_id": peer["station_id"],
                    "action":     peer["action"],
                    "is_ctq":     beat.get("is_ctq", False),
                }
                if "torque_nm" in peer:
                    meas = peer["torque_nm"] * (1.0 + random.uniform(-0.02, 0.02))
                    peer_payload["torque_nm"] = round(meas, 4)
                _publish(client, peer_topic, peer_payload)
                _log_1p2m_peer(peer, unit_no)
                total_beats += 1

            hold = beat["hold"] * speed_factor
            if hold > 0:
                time.sleep(hold)

        elapsed = time.monotonic() - cycle_start
        _log_unit_complete(unit_no, elapsed, total_beats)
        unit_no += 1

    client.loop_stop()
    client.disconnect()
    logger.info("Orchestrator shut down cleanly.  %d beats published.", total_beats)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="DDM-v2 Phase 10 IoT Demo Orchestrator — Project Alpha",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--host", default="localhost",
                   help="Mosquitto broker hostname")
    p.add_argument("--port", type=int, default=1883,
                   help="Mosquitto broker port")
    p.add_argument("--cycle-time", type=float, default=14.0,
                   help="Seconds per completed Smart Speaker unit")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(host=args.host, port=args.port, cycle_time=args.cycle_time)
