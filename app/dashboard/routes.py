from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings, BASE_DIR
from app.database import get_db
from app.models.video import Video
from app.services.queue_manager import queue_manager
from app.services.stream_manager import stream_manager
from app.services.ffmpeg_service import ffmpeg_service

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request, db: Session = Depends(get_db)):
    """Render main web dashboard for video management and instant streaming"""
    videos = db.query(Video).order_by(Video.created_at.desc()).all()
    q_status = queue_manager.get_status()
    s_status = stream_manager.get_status()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "videos": [v.to_dict() for v in videos],
            "transcoding_status": q_status,
            "streaming_status": s_status,
            "settings": settings,
            "base_prefix": settings.base_prefix,
            "ffmpeg_available": ffmpeg_service.available
        }
    )
