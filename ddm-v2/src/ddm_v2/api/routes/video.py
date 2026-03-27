"""Video Upload API Routes — Phase 5 Vision Engine.

Endpoints
---------
POST   /api/v1/video/upload/{sop_version_id}
    Multipart upload of a workstation video; returns ``VideoUploadOut``.

GET    /api/v1/video/uploads/{sop_version_id}
    List all uploads associated with a SOP version.

GET    /api/v1/video/{upload_id}
    Retrieve metadata for a single upload record.

GET    /api/v1/video/stream/{upload_id}
    Stream the raw video file (supports ``Range`` headers for scrubbing).

DELETE /api/v1/video/{upload_id}
    Delete the upload record and its on-disk file.

PATCH  /api/v1/video/timestamps
    Batch-update ``video_timestamp_start`` / ``video_timestamp_end`` on SOP
    actions (called by the Vision Engine after analysis).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.postgres_store import PostgresStore
from ddm_v2.schemas import (
    BulkTimestampUpdateRequest,
    UserRole,
    VideoUploadOut,
    VideoUploadStatus,
    VisionAnalysisResponse,
    VisionDetectedAction,
)
from ddm_v2.services.video_service import VideoService
from ddm_v2.services.vision_service import VisionService

# analyze_video_task is None when Celery is not configured (test / dev environments
# without a Redis broker).  The route falls back to synchronous execution in that case.
try:
    from ddm_v2.services.vision_service import analyze_video_task
except Exception:  # noqa: BLE001
    analyze_video_task = None  # type: ignore[assignment]

router = APIRouter(prefix="/api/v1/video", tags=["video"])

_vision_service = VisionService()  # singleton — stateless, safe to share

# ---------------------------------------------------------------------------
# Dependency: VideoService bound to the current app's upload directory
# ---------------------------------------------------------------------------


def _get_video_service(request: Request) -> VideoService:
    settings = request.app.state.settings
    return VideoService(settings.video_upload_dir)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/upload/{sop_version_id}",
    response_model=VideoUploadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a workstation video and attach it to a SOP version",
)
async def upload_video(
    sop_version_id: str,
    file: UploadFile,
    store: PostgresStore = Depends(get_store),
    current_user: dict = Depends(get_current_user),
    video_svc: VideoService = Depends(_get_video_service),
):
    # 1. Verify the SOP version exists (prevents orphan uploads)
    sop_version = await store.find_by_id("sop_versions", sop_version_id)
    if sop_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SOP version '{sop_version_id}' not found.",
        )

    # 2. Read file bytes and validate (format + size check before touching disk)
    file_bytes = await file.read()
    try:
        video_svc.validate_upload(
            content_type=file.content_type,
            original_filename=file.filename or "upload.bin",
            file_size=len(file_bytes),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # 3. Persist file + extract metadata
    record = await video_svc.save_and_record(
        file_data=file_bytes,
        original_filename=file.filename or "upload.bin",
        content_type=file.content_type,
        sop_version_id=sop_version_id,
        project_id=sop_version["project_id"],
        uploaded_by=current_user.get("id"),
    )

    # 4. Write DB record (session is committed automatically by get_session)
    saved = await store.create_video_upload(record)

    return VideoUploadOut(**saved)


@router.get(
    "/uploads/{sop_version_id}",
    response_model=list[VideoUploadOut],
    summary="List all video uploads for a SOP version",
)
async def list_uploads(
    sop_version_id: str,
    store: PostgresStore = Depends(get_store),
    _current_user: dict = Depends(get_current_user),
):
    rows = await store.list_video_uploads(sop_version_id)
    return [VideoUploadOut(**r) for r in rows]


@router.get(
    "/{upload_id}",
    response_model=VideoUploadOut,
    summary="Get metadata for a single video upload",
)
async def get_upload(
    upload_id: str,
    store: PostgresStore = Depends(get_store),
    _current_user: dict = Depends(get_current_user),
):
    row = await store.get_video_upload(upload_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found.")
    return VideoUploadOut(**row)


@router.get(
    "/stream/{upload_id}",
    summary="Stream the raw video file (supports Range requests for seeking)",
)
async def stream_video(
    upload_id: str,
    request: Request,
    store: PostgresStore = Depends(get_store),
    _current_user: dict = Depends(get_current_user),
    video_svc: VideoService = Depends(_get_video_service),
):
    row = await store.get_video_upload(upload_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found.")

    if row["status"] != VideoUploadStatus.ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video is not ready (status={row['status']}).",
        )

    # Resolve path using the stored_filename from DB — never from the URL —
    # to prevent path-traversal attacks.
    file_path: Path = video_svc.get_file_path(row["stored_filename"])
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Video file no longer exists on disk.",
        )

    media_type, _ = mimetypes.guess_type(row["original_filename"])
    media_type = media_type or "application/octet-stream"

    # Support HTTP Range requests so the browser's <video> element can seek
    # without re-downloading the entire file.
    range_header = request.headers.get("range")
    file_size = file_path.stat().st_size

    if range_header:
        try:
            range_val = range_header.replace("bytes=", "").strip()
            start_str, end_str = range_val.split("-")
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Invalid Range header.",
            )

        if start > end or end >= file_size:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail=f"Range {start}-{end} out of bounds for file size {file_size}.",
            )

        chunk_size = end - start + 1

        def _iter_range():
            with file_path.open("rb") as fh:
                fh.seek(start)
                remaining = chunk_size
                buf_size = 65536
                while remaining > 0:
                    data = fh.read(min(buf_size, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            _iter_range(),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=media_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            },
        )

    # Full file response
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=row["original_filename"],
        headers={"Accept-Ranges": "bytes"},
    )


@router.delete(
    "/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a video upload record and its on-disk file",
)
async def delete_upload(
    upload_id: str,
    store: PostgresStore = Depends(get_store),
    current_user: dict = Depends(
        require_roles(UserRole.engineer, UserRole.manager)
    ),
    video_svc: VideoService = Depends(_get_video_service),
):
    row = await store.get_video_upload(upload_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found.")

    # Delete DB record first; on-disk removal is best-effort
    await store.delete_video_upload(upload_id)
    video_svc.delete_file(row["stored_filename"])


@router.patch(
    "/timestamps",
    summary="Bulk-update video timestamp anchors on SOP actions",
)
async def patch_action_timestamps(
    body: BulkTimestampUpdateRequest,
    store: PostgresStore = Depends(get_store),
    _current_user: dict = Depends(
        require_roles(UserRole.engineer, UserRole.manager)
    ),
):
    patches = [p.model_dump() for p in body.patches]
    updated_count = await store.update_sop_action_timestamps(patches)
    return {"updated_count": updated_count}


@router.post(
    "/analyze/{upload_id}",
    response_model=VisionAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue deep-learning vision analysis (Celery/MediaPipe, non-blocking)",
)
async def analyze_video(
    upload_id: str,
    request: Request,
    store: PostgresStore = Depends(get_store),
    current_user: dict = Depends(
        require_roles(UserRole.engineer, UserRole.manager)
    ),
    video_svc: VideoService = Depends(_get_video_service),
):
    """Enqueue the MediaPipe deep-learning Vision Engine on an uploaded video.

    The analysis is offloaded to a Celery worker so the API returns immediately
    with HTTP 202 Accepted.  Poll ``GET /api/v1/video/{upload_id}`` and check
    the ``status`` field:  ``processing`` → ``analyzed`` (or ``failed``).

    Falls back to the synchronous heuristic engine when no Celery broker is
    reachable (development / test environments without Redis).

    Workflow
    --------
    1. Validate the upload exists and is in ``ready`` state.
    2. Mark the upload as ``processing``.
    3. Dispatch ``analyze_video_task.delay(upload_id)`` → return 202 immediately.
       (Fallback: run ``VisionService.analyze_video()`` synchronously.)
    """
    from ddm_v2.schemas import VideoUploadStatus

    # ── 1. Validate ────────────────────────────────────────────────────────
    upload = await store.get_video_upload(upload_id)
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found.",
        )
    if upload["status"] not in (VideoUploadStatus.ready, VideoUploadStatus.ready.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video must be in 'ready' status to analyse (current: {upload['status']}).",
        )

    sop_version = await store.find_by_id("sop_versions", upload["sop_version_id"])
    if sop_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated SOP version not found.",
        )

    if sop_version["status"] != "Draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SOP version must be in Draft status to receive AI-detected actions.",
        )

    # ── 2. Mark as processing ──────────────────────────────────────────────
    await store.update_video_upload_status(upload_id, VideoUploadStatus.processing.value)

    # ── 3. Dispatch to Celery worker (or synchronous fallback) ─────────────
    if analyze_video_task is not None:
        # Non-blocking: hand off to the Celery/Redis distributed queue.
        analyze_video_task.delay(upload_id)
        return VisionAnalysisResponse(
            upload_id=upload_id,
            sop_version_id=upload["sop_version_id"],
            detected_actions=[],
            total_active_segments=0,
            total_idle_segments=0,
            analysis_engine="mediapipe/queued",
            appended_action_count=0,
        )

    # ── Synchronous fallback (no Celery broker available) ──────────────────
    try:
        file_path: Path | None = None
        stored_fn: str | None = upload.get("stored_filename")
        if stored_fn:
            candidate = video_svc.get_file_path(stored_fn)
            if candidate.exists():
                file_path = candidate

        result = await _vision_service.analyze_video(
            upload_record=upload,
            store=store,
            file_path=file_path,
        )

        actions_for_db: list[dict] = result["actions_for_db"]
        if actions_for_db:
            existing_actions: list[dict] = list(sop_version.get("actions") or [])
            sop_version["actions"] = existing_actions + actions_for_db
            await store.upsert_collection_item("sop_versions", sop_version)

        await store.update_video_upload_status(upload_id, VideoUploadStatus.analyzed.value)

    except Exception as exc:
        await store.update_video_upload_status(
            upload_id,
            VideoUploadStatus.failed.value,
            error_message=str(exc)[:512],
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vision analysis failed: {exc}",
        ) from exc

    detected_action_models = [VisionDetectedAction(**a) for a in result["detected_actions"]]
    return VisionAnalysisResponse(
        upload_id=result["upload_id"],
        sop_version_id=result["sop_version_id"],
        detected_actions=detected_action_models,
        total_active_segments=result["total_active_segments"],
        total_idle_segments=result["total_idle_segments"],
        analysis_engine=result["analysis_engine"],
        appended_action_count=result["appended_action_count"],
    )

