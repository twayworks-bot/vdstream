import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import io
import os
import shutil
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, SessionLocal, engine, Base
from app.config import settings

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    settings.ensure_directories()
    init_db()
    yield

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def dummy_video_file():
    # Create a small dummy video content buffer
    content = b"TEST_VIDEO_PAYLOAD_VDSTREAM_SAMPLE_BYTES" * 100
    return io.BytesIO(content)
