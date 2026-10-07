"""
VDSTREAM - Transcoding Progress Tracker
Maintains live, thread-safe transcoding progress percentages (0.0% ~ 100.0%) for active video jobs.
"""

import time
import threading
from typing import Dict, Any, Optional

class ProgressTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}

    def set_progress(
        self,
        video_id: str,
        percent: float,
        message: Optional[str] = None,
        stage: Optional[str] = None
    ):
        with self._lock:
            current = self._data.get(video_id, {})
            # Ensure progress does not decrease (monotonic increase)
            prev_pct = current.get("percent", 0.0)
            clamped_pct = max(prev_pct, min(100.0, float(percent)))
            
            self._data[video_id] = {
                "percent": round(clamped_pct, 1),
                "message": message or current.get("message", "Processing..."),
                "stage": stage or current.get("stage", "transcoding"),
                "updated_at": time.time()
            }

    def get_progress(self, video_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            val = self._data.get(video_id)
            if val:
                return dict(val)
            return None

    def remove(self, video_id: str):
        with self._lock:
            self._data.pop(video_id, None)

progress_tracker = ProgressTracker()
