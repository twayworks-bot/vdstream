import os
import shutil
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from app.config import settings
from app.database import SessionLocal
from app.models.video import Video, VideoStatus

logger = logging.getLogger("vdstream.retention")

class RetentionService:
    def __init__(self):
        self.is_running: bool = False
        self._task: asyncio.Task = None

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._retention_loop())
        logger.info(
            f"RetentionService started. Policy: {settings.RETENTION_DAYS} days. "
            f"Check interval: {settings.CLEANUP_INTERVAL_HOURS} hours."
        )

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def purge_expired_videos(self) -> int:
        """Find videos where expires_at <= now and remove files and DB records"""
        db = SessionLocal()
        purged_count = 0
        try:
            now = datetime.now(timezone.utc)
            expired_videos: List[Video] = db.query(Video).filter(Video.expires_at <= now).all()
            for v in expired_videos:
                logger.info(f"Purging expired video: {v.id} (expired at {v.expires_at})")
                self._delete_media_files(v)
                db.delete(v)
                purged_count += 1
            db.commit()
            if purged_count > 0:
                logger.info(f"Purged {purged_count} expired videos from storage and database.")
        except Exception as e:
            logger.error(f"Error purging expired videos: {e}")
            db.rollback()
        finally:
            db.close()
        return purged_count

    def delete_video(self, video_id: str) -> bool:
        """Manually delete a specific video and all related assets"""
        db = SessionLocal()
        try:
            video: Video = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                return False
            self._delete_media_files(video)
            db.delete(video)
            db.commit()
            logger.info(f"Video {video_id} and all related files deleted successfully.")
            return True
        except Exception as e:
            logger.error(f"Error deleting video {video_id}: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def _delete_media_files(self, video: Video):
        """Safely delete uploaded, transcoded and HLS files/directories"""
        # 1. Delete upload source
        if video.stored_upload_path and os.path.exists(video.stored_upload_path):
            try:
                os.remove(video.stored_upload_path)
            except OSError as e:
                logger.warning(f"Could not remove upload file {video.stored_upload_path}: {e}")

        # 2. Delete transcoded MP4
        if video.transcoded_path and os.path.exists(video.transcoded_path):
            try:
                os.remove(video.transcoded_path)
            except OSError as e:
                logger.warning(f"Could not remove transcoded file {video.transcoded_path}: {e}")

        # 3. Delete HLS directory
        if video.hls_dir_path and os.path.exists(video.hls_dir_path):
            try:
                shutil.rmtree(video.hls_dir_path, ignore_errors=True)
            except OSError as e:
                logger.warning(f"Could not remove HLS directory {video.hls_dir_path}: {e}")

    async def _retention_loop(self):
        while self.is_running:
            try:
                # Run purge check
                self.purge_expired_videos()
                # Sleep interval
                sleep_seconds = max(60, settings.CLEANUP_INTERVAL_HOURS * 3600)
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Retention loop error: {e}")
                await asyncio.sleep(60)

retention_service = RetentionService()
