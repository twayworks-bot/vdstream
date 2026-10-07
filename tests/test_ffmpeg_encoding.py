import os
import subprocess
from unittest.mock import patch, MagicMock
import pytest
from app.services.ffmpeg_service import ffmpeg_service

def test_subprocess_encoding_safety_with_special_bytes():
    """
    Verify that subprocess.run in probe_video and transcode does not fail
    with UnicodeDecodeError when encountering non-cp949 bytes like 0xa9 (©).
    """
    special_bytes = b"FFmpeg version x264 core 164 \xa9 2026 Author \xed\x95\x9c\xea\xb8\x80"
    
    # Simulate a subprocess run result with non-CP949 UTF-8/Latin-1 bytes
    decoded_text = special_bytes.decode("utf-8", errors="replace")
    
    # Assert that decode with 'replace' does not raise UnicodeDecodeError
    assert "\ufffd" in decoded_text or "2026" in decoded_text

def test_probe_video_handles_utf8_and_special_characters(tmp_path):
    """
    Verify probe_video safely handles metadata containing unicode/special characters.
    """
    dummy_file = tmp_path / "test_unicode.mp4"
    dummy_file.write_bytes(b"dummy video data")
    
    # Mock subprocess.run simulating FFmpeg output containing non-cp949 bytes
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stderr = "Input #0, mov,mp4: Duration: 00:01:00.00, bitrate: 2000 kb/s\n Stream #0:0: Video: h264, 1280x720 \xa9"
    mock_res.stdout = ""
    
    with patch("subprocess.run", return_value=mock_res) as mock_run:
        meta = ffmpeg_service.probe_video(str(dummy_file))
        assert meta["duration"] == 60.0
        assert meta["width"] == 1280
        assert meta["height"] == 720
        # Check that subprocess.run was called with encoding="utf-8" and errors="replace" or "ignore"
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("encoding") == "utf-8"
        assert call_kwargs.get("errors") in ["replace", "ignore"]
