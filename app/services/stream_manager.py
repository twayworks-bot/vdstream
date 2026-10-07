import time
import uuid
import asyncio
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("vdstream.stream_manager")

class StreamSlotUnavailableException(Exception):
    pass

class StreamSession:
    def __init__(self, session_id: str, video_id: str):
        self.session_id: str = session_id
        self.video_id: str = video_id
        self.created_at: float = time.time()
        self.last_heartbeat: float = time.time()

    def update_heartbeat(self):
        self.last_heartbeat = time.time()

    def is_expired(self, timeout_seconds: int) -> bool:
        return (time.time() - self.last_heartbeat) > timeout_seconds

class StreamManager:
    def __init__(self):
        self._sessions: Dict[str, StreamSession] = {}
        self._lock = asyncio.Lock()
        self.is_running: bool = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"StreamManager started with max concurrent streams M={settings.MAX_CONCURRENT_STREAMS}")

    async def stop(self):
        self.is_running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self._sessions.clear()

    async def acquire_slot(self, video_id: str) -> StreamSession:
        """Acquire a streaming session slot. Enforces M=5 limit."""
        async with self._lock:
            # Purge expired sessions first
            self._purge_expired_sessions_sync()

            if len(self._sessions) >= settings.MAX_CONCURRENT_STREAMS:
                raise StreamSlotUnavailableException(
                    f"Maximum concurrent streams limit reached ({settings.MAX_CONCURRENT_STREAMS} active streams). "
                    "Please wait for an active stream to finish."
                )

            session_id = f"sess_{uuid.uuid4().hex[:16]}"
            session = StreamSession(session_id=session_id, video_id=video_id)
            self._sessions[session_id] = session
            logger.info(
                f"Stream session {session_id} acquired for video {video_id}. "
                f"Active streams: {len(self._sessions)}/{settings.MAX_CONCURRENT_STREAMS}"
            )
            return session

    async def heartbeat(self, session_id: str) -> bool:
        """Update last heartbeat timestamp for an active session"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            if session.is_expired(settings.STREAM_SESSION_TIMEOUT_SECONDS):
                del self._sessions[session_id]
                return False
            session.update_heartbeat()
            return True

    async def release_slot(self, session_id: str) -> bool:
        """Release session slot explicitly"""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(
                    f"Stream session {session_id} released. "
                    f"Active streams: {len(self._sessions)}/{settings.MAX_CONCURRENT_STREAMS}"
                )
                return True
            return False

    def is_session_valid(self, session_id: str, video_id: Optional[str] = None) -> bool:
        """Check if a session ID is currently active and valid"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        if session.is_expired(settings.STREAM_SESSION_TIMEOUT_SECONDS):
            return False
        if video_id and session.video_id != video_id:
            return False
        return True

    def get_status(self) -> Dict[str, Any]:
        self._purge_expired_sessions_sync()
        active_count = len(self._sessions)
        return {
            "active_stream_sessions": active_count,
            "max_concurrent_streams": settings.MAX_CONCURRENT_STREAMS,
            "available_slots": max(0, settings.MAX_CONCURRENT_STREAMS - active_count),
            "session_timeout_seconds": settings.STREAM_SESSION_TIMEOUT_SECONDS
        }

    def _purge_expired_sessions_sync(self):
        expired = [
            sid for sid, s in self._sessions.items()
            if s.is_expired(settings.STREAM_SESSION_TIMEOUT_SECONDS)
        ]
        for sid in expired:
            del self._sessions[sid]
            logger.info(f"Stream session {sid} expired and purged due to inactivity.")

    async def _cleanup_loop(self):
        while self.is_running:
            try:
                await asyncio.sleep(5)
                async with self._lock:
                    self._purge_expired_sessions_sync()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in stream session cleanup loop: {e}")

stream_manager = StreamManager()
