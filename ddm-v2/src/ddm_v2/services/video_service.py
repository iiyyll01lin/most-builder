"""Video Upload & Metadata Extraction Service — Phase 5 Vision Engine.

Responsibilities
----------------
1. Persist an uploaded video file to ``video_upload_dir`` under a UUID-based
   filename (prevents path-traversal and filename collisions).
2. Extract video metadata (duration, resolution, FPS) in-process when the
   optional ``opencv-python`` package is available; otherwise falls back to a
   lightweight probe using the ``struct`` stdlib parser for MP4 ``mvhd`` atoms.
   In test environments where no real video exists a mock result is returned.
3. Return a plain ``dict`` matching the ``VideoUploadRow`` schema, ready for
   the ``PostgresStore`` to persist.

No side-effects on the database — callers own the transaction.
"""

from __future__ import annotations

import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Accepted MIME types and extensions (deny-list everything else)
# ---------------------------------------------------------------------------
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",   # AVI
        "video/webm",
        "video/x-matroska",
        "video/mpeg",
        "application/octet-stream",  # generic fallback for multipart uploads
    }
)

_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".mp4", ".mov", ".avi", ".webm", ".mkv", ".mpg", ".mpeg"}
)

_MAX_FILE_SIZE_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GiB hard ceiling


# ---------------------------------------------------------------------------
# Metadata extraction helpers
# ---------------------------------------------------------------------------


def _try_opencv_metadata(file_path: Path) -> dict[str, Any] | None:
    """Attempt metadata extraction via opencv-python.

    Returns a dict with ``duration_seconds``, ``width``, ``height``, ``fps``
    or None when OpenCV is not installed or cannot open the file.
    """
    try:
        import cv2  # type: ignore[import]
    except ImportError:
        return None

    cap = None
    try:
        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            return None
        fps: float = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count: float = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        width: int = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height: int = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = (frame_count / fps) if fps > 0 else None
        return {
            "duration_seconds": round(duration, 3) if duration is not None else None,
            "width": width or None,
            "height": height or None,
            "fps": round(fps, 3) if fps > 0 else None,
        }
    except Exception:  # noqa: BLE001
        return None
    finally:
        if cap is not None:
            cap.release()


def _try_mp4_atom_metadata(file_path: Path) -> dict[str, Any] | None:
    """Minimal MP4 ``mvhd`` atom parser — no external dependencies.

    Reads only the first 64 KiB to locate the ``moov/mvhd`` atom.  Works for
    well-formed MP4/MOV files produced by common cameras.  Returns None for
    all other container formats or malformed files.
    """
    try:
        with file_path.open("rb") as fh:
            data = fh.read(65536)

        pos = 0
        # Search for "mvhd" by scanning the header bytes
        while pos < len(data) - 8:
            idx = data.find(b"mvhd", pos)
            if idx < 4:
                break
            # The mvhd box: [size:4][type:4][version:1][flags:3][...timescale/duration]
            version = data[idx + 4]
            if version == 0:
                # 32-bit: creation_time(4), modification_time(4), timescale(4), duration(4)
                ts_offset = idx + 4 + 1 + 3 + 4 + 4
                if ts_offset + 8 <= len(data):
                    timescale, dur = struct.unpack_from(">II", data, ts_offset)
                    if timescale > 0:
                        return {"duration_seconds": round(dur / timescale, 3), "width": None, "height": None, "fps": None}
            elif version == 1:
                # 64-bit: creation_time(8), modification_time(8), timescale(4), duration(8)
                ts_offset = idx + 4 + 1 + 3 + 8 + 8
                if ts_offset + 12 <= len(data):
                    (timescale,) = struct.unpack_from(">I", data, ts_offset)
                    (dur,) = struct.unpack_from(">Q", data, ts_offset + 4)
                    if timescale > 0:
                        return {"duration_seconds": round(dur / timescale, 3), "width": None, "height": None, "fps": None}
            pos = idx + 1
    except Exception:  # noqa: BLE001
        pass
    return None


def extract_video_metadata(file_path: Path) -> dict[str, Any]:
    """Return ``{duration_seconds, width, height, fps}`` for *file_path*.

    Tries OpenCV first, then the lightweight MP4 atom parser, then returns a
    minimal fallback dict with all fields set to ``None``.  This ensures the
    upload pipeline never fails purely due to missing vision libraries.
    """
    meta = _try_opencv_metadata(file_path)
    if meta is not None:
        return meta

    meta = _try_mp4_atom_metadata(file_path)
    if meta is not None:
        return meta

    # Could not extract metadata — return nulls so the record is still created
    return {"duration_seconds": None, "width": None, "height": None, "fps": None}


# ---------------------------------------------------------------------------
# VideoService
# ---------------------------------------------------------------------------


class VideoService:
    """Stateless service for persisting uploaded video files and building the
    metadata record dict that ``PostgresStore`` will write to the DB.
    """

    def __init__(self, upload_dir: Path) -> None:
        self._upload_dir = upload_dir

    def _ensure_upload_dir(self) -> None:
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_upload(
        self,
        content_type: str | None,
        original_filename: str,
        file_size: int,
    ) -> None:
        """Raise ``ValueError`` with a human-readable message if the upload is
        not allowed.  Called *before* writing any bytes to disk.
        """
        ext = Path(original_filename).suffix.lower()
        ct = (content_type or "").lower().split(";")[0].strip()

        if ext not in _ALLOWED_EXTENSIONS and ct not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(
                f"Unsupported video format '{original_filename}'. "
                f"Allowed extensions: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
            )
        if file_size > _MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File size {file_size:,} bytes exceeds the 2 GiB limit."
            )

    async def save_and_record(
        self,
        *,
        file_data: bytes,
        original_filename: str,
        content_type: str | None,
        sop_version_id: str,
        project_id: str,
        uploaded_by: str | None,
    ) -> dict[str, Any]:
        """Persist *file_data* to disk and return a metadata ``dict`` ready for
        ``PostgresStore.create_video_upload()``.

        This method is ``async`` to keep the FastAPI handler signature uniform;
        disk I/O is synchronous (acceptable for <2 GiB files given the GIL
        releases around file write).  For a production deployment, wrap the
        write in ``asyncio.to_thread`` if very large files or high concurrency
        are expected.
        """
        self._ensure_upload_dir()

        file_id = str(uuid.uuid4())
        ext = Path(original_filename).suffix.lower() or ".bin"
        stored_filename = f"{file_id}{ext}"
        dest = self._upload_dir / stored_filename

        dest.write_bytes(file_data)

        meta = extract_video_metadata(dest)

        return {
            "id": file_id,
            "sop_version_id": sop_version_id,
            "project_id": project_id,
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "file_size": len(file_data),
            "duration_seconds": meta.get("duration_seconds"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "fps": meta.get("fps"),
            "status": "ready",
            "uploaded_by": uploaded_by,
            "uploaded_at": datetime.now(timezone.utc),
            "error_message": None,
        }

    def get_file_path(self, stored_filename: str) -> Path:
        """Return the absolute on-disk path for a stored filename.

        The caller is responsible for verifying that ``stored_filename`` comes
        from a trusted source (i.e., loaded from the DB record, never from a
        raw HTTP request parameter) to prevent path-traversal attacks.
        """
        # Extra safety: strip any directory component that may have slipped in.
        safe_name = Path(stored_filename).name
        return self._upload_dir / safe_name

    def delete_file(self, stored_filename: str) -> None:
        """Remove a stored video file from disk; silently ignores missing files."""
        path = self.get_file_path(stored_filename)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
