"""Vision Service — Phase 5: Heuristic Motion-to-MOST Analysis Engine.

Architecture
------------

    VideoUpload record
         │
         ▼
    TimelineSegmenter ────► [Segment, Segment, ...]   (active + idle spans)
         │
         ▼
    ActionClassifier ──────► [ActionCandidate, ...]   (MOST verb + TMU index)
         │
         ▼
    VisionService ─────────► [SopAction dict, ...]    (precaution-enriched)

Motion Density → TMU Mapping
------------------------------
Each active segment carries a mean energy `E ∈ [0.0, 1.0]` and a
``motion_bias`` that classifies the dominant direction of movement:

  "central"   → High energy at screen centre  → Grasp (G) or Place (P)
  "lateral"   → Large spatial spread / x-axis → Reach (A) or Move (M)

The A-index (reach distance proxy) is derived from segment duration:

  d_seconds × (1 / TMU_FACTOR) = raw_tmu_units
  snap(raw_tmu_units) to nearest lower value in {0, 1, 3, 6, 10, 16, 24, 32}

A full sub-cycle is: Reach-A → Grasp-G → Move-A → Place-P.
Verb assignment rotates through this 4-step cycle so every set of four
active segments produces one ergonomically-coherent assembly micro-cycle.

Engines
-------
*  "opencv"   — Real frame-differencing via cv2.VideoCapture (optional dep)
*  "heuristic" — Deterministic synthetic signal (no extra deps; test-safe)
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# MOST constants
# ---------------------------------------------------------------------------

_MOST_INDICES: tuple[int, ...] = (0, 1, 3, 6, 10, 16, 24, 32)
_TMU_FACTOR: float = 0.036          # seconds per TMU (1 TMU = 0.036 s)
_CYCLE_STEPS: tuple[str, ...] = ("Reach", "Grasp", "Move", "Place")
_CYCLE_SEQ_TYPES: tuple[str, ...] = ("GENERAL", "GENERAL", "CONTROLLED", "GENERAL")
_CYCLE_HANDS: tuple[str, ...] = ("Right Hand", "Right Hand", "Right Hand", "Right Hand")
_IDLE_THRESHOLD: float = 0.12       # energy below this → idle frame
_MIN_SEGMENT_GAP: float = 0.30      # merge adjacent segments closer than this
_MIN_SEGMENT_DURATION: float = 0.20 # discard micro-segments shorter than this
_DEFAULT_CYCLE_DURATION: float = 4.0  # fallback total sub-cycle time

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    start: float
    end: float
    mean_energy: float = 0.0
    motion_bias: str = "central"   # "central" | "lateral"
    is_active: bool = True

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 0.0)


@dataclass
class ActionCandidate:
    """Raw classified action before precaution enrichment."""

    segment: Segment
    verb: str              # "Reach" | "Grasp" | "Move" | "Place"
    seq_type: str          # "GENERAL" | "CONTROLLED"
    a_index: int           # MOST A-parameter value
    g_index: int           # G (or P) parameter value  — 0 for A/M steps
    p_index: int           # P parameter value          — 0 for G/A steps
    m_index: int           # M parameter value          — 0 for non-controlled
    tmu: int
    hand: str
    confidence: float
    object_category: str | None = None
    component: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snap_to_most_index(raw: float) -> int:
    """Snap *raw* (a continuous value in MOST-index units) to the nearest lower
    discrete MOST index from the standard set {0,1,3,6,10,16,24,32}.
    """
    for idx in reversed(_MOST_INDICES):
        if raw >= idx:
            return idx
    return 0


def _duration_to_a_index(duration_seconds: float) -> int:
    """Convert an observed segment duration to the equivalent MOST A-index."""
    raw = duration_seconds / _TMU_FACTOR
    return _snap_to_most_index(raw)


def _fmt_ts(seconds: float) -> str:
    """Format seconds as MM:SS for human-readable action descriptions."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# TimelineSegmenter
# ---------------------------------------------------------------------------


class TimelineSegmenter:
    """Divides a video's timeline into active (motion-present) and idle spans.

    Two modes:
    - **opencv**: Frame-differencing using cv2.VideoCapture.  Used when
      ``opencv-python`` is installed and the file path is provided.
    - **heuristic**: Deterministic synthetic energy signal built from the
      video duration alone.  Produces a reproducible sequence for testing
      and environments without OpenCV.
    """

    def __init__(
        self,
        idle_threshold: float = _IDLE_THRESHOLD,
        min_gap: float = _MIN_SEGMENT_GAP,
        min_duration: float = _MIN_SEGMENT_DURATION,
    ) -> None:
        self._idle_threshold = idle_threshold
        self._min_gap = min_gap
        self._min_duration = min_duration

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def segment(
        self,
        duration_seconds: float,
        file_path: Path | None = None,
        fps: float | None = None,
    ) -> tuple[list[Segment], str]:
        """Return ``(segments, engine_name)`` where ``segments`` is a
        time-ordered list of both active and idle spans.
        """
        if duration_seconds <= 0:
            return [], "heuristic"

        if file_path is not None:
            try:
                segs = self._opencv_segment(file_path, fps or 30.0)
                if segs:
                    return segs, "opencv"
            except Exception:  # noqa: BLE001
                pass

        return self._heuristic_segment(duration_seconds), "heuristic"

    # ------------------------------------------------------------------
    # OpenCV-based segmenter
    # ------------------------------------------------------------------

    def _opencv_segment(self, file_path: Path, fps: float) -> list[Segment]:
        import cv2  # type: ignore[import]

        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            return []

        try:
            frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
            frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
            total_area = frame_w * frame_h

            energies: list[tuple[float, float, str]] = []
            prev_gray = None
            frame_idx = 0

            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                t = frame_idx / fps
                if prev_gray is not None:
                    diff = cv2.absdiff(gray, prev_gray)
                    energy = float(diff.sum()) / (total_area * 255.0)
                    # Lateral vs central: compare left+right energy vs centre strip
                    cx = frame_w // 4
                    centre_energy = float(diff[:, cx : frame_w - cx].sum()) / (
                        max(diff[:, cx : frame_w - cx].size, 1) * 255.0
                    )
                    edge_energy = float(
                        diff[:, :cx].sum() + diff[:, frame_w - cx :].sum()
                    ) / (max(diff[:, :cx].size + diff[:, frame_w - cx :].size, 1) * 255.0)
                    bias = "lateral" if edge_energy > centre_energy else "central"
                    energies.append((t, energy, bias))
                prev_gray = gray
                frame_idx += 1
        finally:
            cap.release()

        if not energies:
            return []

        return self._energies_to_segments(energies)

    # ------------------------------------------------------------------
    # Heuristic (synthetic) segmenter
    # ------------------------------------------------------------------

    def _heuristic_segment(self, duration_seconds: float) -> list[Segment]:
        """Build a synthetic energy signal for *duration_seconds*.

        The signal is seeded from the duration to be deterministic:
          E(t) = 0.5*(sin(2π·t/T₁)+1)·(0.6+0.4·sin(2π·t/T₂+φ))
        where T₁ = 3.0 s (operator cycle), T₂ = 1.5 s (micro-motion),
        φ = 0.8 rad.  This approximates the rhythmic energy pattern of
        a workstation assembly operator.
        """
        resolution = 0.1         # sample every 100 ms
        t1 = 3.0
        t2 = 1.5
        phi = 0.8

        energies: list[tuple[float, float, str]] = []
        t = 0.0
        while t <= duration_seconds:
            e = 0.5 * (math.sin(2 * math.pi * t / t1) + 1) * (
                0.6 + 0.4 * math.sin(2 * math.pi * t / t2 + phi)
            )
            # Simple lateral bias: peaks at quarter and three-quarter cycle →
            # likely reach/return; valleys at centre → grasp/place.
            phase = (t % t1) / t1
            bias = "lateral" if 0.15 < phase < 0.45 or 0.65 < phase < 0.85 else "central"
            energies.append((round(t, 3), max(0.0, min(1.0, e)), bias))
            t += resolution

        return self._energies_to_segments(energies)

    # ------------------------------------------------------------------
    # Shared post-processing: raw energy samples → Segment objects
    # ------------------------------------------------------------------

    def _energies_to_segments(
        self, energies: list[tuple[float, float, str]]
    ) -> list[Segment]:
        """Convert a time-ordered ``(t, energy, bias)`` list to ``Segment`` objects."""
        if not energies:
            return []

        raw_segs: list[Segment] = []
        in_active = energies[0][1] >= self._idle_threshold
        seg_start = energies[0][0]
        seg_energies: list[float] = []
        seg_biases: list[str] = []

        def _close_segment(end_t: float, is_active: bool) -> None:
            dur = end_t - seg_start
            if dur < self._min_duration:
                return
            mean_e = sum(seg_energies) / len(seg_energies) if seg_energies else 0.0
            dominant_bias = (
                "lateral"
                if seg_biases.count("lateral") > len(seg_biases) / 2
                else "central"
            )
            raw_segs.append(
                Segment(
                    start=round(seg_start, 3),
                    end=round(end_t, 3),
                    mean_energy=round(mean_e, 4),
                    motion_bias=dominant_bias,
                    is_active=is_active,
                )
            )

        for t, energy, bias in energies:
            active = energy >= self._idle_threshold
            if active != in_active:
                _close_segment(t, in_active)
                seg_start = t
                seg_energies = []
                seg_biases = []
                in_active = active
            seg_energies.append(energy)
            seg_biases.append(bias)

        lasting = energies[-1][0]
        _close_segment(lasting, in_active)

        # Merge active segments whose gap is < min_gap (brief pauses within motion)
        merged: list[Segment] = []
        for seg in raw_segs:
            if (
                seg.is_active
                and merged
                and merged[-1].is_active
                and seg.start - merged[-1].end < self._min_gap
            ):
                prev = merged[-1]
                # Extend the previous segment and blend mean_energy
                total = prev.duration + seg.duration
                blended_e = (prev.mean_energy * prev.duration + seg.mean_energy * seg.duration) / total if total > 0 else prev.mean_energy
                merged[-1] = Segment(
                    start=prev.start,
                    end=seg.end,
                    mean_energy=round(blended_e, 4),
                    motion_bias=prev.motion_bias,
                    is_active=True,
                )
            else:
                merged.append(seg)

        return merged


# ---------------------------------------------------------------------------
# ActionClassifier
# ---------------------------------------------------------------------------


class ActionClassifier:
    """Maps a sequence of active ``Segment`` objects to ``ActionCandidate`` objects.

    Verb assignment cycles through: Reach → Grasp → Move → Place.
    This mirrors the natural A B G A B P sequence of a General Move.
    """

    def classify(
        self,
        segments: list[Segment],
        context_objects: list[dict[str, Any]] | None = None,
    ) -> list[ActionCandidate]:
        """Return one ``ActionCandidate`` per active segment in *segments*."""
        active = [s for s in segments if s.is_active]
        candidates: list[ActionCandidate] = []
        obj_pool = context_objects or []

        for cycle_pos, seg in enumerate(active):
            verb_idx = cycle_pos % len(_CYCLE_STEPS)
            verb = _CYCLE_STEPS[verb_idx]
            seq_type = _CYCLE_SEQ_TYPES[verb_idx]

            # Energy → confidence (simple linear map 0.12→0.5 .. 1.0→1.0)
            confidence = min(1.0, max(0.5, (seg.mean_energy - self._idle_threshold) / (1.0 - self._idle_threshold) + 0.5))

            a_idx = _duration_to_a_index(seg.duration)
            g_idx = 0
            p_idx = 0
            m_idx = 0

            if verb == "Grasp":
                g_idx = 3 if seg.duration >= 0.5 else 1
                a_idx_return = _snap_to_most_index(a_idx * 0.5)
                tmu = a_idx + g_idx + a_idx_return
            elif verb == "Place":
                p_idx = 3 if seg.duration >= 0.5 else 1
                a_idx_return = _snap_to_most_index(a_idx * 0.5)
                tmu = a_idx + p_idx + a_idx_return
            elif verb == "Move" and seq_type == "CONTROLLED":
                m_idx = _snap_to_most_index(seg.duration / _TMU_FACTOR * 0.6)
                tmu = a_idx + m_idx + a_idx
            else:
                # Reach (GENERAL) — A B0 G0 A B0 P0 A3
                tmu = a_idx + 0 + 0 + a_idx + 0 + 0 + _snap_to_most_index(a_idx * 0.3)

            tmu = max(tmu, 1)

            # Pick a context object if available (round-robin)
            obj_entry = obj_pool[cycle_pos % len(obj_pool)] if obj_pool else None
            obj_category = (obj_entry or {}).get("category")
            component = (obj_entry or {}).get("name_en") or (obj_entry or {}).get("name_cn")

            candidates.append(
                ActionCandidate(
                    segment=seg,
                    verb=verb,
                    seq_type=seq_type,
                    a_index=a_idx,
                    g_index=g_idx,
                    p_index=p_idx,
                    m_index=m_idx,
                    tmu=tmu,
                    hand=_CYCLE_HANDS[verb_idx],
                    confidence=round(confidence, 3),
                    object_category=obj_category,
                    component=component,
                )
            )

        return candidates

    @property
    def _idle_threshold(self) -> float:
        return _IDLE_THRESHOLD


# ---------------------------------------------------------------------------
# VisionService  (the public-facing engine)
# ---------------------------------------------------------------------------


class VisionService:
    """Orchestrates timeline segmentation, action classification, and
    precaution-rule enrichment to produce a list of ``SopAction`` dicts
    from an uploaded video.

    The service is **stateless** — it receives all required data as arguments
    so it can be constructed once and used across concurrent requests.

    Usage
    -----
    ::

        svc = VisionService()
        result = await svc.analyze_video(
            upload_record=upload_dict,
            store=store_instance,
            file_path=Path("/data/videos/abc123.mp4"),
        )
    """

    def __init__(
        self,
        segmenter: TimelineSegmenter | None = None,
        classifier: ActionClassifier | None = None,
    ) -> None:
        self._segmenter = segmenter or TimelineSegmenter()
        self._classifier = classifier or ActionClassifier()

    async def analyze_video(
        self,
        upload_record: dict[str, Any],
        store: Any,                          # PostgresStore — typed as Any to avoid circular import
        file_path: Path | None = None,
    ) -> dict[str, Any]:
        """Analyse *upload_record* and return a result dict suitable for the
        ``VisionAnalysisResponse`` schema.

        Steps
        -----
        1. Extract duration from the upload record.
        2. Run `TimelineSegmenter` (OpenCV or heuristic).
        3. Fetch live master data (objects, precaution rules) from `store`.
        4. Run `ActionClassifier` with the object context.
        5. Apply `_apply_precaution_rules` from `most_workspace_service`.
        6. Build and return action dicts (without writing to DB — the route
           owns the transaction).
        """
        from ddm_v2.services.most_workspace_service import _apply_precaution_rules

        duration: float = float(upload_record.get("duration_seconds") or 0.0)
        fps: float | None = upload_record.get("fps")
        sop_version_id: str = upload_record["sop_version_id"]
        project_id: str = upload_record["project_id"]

        # 1. Segment the timeline
        segments, engine_name = self._segmenter.segment(
            duration_seconds=duration,
            file_path=file_path,
            fps=fps,
        )

        active_segs = [s for s in segments if s.is_active]
        idle_segs = [s for s in segments if not s.is_active]

        if not active_segs:
            return {
                "upload_id": upload_record["id"],
                "sop_version_id": sop_version_id,
                "detected_actions": [],
                "total_active_segments": 0,
                "total_idle_segments": len(idle_segs),
                "analysis_engine": engine_name,
                "appended_action_count": 0,
                "actions_for_db": [],
                "patches_for_db": [],
            }

        # 2. Fetch live master data
        object_library: list[dict[str, Any]] = await store.list_collection("object_library")
        precaution_rules: list[dict[str, Any]] = await store.list_collection("precaution_rules")

        # Filter objects that belong to this project (if project-tagged),
        # otherwise use all available objects as hints.
        context_objects = object_library or []

        # 3. Classify segments → ActionCandidates
        candidates = self._classifier.classify(
            segments=active_segs,
            context_objects=context_objects,
        )

        # 4. Build SopAction dicts + apply precaution rules
        detected_actions: list[dict[str, Any]] = []
        actions_for_db: list[dict[str, Any]] = []
        patches_for_db: list[dict[str, Any]] = []

        from ddm_v2.settings import get_settings
        tmu_factor = get_settings().tmu_factor

        for cand in candidates:
            action_id = f"ai-{uuid.uuid4().hex[:8]}"
            seg = cand.segment

            ts_fmt = _fmt_ts(seg.start)
            description = (
                f"[AI Detected] {cand.verb} "
                f"{cand.component or cand.object_category or 'Object'} "
                f"(Start: {ts_fmt})"
            )

            if cand.seq_type == "GENERAL":
                params = {
                    "A1": cand.a_index,
                    "B1": 0,
                    "G": cand.g_index,
                    "A2": cand.a_index,
                    "B2": 0,
                    "P": cand.p_index,
                    "A3": _snap_to_most_index(cand.a_index * 0.3),
                }
            else:
                params = {
                    "A1": cand.a_index,
                    "B1": 0,
                    "G": cand.g_index,
                    "M": cand.m_index,
                    "X": 0,
                    "I": 0,
                    "A3": _snap_to_most_index(cand.a_index * 0.3),
                }

            action: dict[str, Any] = {
                "id": action_id,
                "seq_type": cand.seq_type,
                "description": description,
                "tmu": cand.tmu,
                "seconds": round(cand.tmu * tmu_factor, 3),
                "params": params,
                "primary_action": cand.verb,
                "hand": cand.hand,
                "object_category": cand.object_category,
                "component": cand.component,
                "glove_type": None,
                "tool": None,
                "is_ctq": False,
                "frequency": 1,
                "precautions": [],
                "level_tag": None,
                "is_simo": False,
                "simo_group_id": None,
                "required_skill": None,
                "equipment_params": None,
                "station_id": None,
                "image_url": None,
                "video_timestamp_start": seg.start,
                "video_timestamp_end": seg.end,
            }

            # Apply compliance rule engine (precaution rules, LCD, etc.)
            action["precautions"] = _apply_precaution_rules(action, precaution_rules)

            detected_action = {
                "action_id": action_id,
                "description": description,
                "seq_type": cand.seq_type,
                "tmu": cand.tmu,
                "seconds": round(cand.tmu * tmu_factor, 3),
                "primary_action": cand.verb,
                "hand": cand.hand,
                "object_category": cand.object_category,
                "glove_type": action["glove_type"],
                "component": cand.component,
                "precautions": action["precautions"],
                "video_timestamp_start": seg.start,
                "video_timestamp_end": seg.end,
                "confidence": cand.confidence,
            }

            detected_actions.append(detected_action)
            actions_for_db.append(action)
            patches_for_db.append({
                "action_id": action_id,
                "video_timestamp_start": seg.start,
                "video_timestamp_end": seg.end,
            })

        return {
            "upload_id": upload_record["id"],
            "sop_version_id": sop_version_id,
            "detected_actions": detected_actions,
            "total_active_segments": len(active_segs),
            "total_idle_segments": len(idle_segs),
            "analysis_engine": engine_name,
            "appended_action_count": len(actions_for_db),
            "actions_for_db": actions_for_db,
            "patches_for_db": patches_for_db,
        }


# ---------------------------------------------------------------------------
# Celery task — Phase 6: distributed deep learning vision pipeline
# ---------------------------------------------------------------------------

def _make_celery_task():  # pragma: no cover — imported lazily to avoid circular init
    """Register and return the ``analyze_video_task`` Celery task.

    This function is called at module-import time only when ``celery`` is
    installed and ``DDM_CELERY_BROKER_URL`` is configured.  Keeping the task
    definition in *this* module (rather than a separate tasks.py) ensures that
    the entire vision pipeline — segmenter, classifier, ML tracker, rule engine
    — is co-located and easy to reason about.

    PostgreSQL connection strategy (see also celery_app.py docstring)
    ------------------------------------------------------------------
    Each ``asyncio.run()`` invocation creates a fresh event loop.  We
    initialise a new ``AsyncEngine`` inside that loop with ``pool_size=2`` so
    that asyncpg's internal transport is always owned by the loop that uses it.
    The engine is explicitly disposed after the task completes, releasing all
    connections back to PostgreSQL.
    """
    import asyncio
    import logging
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from ddm_v2.core.celery_app import celery_app
    from ddm_v2.ml.vision_tracker import DeepVisionAnalyzer
    from ddm_v2.repositories.postgres_store import PostgresStore
    from ddm_v2.schemas import VideoUploadStatus
    from ddm_v2.settings import get_settings

    logger = logging.getLogger("ddm_v2.celery.vision")

    @celery_app.task(
        name="analyze_video_task",
        bind=True,
        max_retries=2,
        default_retry_delay=30,
    )
    def analyze_video_task(self, upload_id: str) -> dict:  # type: ignore[misc]
        """Celery task: run the MediaPipe deep learning pipeline on *upload_id*.

        Workflow
        --------
        1.  Open a fresh async engine + session (per-task pool, pool_size=2).
        2.  Load the ``VideoUpload`` record; verify it is in ``processing`` state.
        3.  Resolve the on-disk video file path.
        4.  Run ``DeepVisionAnalyzer.analyze()`` (MediaPipe → synthetic fallback).
        5.  Convert ``DetectedAction`` objects to ``SopAction`` dicts and apply
            ``_apply_precaution_rules()``.
        6.  Append actions to the ``SopVersion`` and persist to PostgreSQL.
        7.  Mark the upload as ``analyzed`` (or ``failed`` on unhandled error).
        8.  Dispose the engine and return a summary dict.
        """
        settings = get_settings()
        db_url = settings.database_url

        async def _run() -> dict:
            engine = create_async_engine(
                db_url,
                echo=False,
                future=True,
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=0,
            )
            factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
            try:
                async with factory() as session:
                    store = PostgresStore(session)
                    return await _execute_pipeline(upload_id, store, settings)
            finally:
                await engine.dispose()

        try:
            return asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            logger.exception("analyze_video_task failed for upload_id=%s", upload_id)
            # Best-effort status update to 'failed' using a second asyncio.run()
            async def _mark_failed() -> None:
                engine = create_async_engine(db_url, echo=False, future=True,
                                             pool_size=1, max_overflow=0)
                factory = async_sessionmaker(bind=engine, class_=AsyncSession,
                                             expire_on_commit=False, autoflush=False)
                try:
                    async with factory() as session:
                        store = PostgresStore(session)
                        await store.update_video_upload_status(
                            upload_id, VideoUploadStatus.failed.value
                        )
                        await session.commit()
                finally:
                    await engine.dispose()

            try:
                asyncio.run(_mark_failed())
            except Exception:  # noqa: BLE001
                pass
            raise self.retry(exc=exc)

    return analyze_video_task


async def _execute_pipeline(
    upload_id: str,
    store: Any,
    settings: Any,
) -> dict:
    """Async pipeline body executed inside the Celery task's ``asyncio.run()``.

    Separated into its own coroutine so it can also be called from tests that
    supply a mock async session.
    """
    from ddm_v2.ml.vision_tracker import DeepVisionAnalyzer, DetectedAction
    from ddm_v2.schemas import VideoUploadStatus

    # 1. Load upload record
    upload = await store.get_video_upload(upload_id)
    if upload is None:
        raise ValueError(f"VideoUpload '{upload_id}' not found in database.")

    # 2. Resolve video file path (path from DB, never from caller input)
    video_upload_dir = settings.video_upload_dir
    stored_fn: str | None = upload.get("stored_filename")
    file_path: Path | None = None
    if stored_fn:
        candidate = Path(video_upload_dir) / Path(stored_fn).name  # strip any dir traversal
        if candidate.exists():
            file_path = candidate

    # 3. Fetch master-data context
    object_library: list[dict] = await store.list_collection("object_library")
    precaution_rules: list[dict] = await store.list_collection("precaution_rules")
    context_objects = object_library or []

    # 4. Run DeepVisionAnalyzer (MediaPipe → synthetic fallback)
    analyzer = DeepVisionAnalyzer()
    if file_path is not None:
        raw_actions = analyzer.analyze(file_path, context_objects)
        engine_name = "mediapipe"
    else:
        # No file on disk: fall back to heuristic on the upload's duration
        from ddm_v2.services.vision_service import TimelineSegmenter, ActionClassifier

        segmenter = TimelineSegmenter()
        classifier = ActionClassifier()
        duration = float(upload.get("duration_seconds") or 0.0)
        fps = upload.get("fps")
        segments, engine_name = segmenter.segment(
            duration_seconds=duration, file_path=None, fps=fps
        )
        active_segs = [s for s in segments if s.is_active]
        candidates = classifier.classify(active_segs, context_objects)

        # Convert to DetectedAction objects for uniform downstream handling
        from ddm_v2.ml.vision_tracker import DetectedAction as DA

        raw_actions = [
            DA(
                action_id=f"h-{uuid.uuid4().hex[:8]}",
                verb=c.verb,
                seq_type=c.seq_type,
                start_time=c.segment.start,
                end_time=c.segment.end,
                a_index=c.a_index,
                g_index=c.g_index,
                p_index=c.p_index,
                m_index=c.m_index,
                tmu=c.tmu,
                confidence=c.confidence,
                object_category=c.object_category,
                component=c.component,
                metadata={"engine": engine_name},
            )
            for c in candidates
        ]

    # 5. Convert + apply precaution rules
    from ddm_v2.services.most_workspace_service import _apply_precaution_rules

    tmu_factor: float = settings.tmu_factor
    actions_for_db: list[dict] = []
    patches_for_db: list[dict] = []

    for da in raw_actions:
        action_id = da.action_id

        def _fmt_ts(s: float) -> str:
            m, sec = divmod(int(s), 60)
            return f"{m:02d}:{sec:02d}"

        description = (
            f"[AI Detected] {da.verb} "
            f"{da.component or da.object_category or 'Object'} "
            f"(Start: {_fmt_ts(da.start_time)})"
        )

        if da.seq_type == "GENERAL":
            params: dict = {
                "A1": da.a_index,
                "B1": 0,
                "G": da.g_index,
                "A2": da.a_index,
                "B2": 0,
                "P": da.p_index,
                "A3": 0,
            }
        else:
            params = {
                "A1": da.a_index,
                "B1": 0,
                "G": da.g_index,
                "M": da.m_index,
                "X": 0,
                "I": 0,
                "A3": 0,
            }

        action: dict = {
            "id": action_id,
            "seq_type": da.seq_type,
            "description": description,
            "tmu": da.tmu,
            "seconds": round(da.tmu * tmu_factor, 3),
            "params": params,
            "primary_action": da.verb,
            "hand": da.hand,
            "object_category": da.object_category,
            "component": da.component,
            "glove_type": None,
            "tool": None,
            "is_ctq": False,
            "frequency": 1,
            "precautions": [],
            "level_tag": None,
            "is_simo": False,
            "simo_group_id": None,
            "required_skill": None,
            "equipment_params": None,
            "station_id": None,
            "image_url": None,
            "video_timestamp_start": da.start_time,
            "video_timestamp_end": da.end_time,
        }
        action["precautions"] = _apply_precaution_rules(action, precaution_rules)
        actions_for_db.append(action)
        patches_for_db.append({
            "action_id": action_id,
            "video_timestamp_start": da.start_time,
            "video_timestamp_end": da.end_time,
        })

    # 6. Append actions to the SOP version
    sop_version_id: str = upload["sop_version_id"]
    sop_version = await store.find_by_id("sop_versions", sop_version_id)
    if sop_version is not None and actions_for_db:
        existing: list[dict] = list(sop_version.get("actions") or [])
        sop_version["actions"] = existing + actions_for_db
        await store.upsert_collection_item("sop_versions", sop_version)

    # 7. Bulk-update timestamp anchors on SOP actions
    if patches_for_db:
        await store.update_sop_action_timestamps(patches_for_db)

    # 8. Mark upload as analyzed
    await store.update_video_upload_status(upload_id, VideoUploadStatus.analyzed.value)
    await store._session.commit()  # explicit commit — no FastAPI request context here

    return {
        "upload_id": upload_id,
        "sop_version_id": sop_version_id,
        "appended_action_count": len(actions_for_db),
        "analysis_engine": engine_name,
    }


# Register the Celery task when celery is importable (production + integration),
# but silently skip in test environments that have no broker.
try:
    analyze_video_task = _make_celery_task()
except Exception:  # noqa: BLE001  — celery not installed or broker not configured
    analyze_video_task = None  # type: ignore[assignment]
