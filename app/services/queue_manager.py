import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.config import settings
from app.database import SessionLocal
from app.models.video import Video, VideoStatus
from app.services.ffmpeg_service import ffmpeg_service, VideoDurationExceededError, VideoSizeExceededError, FFmpegError

logger = logging.getLogger("vdstream.queue")

class QueueFullException(Exception):
    pass

class QueueManager:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=settings.MAX_QUEUE_SIZE)
        self.active_workers: int = 0
        self.workers: list = []
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TRANSCODE)
        self.is_running: bool = False

    async def start(self):
        """Start background worker tasks"""
        if self.is_running:
            return
        self.is_running = True
        logger.info(
            f"Starting QueueManager with N={settings.MAX_CONCURRENT_TRANSCODE} concurrent workers "
            f"and Queue capacity={settings.MAX_QUEUE_SIZE}"
        )
        for i in range(settings.MAX_CONCURRENT_TRANSCODE):
            task = asyncio.create_task(self._worker_loop(i + 1))
            self.workers.append(task)
        
        # Recover pending tasks from DB
        await self._recover_pending_tasks()

    async def stop(self):
        """Stop background worker tasks"""
        self.is_running = False
        for task in self.workers:
            task.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        logger.info("QueueManager workers stopped.")

    async def enqueue(self, video_id: str) -> int:
        """Enqueue video for transcoding. Returns current queue size."""
        if self.queue.full():
            raise QueueFullException(
                f"Transcoding queue is full (max {settings.MAX_QUEUE_SIZE} tasks). Please retry later."
            )
        await self.queue.put(video_id)
        current_size = self.queue.qsize()
        logger.info(f"Video {video_id} enqueued. Current queue size: {current_size}")
        return current_size

    def get_status(self) -> Dict[str, Any]:
        return {
            "active_transcoding_count": self.active_workers,
            "max_concurrent_transcode": settings.MAX_CONCURRENT_TRANSCODE,
            "queued_count": self.queue.qsize(),
            "max_queue_size": settings.MAX_QUEUE_SIZE
        }

    async def _recover_pending_tasks(self):
        """Recover QUEUED or interrupted PROCESSING tasks on application startup"""
        db = SessionLocal()
        try:
            pending = db.query(Video).filter(
                Video.status.in_([VideoStatus.QUEUED, VideoStatus.PROCESSING])
            ).all()
            for v in pending:
                if not self.queue.full():
                    v.status = VideoStatus.QUEUED
                    v.status_message = "Recovered after server restart. Waiting in queue."
                    await self.queue.put(v.id)
                    logger.info(f"Recovered pending video {v.id} into queue.")
            db.commit()
        except Exception as e:
            logger.error(f"Error during pending tasks recovery: {e}")
        finally:
            db.close()

    async def _worker_loop(self, worker_id: int):
        logger.info(f"Worker-{worker_id} started.")
        while self.is_running:
            try:
                video_id = await self.queue.get()
            except asyncio.CancelledError:
                break

            async with self._semaphore:
                self.active_workers += 1
                try:
                    logger.info(f"Worker-{worker_id} started processing video {video_id}")
                    await self._process_video(video_id)
                except Exception as e:
                    logger.error(f"Worker-{worker_id} encountered unexpected error for video {video_id}: {e}")
                finally:
                    self.active_workers -= 1
                    self.queue.task_done()

    async def _process_video(self, video_id: str):
        db = SessionLocal()
        try:
            video: Optional[Video] = db.query(Video).filter(Video.id == video_id).first()
            if not video:
                logger.warning(f"Video {video_id} not found in database during processing.")
                return

            video.status = VideoStatus.PROCESSING
            video.status_message = "Transcoding to 720p H.264 and generating HLS segments..."
            video.progress_percent = 5.0
            video.updated_at = datetime.now(timezone.utc)
            db.commit()

            from app.services.progress_tracker import progress_tracker
            progress_tracker.set_progress(video_id, 5.0, "트랜스코딩 준비 중...", stage="processing")

            # Progress callback for worker thread
            last_db_pct = [5.0]
            def on_progress(pct: float, msg: str):
                progress_tracker.set_progress(video_id, pct, msg)
                # Commit to DB periodically if percentage changed by >= 10%
                if pct - last_db_pct[0] >= 10.0 or pct >= 99.0:
                    last_db_pct[0] = pct
                    try:
                        sync_db = SessionLocal()
                        v = sync_db.query(Video).filter(Video.id == video_id).first()
                        if v and v.status == VideoStatus.PROCESSING:
                            v.progress_percent = round(pct, 1)
                            v.status_message = msg
                            v.updated_at = datetime.now(timezone.utc)
                            sync_db.commit()
                        sync_db.close()
                    except Exception:
                        pass

            # Execute FFmpeg transcoding in thread pool to avoid blocking asyncio event loop
            loop = asyncio.get_running_loop()
            probe, mp4_path, hls_master = await loop.run_in_executor(
                None,
                ffmpeg_service.transcode_to_720p_and_hls,
                video.stored_upload_path,
                video.transcoded_path,
                video.hls_dir_path,
                video.id,
                on_progress
            )

            # Update video record on success
            video.status = VideoStatus.COMPLETED
            video.status_message = "Transcoding completed successfully. Ready for instant streaming."
            video.progress_percent = 100.0
            video.duration_seconds = probe.get("duration")
            video.width = probe.get("width")
            video.height = probe.get("height")
            video.file_size_bytes = probe.get("final_size_bytes", 0)
            video.hls_playlist_path = hls_master
            video.updated_at = datetime.now(timezone.utc)
            db.commit()
            progress_tracker.set_progress(video_id, 100.0, "완료", stage="completed")
            logger.info(f"Video {video_id} successfully transcoded and ready.")

        except VideoDurationExceededError as e:
            logger.warning(f"Video {video_id} failed duration constraint: {e}")
            video.status = VideoStatus.FAILED
            video.status_message = str(e)
            video.progress_percent = 0.0
            video.updated_at = datetime.now(timezone.utc)
            db.commit()
            from app.services.progress_tracker import progress_tracker
            progress_tracker.set_progress(video_id, 0.0, str(e), stage="failed")
        except VideoSizeExceededError as e:
            logger.warning(f"Video {video_id} failed size constraint: {e}")
            video.status = VideoStatus.FAILED
            video.status_message = str(e)
            video.progress_percent = 0.0
            video.updated_at = datetime.now(timezone.utc)
            db.commit()
            from app.services.progress_tracker import progress_tracker
            progress_tracker.set_progress(video_id, 0.0, str(e), stage="failed")
        except Exception as e:
            logger.error(f"Video {video_id} transcoding failed: {e}")
            video.status = VideoStatus.FAILED
            video.status_message = f"Transcoding failed: {str(e)}"
            video.progress_percent = 0.0
            video.updated_at = datetime.now(timezone.utc)
            db.commit()
            from app.services.progress_tracker import progress_tracker
            progress_tracker.set_progress(video_id, 0.0, str(e), stage="failed")
        finally:
            db.close()

queue_manager = QueueManager()
