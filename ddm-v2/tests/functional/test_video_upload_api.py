"""Functional tests for Phase 5 Video Upload endpoints.

test_video_upload_triggers_vision_analysis: asserts the full upload→metadata
round-trip and the timestamp PATCH endpoint that the Vision Engine will call
after it finishes analysing the video.
"""

from __future__ import annotations

import io

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_MP4_BYTES = (
    # Minimal well-formed MP4 file with a mock mvhd atom so the lightweight
    # atom parser returns a real duration.  The bytes below encode:
    #   ftyp box (20 bytes) + mvhd version-0 atom with timescale=1000, dur=5000
    # Reference: ISO 14496-12 §4.3 / §8.2.2
    b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00isom"  # ftyp (20 bytes)
    # moov box header (size includes all children): we embed just the mvhd
    b"\x00\x00\x00\x6cmoov"                            # moov size=108, type
    # mvhd version 0: size(4)+type(4)+version(1)+flags(3)+
    #   ctime(4)+mtime(4)+timescale(4)+duration(4)+...padding to 68 bytes
    b"\x00\x00\x00\x68mvhd"                            # mvhd size=104, type
    b"\x00"                                             # version=0
    b"\x00\x00\x00"                                    # flags
    b"\x00\x00\x00\x00"                                # creation_time
    b"\x00\x00\x00\x00"                                # modification_time
    b"\x00\x00\x03\xe8"                                # timescale = 1000
    b"\x00\x00\x13\x88"                                # duration = 5000 → 5.0 s
    + b"\x00" * 60                                     # padding (rate/vol/etc.)
)


def _make_sop(client, headers) -> str:
    r = client.post(
        "/api/v1/sop/versions",
        headers=headers,
        json={
            "project_id": "proj-orion",
            "version_no": "V-VIDEO-TEST",
            "actions": [
                {
                    "seq_type": "GENERAL",
                    "description": "Pick screw",
                    "tmu": 10,
                    "seconds": 0.36,
                    "params": {},
                },
                {
                    "seq_type": "GENERAL",
                    "description": "Place screw",
                    "tmu": 12,
                    "seconds": 0.43,
                    "params": {},
                },
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_video_upload_triggers_vision_analysis(client, engineer_headers, tmp_path):
    """Full Phase-5 Phase-1 round-trip:

    1. Create a SOP version.
    2. Upload a (fake) MP4 file → 201 + VideoUploadOut with duration extracted.
    3. List uploads for the SOP version → 1 record.
    4. Simulate Vision Engine writing timestamp anchors (PATCH /timestamps).
    5. Retrieve the SOP version → actions carry the anchors.
    6. Fetch the upload metadata directly.
    7. Delete the upload → 204.
    """
    sop_id = _make_sop(client, engineer_headers)

    # ── 2. Upload fake video ────────────────────────────────────────────────
    resp = client.post(
        f"/api/v1/video/upload/{sop_id}",
        headers=engineer_headers,
        files={"file": ("workstation_take1.mp4", io.BytesIO(_FAKE_MP4_BYTES), "video/mp4")},
    )
    assert resp.status_code == 201, resp.text
    upload = resp.json()
    assert upload["sop_version_id"] == sop_id
    assert upload["original_filename"] == "workstation_take1.mp4"
    assert upload["status"] == "ready"
    # The lightweight atom parser should decode duration = 5.0 s from fake bytes
    assert upload["duration_seconds"] == pytest.approx(5.0, abs=0.01)

    upload_id = upload["id"]

    # ── 3. List uploads ─────────────────────────────────────────────────────
    list_resp = client.get(
        f"/api/v1/video/uploads/{sop_id}",
        headers=engineer_headers,
    )
    assert list_resp.status_code == 200, list_resp.text
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["id"] == upload_id

    # ── 4. Vision Engine writes timestamp anchors ───────────────────────────
    # First, retrieve the SOP version to get action IDs
    sop_resp = client.get(f"/api/v1/sop/versions/{sop_id}", headers=engineer_headers)
    assert sop_resp.status_code == 200, sop_resp.text
    actions = sop_resp.json()["actions"]
    assert len(actions) == 2

    patch_resp = client.patch(
        "/api/v1/video/timestamps",
        headers=engineer_headers,
        json={
            "sop_version_id": sop_id,
            "patches": [
                {
                    "action_id": actions[0]["id"],
                    "video_timestamp_start": 0.0,
                    "video_timestamp_end": 2.1,
                },
                {
                    "action_id": actions[1]["id"],
                    "video_timestamp_start": 2.1,
                    "video_timestamp_end": 4.8,
                },
            ],
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["updated_count"] == 2

    # ── 5. SOP actions now carry anchors ────────────────────────────────────
    sop_resp2 = client.get(f"/api/v1/sop/versions/{sop_id}", headers=engineer_headers)
    updated_actions = sop_resp2.json()["actions"]
    assert updated_actions[0]["video_timestamp_start"] == pytest.approx(0.0)
    assert updated_actions[0]["video_timestamp_end"] == pytest.approx(2.1)
    assert updated_actions[1]["video_timestamp_start"] == pytest.approx(2.1)
    assert updated_actions[1]["video_timestamp_end"] == pytest.approx(4.8)

    # ── 6. Fetch individual upload metadata ─────────────────────────────────
    meta_resp = client.get(f"/api/v1/video/{upload_id}", headers=engineer_headers)
    assert meta_resp.status_code == 200
    assert meta_resp.json()["id"] == upload_id

    # ── 7. Delete upload ────────────────────────────────────────────────────
    del_resp = client.delete(f"/api/v1/video/{upload_id}", headers=engineer_headers)
    assert del_resp.status_code == 204

    # Confirm it's gone
    gone_resp = client.get(f"/api/v1/video/{upload_id}", headers=engineer_headers)
    assert gone_resp.status_code == 404


@pytest.mark.functional
def test_video_upload_rejects_invalid_extension(client, engineer_headers):
    """A non-video file extension must be rejected with 422."""
    sop_id = _make_sop(client, engineer_headers)
    resp = client.post(
        f"/api/v1/video/upload/{sop_id}",
        headers=engineer_headers,
        files={"file": ("exploit.exe", b"\x4d\x5a\x90\x00", "application/x-msdownload")},
    )
    assert resp.status_code == 422


@pytest.mark.functional
def test_video_upload_returns_404_for_missing_sop(client, engineer_headers):
    """Upload to a non-existent SOP version must return 404."""
    resp = client.post(
        "/api/v1/video/upload/sop-does-not-exist",
        headers=engineer_headers,
        files={"file": ("test.mp4", _FAKE_MP4_BYTES, "video/mp4")},
    )
    assert resp.status_code == 404


@pytest.mark.functional
def test_video_timestamp_patch_ignores_unknown_action(client, engineer_headers):
    """Patching a non-existent action_id must not crash — updated_count reflects
    only rows that were actually found and updated.
    """
    sop_id = _make_sop(client, engineer_headers)
    resp = client.patch(
        "/api/v1/video/timestamps",
        headers=engineer_headers,
        json={
            "sop_version_id": sop_id,
            "patches": [
                {
                    "action_id": "nonexistent-action-id",
                    "video_timestamp_start": 0.0,
                    "video_timestamp_end": 1.0,
                }
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["updated_count"] == 0


# ---------------------------------------------------------------------------
# Phase 2 — Vision Analysis API
# ---------------------------------------------------------------------------

# Larger fake MP4 with 60-second duration (timescale=1000, duration=60_000)
_FAKE_MP4_60S = (
    b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00isom"
    b"\x00\x00\x00\x6cmoov"
    b"\x00\x00\x00\x68mvhd"
    b"\x00"          # version=0
    b"\x00\x00\x00"  # flags
    b"\x00\x00\x00\x00"   # creation_time
    b"\x00\x00\x00\x00"   # modification_time
    b"\x00\x00\x03\xe8"   # timescale = 1000
    b"\x00\x00\xEA\x60"   # duration = 60_000 → 60.0 s
    + b"\x00" * 60
)


@pytest.mark.functional
def test_analyze_endpoint_produces_timestamped_actions(client, engineer_headers):
    """POST /api/v1/video/analyze/{upload_id}:
    - Runs the heuristic Vision Engine on the uploaded video.
    - Appends detected actions to the SOP version.
    - Returns VisionAnalysisResponse with sequential timestamps.
    - Upload status transitions to 'analyzed'.
    """
    # 1. SOP version with no actions
    create = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": "proj-orion", "version_no": "V-VISION-API", "actions": []},
    )
    assert create.status_code == 201
    sop_id = create.json()["id"]

    # 2. Upload a 60-second fake video
    upload_resp = client.post(
        f"/api/v1/video/upload/{sop_id}",
        headers=engineer_headers,
        files={"file": ("assembly_60s.mp4", io.BytesIO(_FAKE_MP4_60S), "video/mp4")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    upload_id = upload_resp.json()["id"]
    assert upload_resp.json()["duration_seconds"] == pytest.approx(60.0, abs=0.1)

    # 3. Trigger analysis
    analyze_resp = client.post(
        f"/api/v1/video/analyze/{upload_id}",
        headers=engineer_headers,
    )
    assert analyze_resp.status_code == 202, analyze_resp.text
    analysis = analyze_resp.json()

    assert analysis["upload_id"] == upload_id
    assert analysis["sop_version_id"] == sop_id
    assert analysis["analysis_engine"] in ("heuristic", "opencv", "mediapipe/queued")

    detected = analysis["detected_actions"]
    # When Celery is active detected_actions is [] (queued); skip content checks.
    if detected:
        # Sequential timestamps
        starts = [a["video_timestamp_start"] for a in detected]
        assert starts == sorted(starts), "Detected actions must be sorted by timestamp"

        for a in detected:
            assert a["video_timestamp_end"] > a["video_timestamp_start"]
            assert a["confidence"] > 0.0
            assert a["tmu"] >= 1
            assert "[AI Detected]" in a["description"]

    # 4. SOP version now has appended AI actions (synchronous path only)
    if analysis.get("appended_action_count", 0) > 0:
        sop_after = client.get(f"/api/v1/sop/versions/{sop_id}", headers=engineer_headers)
        assert sop_after.status_code == 200
        actions_after = sop_after.json()["actions"]
        assert len(actions_after) == analysis["appended_action_count"]

    # 5. Upload status is 'analyzed' or 'processing' (if queued to Celery)
    upload_after = client.get(f"/api/v1/video/{upload_id}", headers=engineer_headers)
    assert upload_after.json()["status"] in ("analyzed", "processing")


@pytest.mark.functional
def test_analyze_rejects_non_ready_upload(client, engineer_headers):
    """Calling analyze on a non-ready upload must return 409."""
    sop_id = _make_sop(client, engineer_headers)

    # Upload, analyze first time → status becomes 'analyzed'
    up = client.post(
        f"/api/v1/video/upload/{sop_id}",
        headers=engineer_headers,
        files={"file": ("a.mp4", io.BytesIO(_FAKE_MP4_60S), "video/mp4")},
    )
    assert up.status_code == 201
    uid = up.json()["id"]

    r1 = client.post(f"/api/v1/video/analyze/{uid}", headers=engineer_headers)
    assert r1.status_code == 202

    # Second call should be rejected with 409 only if the first completed synchronously.
    # In Celery mode the upload status is 'processing' after the first call, so
    # the second call also returns 409 (not ready).
    r2 = client.post(f"/api/v1/video/analyze/{uid}", headers=engineer_headers)
    assert r2.status_code == 409


@pytest.mark.functional
def test_analyze_returns_404_for_missing_upload(client, engineer_headers):
    resp = client.post("/api/v1/video/analyze/no-such-upload", headers=engineer_headers)
    assert resp.status_code == 404
