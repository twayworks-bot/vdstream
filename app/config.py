import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # Basic Application
    APP_PIN: str = "1234"
    HOST: str = "0.0.0.0"
    PORT: int = 5000
    DEFAULT_PREFIX: str = "vdstream"
    SECRET_KEY: str = "vdstream-secret-token-key-2026"

    # Concurrency and Queues (N < 5, M = 5)
    MAX_CONCURRENT_UPLOAD: int = 3
    MAX_CONCURRENT_TRANSCODE: int = 3
    MAX_QUEUE_SIZE: int = 20
    MAX_CONCURRENT_STREAMS: int = 5
    STREAM_SESSION_TIMEOUT_SECONDS: int = 60
    ALLOW_PREVIEW_FALLBACK: bool = True

    # Video Constraints
    MAX_VIDEOSIZE: str = "100MB"
    MAX_OUTPUT_VIDEO_SIZE_MB: int = 100
    MAX_VIDEOLAPS: str = "10min"
    MAX_VIDEO_DURATION_SECONDS: int = 600
    TARGET_MAX_HEIGHT: int = 720

    # Encoding Parameters
    VIDEO_CODEC: str = "libx264"
    AUDIO_CODEC: str = "aac"
    VIDEO_BITRATE: str = "2500k"
    AUDIO_BITRATE: str = "128k"
    HLS_SEGMENT_TIME: int = 4

    # Storage and Retention
    RETENTION_DAYS: int = 365
    CLEANUP_INTERVAL_HOURS: int = 24
    DOWNLOAD_DIR: str = "./downloads"
    STORAGE_DIR: str = "./storage"
    UPLOAD_DIR: str = "./storage/uploads"
    TRANSCODE_DIR: str = "./storage/transcoded"
    HLS_DIR: str = "./storage/hls"
    DB_URL: str = "sqlite:///./storage/vdstream.db"

    # FFmpeg Binaries
    FFMPEG_PATH: str = "./bin/ffmpeg.exe"
    FFPROBE_PATH: str = "./bin/ffprobe.exe"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def base_prefix(self) -> str:
        """Normalized base prefix starting with slash, e.g. '/vdstream', or '' if empty"""
        raw = self.DEFAULT_PREFIX.strip().strip("/")
        return f"/{raw}" if raw else ""

    def ensure_directories(self):
        for p in [self.STORAGE_DIR, self.UPLOAD_DIR, self.TRANSCODE_DIR, self.HLS_DIR, self.DOWNLOAD_DIR]:
            path = Path(p)
            if not path.is_absolute():
                path = BASE_DIR / path
            path.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()
