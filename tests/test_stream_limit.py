import pytest
from app.services.stream_manager import stream_manager, StreamSlotUnavailableException
from app.models.video import Video, VideoStatus
from app.database import SessionLocal
from app.config import settings

def test_stream_slot_limit_enforcement(client):
    p = settings.base_prefix
    # Ensure a completed video exists in DB
    db = SessionLocal()
    vid_id = "vid_stream_test_slot"
    v = db.query(Video).filter(Video.id == vid_id).first()
    if not v:
        v = Video(
            id=vid_id,
            title="Slot Test Video",
            original_filename="slot.mp4",
            stored_upload_path="test.mp4",
            transcoded_path="test_720p.mp4",
            hls_dir_path="test_hls",
            hls_playlist_path="test_hls/master.m3u8",
            status=VideoStatus.COMPLETED
        )
        db.add(v)
        db.commit()
    db.close()

    # Clear any active sessions first
    stream_manager._sessions.clear()

    acquired_sessions = []
    # Acquire 5 slots (M = 5)
    for i in range(5):
        resp = client.get(f"{p}/api/v1/videos/{vid_id}/stream")
        assert resp.status_code == 200
        data = resp.json()["data"]
        acquired_sessions.append(data["session_id"])

    assert len(acquired_sessions) == 5

    # 6th stream attempt should fail with HTTP 429
    overflow_resp = client.get(f"{p}/api/v1/videos/{vid_id}/stream")
    assert overflow_resp.status_code == 429
    assert "Maximum concurrent streams limit reached" in overflow_resp.json()["detail"]

    # Heartbeat one of the active sessions
    hb_resp = client.post(f"{p}/api/v1/streams/{acquired_sessions[0]}/heartbeat")
    assert hb_resp.status_code == 200

    # Release one session
    rel_resp = client.post(f"{p}/api/v1/streams/{acquired_sessions[0]}/release")
    assert rel_resp.status_code == 200

    # Now a new stream attempt should succeed!
    retry_resp = client.get(f"{p}/api/v1/videos/{vid_id}/stream")
    assert retry_resp.status_code == 200

    # Cleanup
    stream_manager._sessions.clear()

def test_stream_mp4_endpoint_not_treated_as_segment(client, tmp_path):
    p = settings.base_prefix
    # Setup dummy video file on disk
    dummy_file = tmp_path / "valid_test.mp4"
    dummy_file.write_bytes(b"MOCK_STREAMING_DATA" * 50)

    db = SessionLocal()
    vid_id = "vid_test_mp4_route"
    v = db.query(Video).filter(Video.id == vid_id).first()
    if not v:
        v = Video(
            id=vid_id,
            title="MP4 Route Test",
            original_filename="route.mp4",
            stored_upload_path=str(dummy_file),
            transcoded_path=str(dummy_file),
            hls_dir_path=str(tmp_path),
            hls_playlist_path=str(tmp_path / "master.m3u8"),
            status=VideoStatus.COMPLETED
        )
        db.add(v)
        db.commit()
    else:
        v.transcoded_path = str(dummy_file)
        v.status = VideoStatus.COMPLETED
        db.commit()
    db.close()

    # Call /{prefix}/api/v1/streams/{video_id}/mp4
    resp = client.get(f"{p}/api/v1/streams/{vid_id}/mp4")
    # Must NOT be 404 Segment file not found
    assert resp.status_code in [200, 206]
    assert resp.headers.get("content-type") == "video/mp4"

