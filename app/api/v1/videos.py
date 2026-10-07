import os
import uuid
import time
import aiofiles
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings, BASE_DIR
from app.database import get_db
from app.models.video import Video, VideoStatus
from app.services.queue_manager import queue_manager, QueueFullException
from app.services.stream_manager import stream_manager, StreamSlotUnavailableException
from app.services.retention_service import retention_service

router = APIRouter()

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v"}

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_video(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Upload a video file and queue it for 720p transcoding and HLS packaging.
    Enforces concurrency N and FIFO queueing.
    """
    # 1. Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported video format: '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # 2. Generate unique video id
    video_id = f"vid_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    video_title = title.strip() if title and title.strip() else file.filename

    # 3. Save uploaded file to storage/uploads
    upload_filename = f"{video_id}_{file.filename}"
    upload_path = (Path(settings.UPLOAD_DIR) / upload_filename).resolve()
    
    try:
        async with aiofiles.open(upload_path, "wb") as out_file:
            while content := await file.read(1024 * 1024):  # 1MB chunks
                await out_file.write(content)
    except Exception as e:
        if upload_path.exists():
            upload_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )

    # 4. Target destination paths
    transcoded_filename = f"{video_id}_720p.mp4"
    transcoded_path = (Path(settings.TRANSCODE_DIR) / transcoded_filename).resolve()
    hls_dir = (Path(settings.HLS_DIR) / video_id).resolve()
    hls_master = hls_dir / "master.m3u8"

    # 5. Create database record
    video = Video(
        id=video_id,
        title=video_title,
        original_filename=file.filename,
        stored_upload_path=str(upload_path),
        transcoded_path=str(transcoded_path),
        hls_dir_path=str(hls_dir),
        hls_playlist_path=str(hls_master),
        status=VideoStatus.QUEUED,
        status_message="Video uploaded. Waiting in transcode queue."
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    # 6. Enqueue task for background worker
    try:
        q_size = await queue_manager.enqueue(video_id)
    except QueueFullException as e:
        # If queue is full, update video status to FAILED and reject
        video.status = VideoStatus.FAILED
        video.status_message = str(e)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )

    return {
        "status": "success",
        "message": "Video uploaded successfully and queued for transcoding.",
        "data": {
            "video_id": video.id,
            "filename": video.original_filename,
            "title": video.title,
            "status": video.status.value,
            "queue_position": q_size,
            "created_at": video.created_at.isoformat(),
            "expires_at": video.expires_at.isoformat(),
            "status_url": f"{settings.base_prefix}/api/v1/videos/{video.id}/status"
        }
    }

@router.get("/{video_id}/status")
async def get_video_status(video_id: str, db: Session = Depends(get_db)):
    """Get current transcoding progress and metadata of a video"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    from app.services.progress_tracker import progress_tracker

    resp_data = video.to_dict()
    if video.status == VideoStatus.PROCESSING:
        live = progress_tracker.get_progress(video.id)
        if live:
            resp_data["progress_percent"] = live["percent"]
            if live.get("message"):
                resp_data["status_message"] = live["message"]

    if video.status == VideoStatus.COMPLETED:
        resp_data["stream_info_url"] = f"{settings.base_prefix}/api/v1/videos/{video.id}/stream"

    return {
        "status": "success",
        "data": resp_data
    }

@router.get("/{video_id}/stream")
async def get_streaming_info(video_id: str, db: Session = Depends(get_db)):
    """
    Acquire a streaming session and get HLS / MP4 playback URLs.
    Enforces M=5 concurrent active streams.
    """
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    if video.status != VideoStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video is not ready for streaming yet. Current status: {video.status.value}"
        )

    # Acquire stream slot (M=5 constraint)
    try:
        session = await stream_manager.acquire_slot(video_id)
    except StreamSlotUnavailableException as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )

    # Increment view count
    video.view_count += 1
    db.commit()

    stream_status = stream_manager.get_status()

    return {
        "status": "success",
        "data": {
            "video_id": video.id,
            "title": video.title,
            "duration_seconds": video.duration_seconds,
            "session_id": session.session_id,
            "session_expires_in_seconds": settings.STREAM_SESSION_TIMEOUT_SECONDS,
            "streaming_urls": {
                "hls_master_url": f"{settings.base_prefix}/api/v1/streams/{video.id}/master.m3u8?session_id={session.session_id}",
                "mp4_range_url": f"{settings.base_prefix}/api/v1/streams/{video.id}/mp4?session_id={session.session_id}"
            },
            "active_streams": stream_status["active_stream_sessions"],
            "max_concurrent_streams": stream_status["max_concurrent_streams"],
            "available_slots": stream_status["available_slots"]
        }
    }

@router.get("")
async def list_videos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db)
):
    """List managed videos with pagination and status filter"""
    from app.services.progress_tracker import progress_tracker

    query = db.query(Video)
    if status_filter:
        query = query.filter(Video.status == status_filter.upper())
    
    total = query.count()
    videos = query.order_by(Video.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    items = []
    for v in videos:
        d = v.to_dict()
        if v.status == VideoStatus.PROCESSING:
            live = progress_tracker.get_progress(v.id)
            if live:
                d["progress_percent"] = live["percent"]
                if live.get("message"):
                    d["status_message"] = live["message"]
        items.append(d)

    return {
        "status": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1
        }
    }

@router.delete("/{video_id}")
async def delete_video(video_id: str):
    """Delete a video and all related transcoded / HLS media files immediately"""
    success = retention_service.delete_video(video_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found or already deleted.")
    
    return {
        "status": "success",
        "message": f"Video {video_id} and all related files deleted successfully."
    }
