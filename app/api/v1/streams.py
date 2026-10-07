import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request, status, Query
from fastapi.responses import FileResponse, StreamingResponse, Response
from app.config import settings
from app.services.stream_manager import stream_manager
from app.database import SessionLocal
from app.models.video import Video, VideoStatus

router = APIRouter()

def _validate_session_if_present(session_id: Optional[str], video_id: str):
    """If session_id is provided, verify it is still valid and active"""
    if session_id:
        if not stream_manager.is_session_valid(session_id, video_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Stream session is expired or invalid. Please re-acquire a streaming session."
            )

@router.get("/{video_id}/master.m3u8")
async def get_hls_master_playlist(
    video_id: str,
    session_id: Optional[str] = Query(None)
):
    """Serve HLS master playlist (.m3u8)"""
    _validate_session_if_present(session_id, video_id)

    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
        
        m3u8_path = Path(video.hls_dir_path) / "master.m3u8"
        if not m3u8_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HLS playlist not found.")

        # Read playlist and ensure segment URLs point to the API endpoint with session_id
        with open(m3u8_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Rewrite relative segment URLs if needed to append session_id
        if session_id:
            # Replace segment_XXX.ts with segment_XXX.ts?session_id=...
            content = re.sub(
                r"(segment_\d+\.ts)",
                rf"\1?session_id={session_id}",
                content
            )

        return Response(
            content=content,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache"}
        )
    finally:
        db.close()

@router.get("/{video_id}/mp4")
async def stream_mp4_range(
    video_id: str,
    request: Request,
    session_id: Optional[str] = Query(None)
):
    """
    Serve transcoded 720p MP4 with HTTP 206 Partial Content (Byte-Range support)
    for instant smooth seeking and streaming.
    """
    _validate_session_if_present(session_id, video_id)

    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

        if not video.transcoded_path or not os.path.exists(video.transcoded_path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcoded video file not found.")

        file_path = video.transcoded_path
        file_size = os.path.getsize(file_path)

        range_header = request.headers.get("range")
        if not range_header:
            # Full file response
            return FileResponse(
                file_path,
                media_type="video/mp4",
                headers={"Accept-Ranges": "bytes"}
            )

        # Parse range header: e.g. "bytes=0-1048575"
        range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not range_match:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid Range header")

        start = int(range_match.group(1))
        end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

        if start >= file_size or end >= file_size or start > end:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        content_length = (end - start) + 1

        def iter_file():
            with open(file_path, "rb") as f:
                f.seek(start)
                bytes_left = content_length
                chunk_size = 1024 * 512  # 512KB chunks
                while bytes_left > 0:
                    read_size = min(chunk_size, bytes_left)
                    data = f.read(read_size)
                    if not data:
                        break
                    bytes_left -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Cache-Control": "no-cache"
            }
        )
    finally:
        db.close()

@router.get("/{video_id}/{segment_name:path}")
async def get_hls_segment(
    video_id: str,
    segment_name: str,
    request: Request,
    session_id: Optional[str] = Query(None)
):
    """Serve individual HLS video TS segment or sub-playlist"""
    # Guard against accidental /mp4 or /master.m3u8 matching
    if segment_name == "mp4":
        return await stream_mp4_range(video_id=video_id, request=request, session_id=session_id)
    if segment_name == "master.m3u8":
        return await get_hls_master_playlist(video_id=video_id, session_id=session_id)

    _validate_session_if_present(session_id, video_id)

    # Sanitize segment_name to prevent directory traversal
    safe_name = os.path.basename(segment_name)
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

        target_file = Path(video.hls_dir_path) / safe_name
        if not target_file.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment file not found.")

        media_type = "video/MP2T" if safe_name.endswith(".ts") else "application/vnd.apple.mpegurl"
        return FileResponse(
            str(target_file),
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=3600"}
        )
    finally:
        db.close()

@router.post("/{session_id}/heartbeat")
async def stream_heartbeat(session_id: str):
    """Keep active stream session alive (heartbeat every 15s)"""
    success = await stream_manager.heartbeat(session_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or has timed out."
        )
    return {
        "status": "success",
        "message": "Heartbeat updated successfully",
        "session_id": session_id
    }

@router.post("/{session_id}/release")
async def release_stream_session(session_id: str):
    """Release streaming slot when client leaves or stops playback"""
    success = await stream_manager.release_slot(session_id)
    return {
        "status": "success",
        "message": "Session slot released successfully" if success else "Session not found or already released",
        "session_id": session_id
    }
