import pytest
import asyncio
from app.services.queue_manager import queue_manager, QueueFullException
from app.config import settings

@pytest.mark.asyncio
async def test_queue_overflow_protection():
    # Save original queue maxsize
    temp_queue = asyncio.Queue(maxsize=3)
    orig_queue = queue_manager.queue
    queue_manager.queue = temp_queue

    try:
        # Fill 3 items
        await queue_manager.enqueue("vid_1")
        await queue_manager.enqueue("vid_2")
        await queue_manager.enqueue("vid_3")

        # 4th item should raise QueueFullException
        with pytest.raises(QueueFullException):
            await queue_manager.enqueue("vid_4")
    finally:
        queue_manager.queue = orig_queue

def test_dashboard_access(client):
    p = settings.base_prefix
    response = client.get(f"{p}/dashboard")
    assert response.status_code == 200
    assert "VDSTREAM" in response.text
    assert "트랜스코딩 진행" in response.text
