import pytest
from unittest.mock import patch
from app.services.ffmpeg_service import ffmpeg_service, VideoDurationExceededError, VideoSizeExceededError
from app.config import settings

def test_duration_constraint_exceeded():
    # Mock probe_video returning 601 seconds (> 600 seconds)
    with patch.object(ffmpeg_service, "probe_video", return_value={"duration": 605.0, "width": 1920, "height": 1080}):
        with pytest.raises(VideoDurationExceededError):
            ffmpeg_service.transcode_to_720p_and_hls(
                "dummy_input.mp4",
                "dummy_output.mp4",
                "dummy_hls_dir",
                "vid_test"
            )

def test_duration_constraint_acceptable(tmp_path):
    # Mock probe_video returning 590 seconds (<= 600 seconds)
    dummy_input = tmp_path / "dummy_input.mp4"
    dummy_input.write_bytes(b"DUMMY_MP4_CONTENT_FOR_TEST")
    output_mp4 = tmp_path / "out" / "dummy_out.mp4"
    output_hls = tmp_path / "hls"

    with patch.object(ffmpeg_service, "available", False):
        with patch.object(ffmpeg_service, "probe_video", return_value={"duration": 590.0, "width": 1920, "height": 1080}):
            probe, mp4_out, hls_out = ffmpeg_service.transcode_to_720p_and_hls(
                str(dummy_input),
                str(output_mp4),
                str(output_hls),
                "vid_test"
            )
            assert probe["duration"] == 590.0
            assert probe["height"] <= 720
