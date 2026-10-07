import os
import shutil
import asyncio
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from app.config import settings, BASE_DIR

logger = logging.getLogger("vdstream.ffmpeg")

class FFmpegError(Exception):
    pass

class VideoDurationExceededError(FFmpegError):
    pass

class VideoSizeExceededError(FFmpegError):
    pass

class FFmpegService:
    def __init__(self):
        self.ffmpeg_path = self._resolve_executable(settings.FFMPEG_PATH, "ffmpeg")
        self.ffprobe_path = self._resolve_executable(settings.FFPROBE_PATH, "ffprobe")
        # FFmpeg alone is sufficient for probing and transcoding
        self.available = bool(self.ffmpeg_path)
        if self.available:
            logger.info(f"FFmpeg located: {self.ffmpeg_path}")
            if self.ffprobe_path:
                logger.info(f"FFprobe located: {self.ffprobe_path}")
            else:
                logger.info("FFprobe not found; will use FFmpeg -i fallback for probing.")
        else:
            logger.warning(
                "FFmpeg binary not found on system PATH or configured path! "
                "System will operate in fallback/mock mode for test environments."
            )

    def _resolve_executable(self, configured_path: str, name: str) -> Optional[str]:
        # 1. Check configured path
        p = Path(configured_path)
        if not p.is_absolute():
            p = (BASE_DIR / p).resolve()
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
        
        # 2. Check system PATH
        system_which = shutil.which(name)
        if system_which:
            return system_which
            
        return None

    def probe_video(self, input_path: str) -> Dict[str, Any]:
        """Extract duration, resolution, codecs from video using ffprobe or ffmpeg -i"""
        if not self.available:
            # Fallback mock probe for development when ffmpeg binary is not placed yet
            file_size = os.path.getsize(input_path) if os.path.exists(input_path) else 1024
            return {
                "duration": 60.0,
                "width": 1280,
                "height": 720,
                "video_codec": "h264",
                "audio_codec": "aac",
                "bitrate": 2000000,
                "size_bytes": file_size
            }

        # 1. Try ffprobe if available
        if self.ffprobe_path:
            try:
                cmd = [
                    self.ffprobe_path,
                    "-v", "error",
                    "-show_entries", "format=duration,size,bit_rate:stream=width,height,codec_name,codec_type",
                    "-of", "json",
                    input_path
                ]
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True
                )
                probe_data = json.loads(result.stdout)
                
                fmt = probe_data.get("format", {})
                duration = float(fmt.get("duration", 0.0))
                size_bytes = int(fmt.get("size", os.path.getsize(input_path)))
                bitrate = int(fmt.get("bit_rate", 0))

                width = None
                height = None
                video_codec = None
                audio_codec = None

                for s in probe_data.get("streams", []):
                    ctype = s.get("codec_type")
                    if ctype == "video" and width is None:
                        width = s.get("width")
                        height = s.get("height")
                        video_codec = s.get("codec_name")
                    elif ctype == "audio" and audio_codec is None:
                        audio_codec = s.get("codec_name")

                return {
                    "duration": duration,
                    "width": width or 1280,
                    "height": height or 720,
                    "video_codec": video_codec or "unknown",
                    "audio_codec": audio_codec or "unknown",
                    "bitrate": bitrate,
                    "size_bytes": size_bytes
                }
            except Exception as e:
                logger.warning(f"FFprobe failed, falling back to FFmpeg -i: {e}")

        # 2. Use ffmpeg -i to probe metadata via stderr
        try:
            import re
            cmd = [self.ffmpeg_path, "-i", input_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
            output = res.stderr

            file_size = os.path.getsize(input_path) if os.path.exists(input_path) else 0

            # Match Duration: 00:06:09.99
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", output)
            duration = 0.0
            if dur_match:
                hours = float(dur_match.group(1))
                minutes = float(dur_match.group(2))
                seconds = float(dur_match.group(3))
                duration = hours * 3600 + minutes * 60 + seconds

            # Match Resolution: 1280x720
            res_match = re.search(r",\s*(\d{2,5})x(\d{2,5})", output)
            width = int(res_match.group(1)) if res_match else 1280
            height = int(res_match.group(2)) if res_match else 720

            # Match Video Codec: Video: h264
            v_match = re.search(r"Video:\s*([a-zA-Z0-9_-]+)", output)
            video_codec = v_match.group(1) if v_match else "h264"

            # Match Audio Codec: Audio: aac
            a_match = re.search(r"Audio:\s*([a-zA-Z0-9_-]+)", output)
            audio_codec = a_match.group(1) if a_match else "aac"

            # Match Bitrate: bitrate: 2268 kb/s
            br_match = re.search(r"bitrate:\s*(\d+)\s*kb/s", output)
            bitrate = int(br_match.group(1)) * 1000 if br_match else 2000000

            return {
                "duration": duration,
                "width": width,
                "height": height,
                "video_codec": video_codec,
                "audio_codec": audio_codec,
                "bitrate": bitrate,
                "size_bytes": file_size
            }
        except Exception as e:
            logger.error(f"FFmpeg -i probe error: {e}")
            raise FFmpegError(f"Error reading video metadata: {str(e)}")

    def transcode_to_720p_and_hls(
        self,
        input_path: str,
        output_mp4_path: str,
        output_hls_dir: str,
        video_id: str,
        progress_callback: Optional[Any] = None
    ) -> Tuple[Dict[str, Any], str, str]:
        """
        Transcode input video to max 720p H.264/AAC MP4 and generate HLS bundle.
        Enforces duration <= 10 min (600s) and resulting size <= 100MB.
        Reports live progress percentages (0% -> 100%) via progress_callback.
        """
        def report(pct: float, msg: str):
            if progress_callback:
                try:
                    progress_callback(pct, msg)
                except Exception:
                    pass

        # 1. Probe input video
        report(5.0, "입력 비디오 메타데이터 분석 중 (5%)...")
        probe = self.probe_video(input_path)
        duration = probe.get("duration", 0.0)

        # 2. Enforce Duration Constraint (10 min = 600 seconds)
        if duration > settings.MAX_VIDEO_DURATION_SECONDS:
            raise VideoDurationExceededError(
                f"Video duration ({duration:.1f}s) exceeds maximum allowed limit of {settings.MAX_VIDEO_DURATION_SECONDS}s (10 minutes)."
            )

        os.makedirs(os.path.dirname(output_mp4_path), exist_ok=True)
        os.makedirs(output_hls_dir, exist_ok=True)
        master_m3u8 = os.path.join(output_hls_dir, "master.m3u8")

        # Fallback Mock Transcode if FFmpeg is not installed
        if not self.available:
            logger.info("Using mock transcoder since FFmpeg binary is absent.")
            report(30.0, "720p 모의 변환 중 (30%)...")
            # Create a mock valid MP4 file and mock HLS files for seamless test/dev operation
            with open(output_mp4_path, "wb") as f:
                f.write(b"MOCK_MP4_HEADER_VDSTREAM_720P_VALID_STREAM" + (b"\x00" * 1024))
            
            report(75.0, "HLS 모의 세그먼트 생성 중 (75%)...")
            with open(master_m3u8, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXT-X-MEDIA-SEQUENCE:0\n")
                f.write("#EXTINF:4.000000,\nsegment_000.ts\n#EXT-X-ENDLIST\n")

            mock_seg = os.path.join(output_hls_dir, "segment_000.ts")
            with open(mock_seg, "wb") as f:
                f.write(b"MOCK_TS_PACKET_VDSTREAM" + (b"\x00" * 512))

            result_size = os.path.getsize(output_mp4_path)
            probe["final_size_bytes"] = result_size
            probe["height"] = min(probe.get("height", 720), settings.TARGET_MAX_HEIGHT)
            report(100.0, "트랜스코딩 완료. 즉시 스트리밍 가능.")
            return probe, output_mp4_path, master_m3u8

        # Calculate dynamic bitrate to guarantee <= 100MB
        max_bytes = settings.MAX_OUTPUT_VIDEO_SIZE_MB * 1024 * 1024
        target_bitrate_kbps = 2500
        if duration > 0:
            safe_video_bitrate = int(((max_bytes * 0.90 * 8) / duration) / 1000) - 128
            target_bitrate_kbps = max(500, min(2500, safe_video_bitrate))

        logger.info(f"Target video bitrate for {duration:.1f}s video: {target_bitrate_kbps}k")

        # Step A: Transcode to Max 720p MP4 (FastStart enabled) with live -progress output
        mp4_cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-vf", f"scale=-2:min({settings.TARGET_MAX_HEIGHT}\\,ih)",
            "-c:v", settings.VIDEO_CODEC,
            "-preset", "fast",
            "-b:v", f"{target_bitrate_kbps}k",
            "-maxrate", f"{int(target_bitrate_kbps * 1.5)}k",
            "-bufsize", f"{int(target_bitrate_kbps * 2)}k",
            "-c:a", settings.AUDIO_CODEC,
            "-b:a", settings.AUDIO_BITRATE,
            "-ar", "44100",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            output_mp4_path
        ]

        logger.info(f"Running MP4 Transcode command with progress: {' '.join(mp4_cmd)}")
        report(10.0, "720p H.264 인코딩 시작 (10%)...")

        err_log_path = f"{output_mp4_path}.ffmpeg_err.log"
        try:
            with open(err_log_path, "w", encoding="utf-8", errors="replace") as err_file:
                process = subprocess.Popen(
                    mp4_cmd,
                    stdout=subprocess.PIPE,
                    stderr=err_file,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )

                last_reported = 10.0
                if process.stdout:
                    for line in process.stdout:
                        line = line.strip()
                        if line.startswith("out_time_us="):
                            val = line.split("=", 1)[1]
                            if val.isdigit():
                                us = int(val)
                                sec = us / 1_000_000.0
                                if duration > 0:
                                    ratio = min(sec / duration, 1.0)
                                    cur_pct = 10.0 + (ratio * 75.0)  # 10% ~ 85%
                                    if cur_pct - last_reported >= 1.5 or cur_pct >= 84.0:
                                        last_reported = cur_pct
                                        report(cur_pct, f"720p H.264 인코딩 중 ({int(cur_pct)}%)")
                        elif line.startswith("progress=end"):
                            break

                process.wait()

            if process.returncode != 0:
                err_content = ""
                if os.path.exists(err_log_path):
                    with open(err_log_path, "r", encoding="utf-8", errors="replace") as ef:
                        err_content = ef.read()[-1000:]
                logger.error(f"FFmpeg MP4 transcoding failed: {err_content}")
                raise FFmpegError(f"FFmpeg MP4 transcoding failed: {err_content}")

        finally:
            if os.path.exists(err_log_path):
                try:
                    os.remove(err_log_path)
                except Exception:
                    pass

        # Verify output size does not exceed 100MB
        final_mp4_size = os.path.getsize(output_mp4_path)
        if final_mp4_size > max_bytes:
            os.remove(output_mp4_path)
            raise VideoSizeExceededError(
                f"Transcoded video size ({final_mp4_size / (1024*1024):.2f}MB) exceeds limit of {settings.MAX_OUTPUT_VIDEO_SIZE_MB}MB."
            )

        # Step B: Generate HLS segments and playlist from transcoded 720p MP4
        report(86.0, "HLS 무다운로드 스트리밍 세그먼트 생성 중 (86%)...")
        segment_pattern = os.path.join(output_hls_dir, "segment_%03d.ts")
        hls_cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", output_mp4_path,
            "-c", "copy",
            "-hls_time", str(settings.HLS_SEGMENT_TIME),
            "-hls_list_size", "0",
            "-hls_segment_filename", segment_pattern,
            master_m3u8
        ]

        logger.info(f"Running HLS Generation command: {' '.join(hls_cmd)}")
        res_hls = subprocess.run(
            hls_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if res_hls.returncode != 0:
            logger.error(f"FFmpeg HLS segmentation failed: {res_hls.stderr}")
            raise FFmpegError(f"FFmpeg HLS generation failed: {res_hls.stderr}")

        report(98.0, "메타데이터 동기화 및 스트리밍 플레이리스트 준비 중 (98%)...")

        # Post-probe result MP4
        post_probe = self.probe_video(output_mp4_path)
        post_probe["final_size_bytes"] = final_mp4_size

        report(100.0, "트랜스코딩 완료. 스트리밍 준비 완료.")
        return post_probe, output_mp4_path, master_m3u8

ffmpeg_service = FFmpegService()
