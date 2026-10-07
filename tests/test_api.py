import time
import pytest
from app.models.video import Video, VideoStatus
from app.database import SessionLocal
from app.config import settings

def test_root_and_prefix_redirects(client):
    p = settings.base_prefix
    # GET / should redirect to /{DEFAULT_PREFIX}/dashboard
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in [302, 307]
    assert resp.headers["location"] == f"{p}/dashboard"

    # GET /{DEFAULT_PREFIX} should also redirect
    if p:
        resp_p = client.get(p, follow_redirects=False)
        assert resp_p.status_code in [302, 307]
        assert resp_p.headers["location"] == f"{p}/dashboard"

def test_system_status_api(client):
    p = settings.base_prefix
    response = client.get(f"{p}/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "transcoding" in data["data"]
    assert "streaming" in data["data"]
    assert data["data"]["streaming"]["max_concurrent_streams"] == 5

def test_container_healthcheck_api(client):
    p = settings.base_prefix
    # Root /api/status test
    resp_root = client.get("/api/status")
    assert resp_root.status_code == 200
    data_root = resp_root.json()
    assert data_root["status"] == "healthy"
    assert data_root["service"] == "vdstream"

    # Prefix /{base_prefix}/api/status test (used by Docker HEALTHCHECK)
    if p:
        resp_prefix = client.get(f"{p}/api/status")
        assert resp_prefix.status_code == 200
        data_prefix = resp_prefix.json()
        assert data_prefix["status"] == "healthy"
        assert data_prefix["service"] == "vdstream"


def test_video_upload_and_status(client, dummy_video_file):
    p = settings.base_prefix
    # Upload video
    files = {"file": ("test_clip.mp4", dummy_video_file, "video/mp4")}
    data = {"title": "Test Integration Video"}
    response = client.post(f"{p}/api/v1/videos/upload", files=files, data=data)
    assert response.status_code == 202
    res_json = response.json()
    assert res_json["status"] == "success"
    video_id = res_json["data"]["video_id"]
    assert video_id.startswith("vid_")
    assert res_json["data"]["status_url"].startswith(f"{p}/api/v1/videos/")

    # Get status
    time.sleep(1) # wait briefly for worker
    status_resp = client.get(f"{p}/api/v1/videos/{video_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()["data"]
    assert status_data["video_id"] == video_id
    assert status_data["title"] == "Test Integration Video"
    assert status_data["status"] in ["QUEUED", "PROCESSING", "COMPLETED"]

def test_list_videos(client):
    p = settings.base_prefix
    response = client.get(f"{p}/api/v1/videos?limit=10")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 1

def test_delete_video(client, dummy_video_file):
    p = settings.base_prefix
    # Upload first
    files = {"file": ("to_delete.mp4", dummy_video_file, "video/mp4")}
    upload_res = client.post(f"{p}/api/v1/videos/upload", files=files, data={"title": "Delete Me"})
    vid_id = upload_res.json()["data"]["video_id"]

    # Delete
    del_res = client.delete(f"{p}/api/v1/videos/{vid_id}")
    assert del_res.status_code == 200

    # Verify 404
    chk_res = client.get(f"{p}/api/v1/videos/{vid_id}/status")
    assert chk_res.status_code == 404
