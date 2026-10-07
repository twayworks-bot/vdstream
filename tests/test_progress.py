import pytest
from app.models.video import Video, VideoStatus
from app.services.progress_tracker import progress_tracker
from app.services.ffmpeg_service import ffmpeg_service
from app.config import settings
from app.database import SessionLocal

def test_video_model_progress_percent():
    v = Video(
        id="vid_test_progress_model",
        title="Progress Model Test",
        original_filename="test.mp4",
        stored_upload_path="/fake/test.mp4",
        status=VideoStatus.PROCESSING,
        progress_percent=42.7
    )
    d = v.to_dict()
    assert "progress_percent" in d
    assert d["progress_percent"] == 42.7

    # When completed, progress is 100.0
    v.status = VideoStatus.COMPLETED
    d_completed = v.to_dict()
    assert d_completed["progress_percent"] == 100.0

    # When failed, progress is 0.0
    v.status = VideoStatus.FAILED
    d_failed = v.to_dict()
    assert d_failed["progress_percent"] == 0.0

def test_progress_tracker_monotonic_and_clamp():
    vid_id = "vid_tracker_test"
    progress_tracker.remove(vid_id)

    progress_tracker.set_progress(vid_id, 10.0, "10% stage")
    assert progress_tracker.get_progress(vid_id)["percent"] == 10.0

    # Test monotonic: setting lower value should not regress
    progress_tracker.set_progress(vid_id, 8.0, "should not regress")
    assert progress_tracker.get_progress(vid_id)["percent"] == 10.0

    # Test forward progress
    progress_tracker.set_progress(vid_id, 75.5, "75% stage")
    assert progress_tracker.get_progress(vid_id)["percent"] == 75.5

    # Test clamp at 100
    progress_tracker.set_progress(vid_id, 120.0, "over 100")
    assert progress_tracker.get_progress(vid_id)["percent"] == 100.0

    progress_tracker.remove(vid_id)
    assert progress_tracker.get_progress(vid_id) is None

def test_api_status_includes_live_progress(client):
    p = settings.base_prefix
    vid_id = "vid_live_api_progress_test"

    db = SessionLocal()
    v = db.query(Video).filter(Video.id == vid_id).first()
    if not v:
        v = Video(
            id=vid_id,
            title="Live Progress API Test",
            original_filename="live.mp4",
            stored_upload_path="/dummy/live.mp4",
            status=VideoStatus.PROCESSING,
            progress_percent=15.0
        )
        db.add(v)
    else:
        v.status = VideoStatus.PROCESSING
        v.progress_percent = 15.0
    db.commit()
    db.close()

    # Simulate in-memory live progress
    progress_tracker.set_progress(vid_id, 63.8, "Live transcode 64%")

    # Call GET /{prefix}/api/v1/videos/{video_id}/status
    resp = client.get(f"{p}/api/v1/videos/{vid_id}/status")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["video_id"] == vid_id
    assert data["status"] == "PROCESSING"
    assert data["progress_percent"] == 63.8
    assert "Live transcode" in data["status_message"]

    # Also check list API
    resp_list = client.get(f"{p}/api/v1/videos?limit=50")
    assert resp_list.status_code == 200
    items = resp_list.json()["data"]["items"]
    target_item = next((x for x in items if x["video_id"] == vid_id), None)
    assert target_item is not None
    assert target_item["progress_percent"] == 63.8

    progress_tracker.remove(vid_id)

def test_transcode_progress_callback_invoked(tmp_path, monkeypatch):
    dummy_input = tmp_path / "in.mp4"
    dummy_input.write_bytes(b"dummy_data_for_callback" * 100)
    out_mp4 = tmp_path / "out.mp4"
    out_hls_dir = tmp_path / "hls"

    calls = []
    def callback(pct, msg):
        calls.append((pct, msg))

    # Temporarily set available = False to test progress callback progression reliably
    monkeypatch.setattr(ffmpeg_service, "available", False)

    probe, _, _ = ffmpeg_service.transcode_to_720p_and_hls(
        str(dummy_input),
        str(out_mp4),
        str(out_hls_dir),
        "vid_cb_test",
        progress_callback=callback
    )

    # Verify callback was called and reached 100%
    assert len(calls) > 0
    final_pct, final_msg = calls[-1]
    assert final_pct == 100.0

