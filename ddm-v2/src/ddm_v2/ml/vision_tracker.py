"""Deep Learning CV Pipeline — Phase 6: MediaPipe Hand / Pose Tracker.

``DeepVisionAnalyzer`` processes an MP4/AVI video frame-by-frame using Google
MediaPipe's hand-landmark solution to produce a time-ordered list of discrete
MOST ``SOPAction`` primitives (Reach / Grasp / Move / Place).

Algorithm overview
------------------

1. **Frame extraction** — ``cv2.VideoCapture`` decodes frames at the native FPS
   of the source video.  Every frame is passed to MediaPipe Hands in RGB.

2. **Landmark extraction** — We use the 21-keypoint hand model.  On each frame
   we record:
   - ``centroid``   — mean (x, y) of all 21 landmarks, normalised [0, 1]
   - ``pinch_dist`` — Euclidean distance between THUMB_TIP (4) and INDEX_TIP (8)
   - ``fist_score`` — mean distance of all fingertips from palm base (0)

3. **Multi-frame state machine** (sliding-window, 0.5 s window, 50 % step):

   Each window produces one of four hand-states::

       OPEN  — fist_score > OPEN_THRESHOLD
       FIST  — fist_score <= FIST_THRESHOLD
       PINCH — pinch_dist < PINCH_THRESHOLD (overrides FIST/OPEN)
       IDLE  — no hand detected

   State transitions map to MOST primitives in a cyclic sequence:
   ``Reach → Grasp → Move → Place → Reach …``

   The velocity of the centroid (cm/s equivalent — Euclidean distance per
   second in normalised coordinates) refines the assignment:

   - ``velocity >= VEL_HIGH`` while OPEN → *Reach* (A)  or *Move* (M for
     CONTROLLED)
   - ``FIST || PINCH`` while velocity low  → *Grasp* (G)
   - ``OPEN`` while velocity low at expected Place position → *Place* (P)

4. **Output** — a list of ``DetectedAction`` dataclasses, each carrying
   ``start_time``, ``end_time``, ``verb``, ``seq_type``, raw TMU, and a
   confidence score derived from the detection frame-hit-rate.

Graceful degradation
--------------------
If MediaPipe or OpenCV are not installed (unit-test environments), the module
falls back to a lightweight *synthetic* signal identical in structure to the
``TimelineSegmenter._heuristic_segment()`` used in Phase 5.  The fallback is
activated automatically and is **never** used in production containers where
``mediapipe`` and ``opencv-python-headless`` are installed.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# MOST constants (shared with vision_service for TMU conversion)
# ---------------------------------------------------------------------------
_MOST_INDICES: tuple[int, ...] = (0, 1, 3, 6, 10, 16, 24, 32)
_TMU_FACTOR: float = 0.036
_CYCLE_STEPS: tuple[str, ...] = ("Reach", "Grasp", "Move", "Place")
_CYCLE_SEQ_TYPES: tuple[str, ...] = ("GENERAL", "GENERAL", "CONTROLLED", "GENERAL")

# ---------------------------------------------------------------------------
# MediaPipe & CV thresholds
# ---------------------------------------------------------------------------
_WIN_SECONDS: float = 0.5         # sliding-window duration (seconds)
_WIN_STEP: float = 0.25           # step between consecutive windows (seconds)
_FIST_THRESHOLD: float = 0.07     # fist_score <= this → FIST
_OPEN_THRESHOLD: float = 0.13     # fist_score >= this → OPEN
_PINCH_THRESHOLD: float = 0.05    # pinch_dist < this  → PINCH
_VEL_HIGH: float = 0.30           # normalised-coord velocity/s → active motion
_MIN_ACTION_DURATION: float = 0.20  # discard detections shorter than this

# MediaPipe landmark indices
_THUMB_TIP: int = 4
_INDEX_TIP: int = 8
_FINGERTIP_IDS: tuple[int, ...] = (4, 8, 12, 16, 20)
_PALM_BASE: int = 0


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------

@dataclass
class DetectedAction:
    action_id: str
    verb: str                   # "Reach" | "Grasp" | "Move" | "Place"
    seq_type: str               # "GENERAL" | "CONTROLLED"
    start_time: float           # seconds from video start
    end_time: float             # seconds from video start
    a_index: int                # MOST A parameter
    g_index: int                # MOST G parameter (0 for non-G steps)
    p_index: int                # MOST P parameter (0 for non-P steps)
    m_index: int                # MOST M parameter (0 for non-CM steps)
    tmu: int
    hand: str = "Right Hand"
    confidence: float = 1.0
    object_category: str | None = None
    component: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(self.end_time - self.start_time, 0.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _snap_to_most_index(raw: float) -> int:
    for idx in reversed(_MOST_INDICES):
        if raw >= idx:
            return idx
    return 0


def _duration_to_a_index(duration_seconds: float) -> int:
    return _snap_to_most_index(duration_seconds / _TMU_FACTOR)


def _euclidean(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


# ---------------------------------------------------------------------------
# DeepVisionAnalyzer
# ---------------------------------------------------------------------------

class DeepVisionAnalyzer:
    """MediaPipe-backed frame-by-frame hand tracker.

    Parameters
    ----------
    max_num_hands:
        Maximum number of hands MediaPipe will track simultaneously.
        Default 2 so both hands of an assembly operator are captured; the
        dominant (highest-confidence) hand is used for state classification.
    min_detection_confidence:
        Minimum confidence for initial hand detection (0.0 – 1.0).
    min_tracking_confidence:
        Minimum confidence to continue tracking an already-detected hand.
    """

    def __init__(
        self,
        max_num_hands: int = 2,
        min_detection_confidence: float = 0.6,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self._max_num_hands = max_num_hands
        self._min_det = min_detection_confidence
        self._min_trk = min_tracking_confidence

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        video_path: Path | str,
        context_objects: list[dict[str, Any]] | None = None,
    ) -> list[DetectedAction]:
        """Analyse *video_path* and return a list of detected ``DetectedAction``
        objects, ordered by ``start_time``.

        Falls back to synthetic signal when MediaPipe / OpenCV are unavailable.
        """
        video_path = Path(video_path)
        try:
            return self._analyze_mediapipe(video_path, context_objects or [])
        except ImportError:
            return self._analyze_synthetic(video_path, context_objects or [])

    # ------------------------------------------------------------------
    # MediaPipe path
    # ------------------------------------------------------------------

    def _analyze_mediapipe(
        self,
        video_path: Path,
        context_objects: list[dict[str, Any]],
    ) -> list[DetectedAction]:
        import cv2  # type: ignore[import]
        import mediapipe as mp  # type: ignore[import]

        mp_hands = mp.solutions.hands

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise OSError(f"Cannot open video: {video_path}")

        fps: float = cap.get(cv2.CAP_PROP_FPS) or 25.0
        # Guard against degenerate FPS values from corrupted containers
        fps = max(fps, 1.0)

        # Per-frame records: (timestamp, centroid_x, centroid_y, fist_score, pinch_dist, detected)
        frame_records: list[tuple[float, float, float, float, float, bool]] = []

        with mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self._max_num_hands,
            min_detection_confidence=self._min_det,
            min_tracking_confidence=self._min_trk,
        ) as hands:
            frame_idx = 0
            try:
                while True:
                    ok, bgr_frame = cap.read()
                    if not ok:
                        break
                    timestamp = frame_idx / fps
                    rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
                    result = hands.process(rgb)

                    if result.multi_hand_landmarks:
                        # Pick the hand with the highest detection score
                        if result.multi_handedness:
                            scores = [h.classification[0].score for h in result.multi_handedness]
                            best_idx = max(range(len(scores)), key=lambda i: scores[i])
                        else:
                            best_idx = 0
                        lm = result.multi_hand_landmarks[best_idx].landmark

                        xs = [p.x for p in lm]
                        ys = [p.y for p in lm]
                        cx = sum(xs) / len(xs)
                        cy = sum(ys) / len(ys)

                        thumb_tip = (lm[_THUMB_TIP].x, lm[_THUMB_TIP].y)
                        index_tip = (lm[_INDEX_TIP].x, lm[_INDEX_TIP].y)
                        pinch_dist = _euclidean(thumb_tip, index_tip)

                        palm = (lm[_PALM_BASE].x, lm[_PALM_BASE].y)
                        fist_score = sum(
                            _euclidean((lm[i].x, lm[i].y), palm) for i in _FINGERTIP_IDS
                        ) / len(_FINGERTIP_IDS)

                        frame_records.append((timestamp, cx, cy, fist_score, pinch_dist, True))
                    else:
                        frame_records.append((timestamp, 0.5, 0.5, 0.0, 1.0, False))

                    frame_idx += 1
            finally:
                cap.release()

        if not frame_records:
            return []

        return self._records_to_actions(frame_records, fps, context_objects)

    # ------------------------------------------------------------------
    # Sliding-window state machine
    # ------------------------------------------------------------------

    def _records_to_actions(
        self,
        records: list[tuple[float, float, float, float, float, bool]],
        fps: float,
        context_objects: list[dict[str, Any]],
    ) -> list[DetectedAction]:
        if not records:
            return []

        total_duration = records[-1][0]
        windows: list[tuple[float, float, str, float, int]] = []
        # (start, end, hand_state, velocity, detected_frame_count)

        t = 0.0
        while t < total_duration:
            win_end = min(t + _WIN_SECONDS, total_duration)
            window_recs = [r for r in records if t <= r[0] < win_end]

            if not window_recs:
                t += _WIN_STEP
                continue

            detected = [r for r in window_recs if r[5]]
            hit_rate = len(detected) / len(window_recs) if window_recs else 0.0

            if hit_rate < 0.25 or not detected:
                # Predominantly IDLE window
                windows.append((t, win_end, "IDLE", 0.0, 0))
                t += _WIN_STEP
                continue

            # Aggregate state from detected frames
            mean_fist = sum(r[3] for r in detected) / len(detected)
            mean_pinch = sum(r[4] for r in detected) / len(detected)

            # Centroid velocity: Euclidean displacement between first and last
            # detected frame divided by elapsed time
            if len(detected) >= 2:
                p0 = (detected[0][1], detected[0][2])
                p1 = (detected[-1][1], detected[-1][2])
                elapsed = max(detected[-1][0] - detected[0][0], 1 / fps)
                velocity = _euclidean(p0, p1) / elapsed
            else:
                velocity = 0.0

            if mean_pinch < _PINCH_THRESHOLD:
                state = "PINCH"
            elif mean_fist <= _FIST_THRESHOLD:
                state = "FIST"
            elif mean_fist >= _OPEN_THRESHOLD:
                state = "OPEN"
            else:
                state = "TRANSITION"

            windows.append((t, win_end, state, velocity, len(detected)))
            t += _WIN_STEP

        # Map windows to MOST verbs using cyclic assignment modulated by state
        actions: list[DetectedAction] = []
        cycle_pos = 0
        obj_pool = context_objects or []

        # Merge consecutive non-IDLE windows into action spans
        i = 0
        while i < len(windows):
            win_start, win_end, state, velocity, det_count = windows[i]

            if state == "IDLE":
                i += 1
                continue

            # Extend span while consecutive windows share a compatible state
            span_end = win_end
            span_states: list[str] = [state]
            span_velocities: list[float] = [velocity]
            span_det_counts: list[int] = [det_count]

            j = i + 1
            while j < len(windows):
                nw_start, nw_end, nw_state, nw_vel, nw_det = windows[j]
                if nw_state == "IDLE":
                    break
                # Merge if the gap is small (≤ 1 window step) or state is same
                gap = nw_start - span_end
                if gap > _WIN_STEP * 2:
                    break
                span_end = nw_end
                span_states.append(nw_state)
                span_velocities.append(nw_vel)
                span_det_counts.append(nw_det)
                j += 1

            duration = span_end - win_start
            if duration < _MIN_ACTION_DURATION:
                i = j
                continue

            dominant_state = max(set(span_states), key=span_states.count)
            mean_vel = sum(span_velocities) / len(span_velocities)
            total_det = sum(span_det_counts)
            total_frames = max(len(span_states), 1)
            confidence = min(1.0, total_det / (total_frames * (fps * _WIN_SECONDS)))

            # Assign verb using cycle + state hints
            verb_idx = cycle_pos % len(_CYCLE_STEPS)
            verb = _CYCLE_STEPS[verb_idx]
            seq_type = _CYCLE_SEQ_TYPES[verb_idx]

            # Override verb based on biomechanical signature
            if dominant_state in ("FIST", "PINCH") and mean_vel < _VEL_HIGH:
                verb = "Grasp"
                seq_type = "GENERAL"
            elif dominant_state == "OPEN" and mean_vel < _VEL_HIGH:
                verb = "Place"
                seq_type = "GENERAL"
            elif mean_vel >= _VEL_HIGH and dominant_state == "OPEN":
                # High-speed open hand: Reach (GENERAL) or Move (CONTROLLED)
                if seq_type == "CONTROLLED":
                    verb = "Move"
                else:
                    verb = "Reach"

            a_idx = _duration_to_a_index(duration)
            g_idx = 0
            p_idx = 0
            m_idx = 0

            if verb == "Grasp":
                g_idx = 3 if duration >= 0.5 else 1
                tmu = a_idx + g_idx + _snap_to_most_index(a_idx * 0.5)
            elif verb == "Place":
                p_idx = 3 if duration >= 0.5 else 1
                tmu = a_idx + p_idx + _snap_to_most_index(a_idx * 0.5)
            elif verb == "Move":
                m_idx = _snap_to_most_index(duration / _TMU_FACTOR * 0.6)
                tmu = a_idx + m_idx + a_idx
            else:
                # Reach
                tmu = a_idx + 0 + 0 + a_idx + 0 + 0 + _snap_to_most_index(a_idx * 0.3)

            tmu = max(tmu, 1)

            obj_entry = obj_pool[len(actions) % len(obj_pool)] if obj_pool else None
            action = DetectedAction(
                action_id=f"mp-{uuid.uuid4().hex[:8]}",
                verb=verb,
                seq_type=seq_type,
                start_time=round(win_start, 3),
                end_time=round(span_end, 3),
                a_index=a_idx,
                g_index=g_idx,
                p_index=p_idx,
                m_index=m_idx,
                tmu=tmu,
                confidence=round(min(1.0, max(0.1, confidence)), 3),
                object_category=(obj_entry or {}).get("category"),
                component=(obj_entry or {}).get("name_en") or (obj_entry or {}).get("name_cn"),
                metadata={
                    "dominant_state": dominant_state,
                    "mean_velocity": round(mean_vel, 4),
                    "engine": "mediapipe",
                },
            )
            actions.append(action)
            cycle_pos += 1
            i = j

        return actions

    # ------------------------------------------------------------------
    # Synthetic fallback (no MediaPipe / OpenCV)
    # ------------------------------------------------------------------

    def _analyze_synthetic(
        self,
        video_path: Path,
        context_objects: list[dict[str, Any]],
    ) -> list[DetectedAction]:
        """Deterministic synthetic pipeline used in test environments.

        Produces the same Reach-Grasp-Move-Place cycle structure as the
        heuristic ``TimelineSegmenter`` so that downstream DB-write and
        precaution-rule tests are exercised without a real video file.

        The synthetic signal models a 4-phase assembly micro-cycle:
          Phase 0 (0–25%): Reach   — OPEN hand, high lateral velocity
          Phase 1 (25–50%): Grasp  — FIST, low velocity
          Phase 2 (50–75%): Move   — OPEN hand, high velocity
          Phase 3 (75–100%): Place — OPEN hand, low velocity, new position
        """
        duration = _probe_duration(video_path)

        resolution = 0.1  # 100 ms samples
        fps = 1.0 / resolution
        records: list[tuple[float, float, float, float, float, bool]] = []

        t = 0.0
        cycle_period = 3.0  # one full Reach-Grasp-Move-Place cycle = 3 s
        idle_threshold = 0.12

        # A simple energy envelope: sine with 3 s period, idle between cycles
        import math as _math

        while t <= duration:
            energy = 0.5 * (_math.sin(2 * _math.pi * t / cycle_period) + 1) * (
                0.6 + 0.4 * _math.sin(2 * _math.pi * t / 1.5 + 0.8)
            )
            energy = max(0.0, min(1.0, energy))
            detected = energy >= idle_threshold

            # Phase within cycle determines hand state and centroid motion
            cycle_phase = (t % cycle_period) / cycle_period

            if cycle_phase < 0.25:
                # Reach: OPEN hand moving laterally (high velocity simulated by
                # varying cx between 0.2 and 0.8 over time)
                sweep = _math.sin(2 * _math.pi * t / (cycle_period * 0.25))
                cx = 0.5 + 0.3 * sweep
                cy = 0.5
                fist_score = 0.20   # OPEN
                pinch_dist = 0.15
            elif cycle_phase < 0.50:
                # Grasp: FIST, hand stationary at target
                cx = 0.8
                cy = 0.5
                fist_score = 0.05   # FIST (< _FIST_THRESHOLD = 0.07)
                pinch_dist = 0.03   # PINCH
            elif cycle_phase < 0.75:
                # Move: OPEN hand sweeping back
                sweep = _math.sin(2 * _math.pi * t / (cycle_period * 0.25))
                cx = 0.8 - 0.3 * abs(sweep)
                cy = 0.5
                fist_score = 0.22   # OPEN
                pinch_dist = 0.15
            else:
                # Place: OPEN hand, stationary at destination
                cx = 0.2
                cy = 0.5
                fist_score = 0.20   # OPEN
                pinch_dist = 0.12

            records.append((round(t, 3), cx, cy, fist_score, pinch_dist, detected))
            t += resolution

        actions = self._records_to_actions(records, fps, context_objects)
        for a in actions:
            a.metadata["engine"] = "synthetic"
        return actions


# ---------------------------------------------------------------------------
# Tiny duration probe helper (no cv2 dependency)
# ---------------------------------------------------------------------------

def _probe_duration(path: Path) -> float:
    """Extract video duration in seconds from an MP4 ``mvhd`` box.

    Falls back to 8.0 s if the file doesn't exist or isn't a valid MP4.
    """
    import struct

    if not path.exists():
        return 8.0
    try:
        with path.open("rb") as fh:
            data = fh.read(min(1_000_000, path.stat().st_size))
        idx = data.find(b"mvhd")
        if idx == -1:
            return 8.0
        offset = idx + 4
        version = data[offset]
        if version == 1:
            time_scale = struct.unpack_from(">I", data, offset + 20)[0]
            duration_units = struct.unpack_from(">Q", data, offset + 24)[0]
        else:
            time_scale = struct.unpack_from(">I", data, offset + 12)[0]
            duration_units = struct.unpack_from(">I", data, offset + 16)[0]
        if time_scale > 0:
            return round(duration_units / time_scale, 3)
    except Exception:  # noqa: BLE001
        pass
    return 8.0
