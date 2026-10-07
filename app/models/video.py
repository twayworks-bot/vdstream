import enum
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, String, Integer, Float, BigInteger, DateTime, Enum, Text
from app.database import Base
from app.config import settings

class VideoStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

def default_expiry():
    return datetime.now(timezone.utc) + timedelta(days=settings.RETENTION_DAYS)

class Video(Base):
    __tablename__ = "videos"

    id = Column(String(64), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    stored_upload_path = Column(String(512), nullable=False)
    transcoded_path = Column(String(512), nullable=True)
    hls_dir_path = Column(String(512), nullable=True)
    hls_playlist_path = Column(String(512), nullable=True)
    
    status = Column(Enum(VideoStatus), default=VideoStatus.QUEUED, nullable=False, index=True)
    status_message = Column(Text, nullable=True)
    
    duration_seconds = Column(Float, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True, default=0)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    view_count = Column(Integer, default=0, nullable=False)
    progress_percent = Column(Float, default=0.0, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, default=default_expiry, nullable=False, index=True)

    def to_dict(self):
        file_size_mb = round(self.file_size_bytes / (1024 * 1024), 2) if self.file_size_bytes else 0.0
        # Determine actual progress percent
        if self.status == VideoStatus.COMPLETED:
            eff_progress = 100.0
        elif self.status == VideoStatus.FAILED:
            eff_progress = 0.0
        else:
            eff_progress = round(self.progress_percent or 0.0, 1)

        return {
            "video_id": self.id,
            "title": self.title,
            "original_filename": self.original_filename,
            "status": self.status.value,
            "status_message": self.status_message,
            "progress_percent": eff_progress,
            "duration_seconds": self.duration_seconds,
            "duration_formatted": f"{int(self.duration_seconds // 60)}:{int(self.duration_seconds % 60):02d}" if self.duration_seconds else "0:00",
            "file_size_bytes": self.file_size_bytes,
            "file_size_mb": file_size_mb,
            "width": self.width,
            "height": self.height,
            "view_count": self.view_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_ready": self.status == VideoStatus.COMPLETED
        }
