from fastapi import APIRouter
from app.config import settings
from app.services.queue_manager import queue_manager
from app.services.stream_manager import stream_manager
from app.services.ffmpeg_service import ffmpeg_service

router = APIRouter()

@router.get("/status")
async def get_system_status():
    """Retrieve runtime resource, queue, and streaming slot status"""
    q_status = queue_manager.get_status()
    s_status = stream_manager.get_status()
    
    return {
        "status": "success",
        "data": {
            "transcoding": q_status,
            "streaming": s_status,
            "constraints": {
                "max_resolution": f"{settings.TARGET_MAX_HEIGHT}p",
                "max_file_size_mb": settings.MAX_OUTPUT_VIDEO_SIZE_MB,
                "max_duration_seconds": settings.MAX_VIDEO_DURATION_SECONDS,
                "retention_days": settings.RETENTION_DAYS
            },
            "ffmpeg": {
                "available": ffmpeg_service.available,
                "ffmpeg_path": ffmpeg_service.ffmpeg_path,
                "ffprobe_path": ffmpeg_service.ffprobe_path
            }
        }
    }
