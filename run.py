import uvicorn
from app.config import settings

if __name__ == "__main__":
    prefix = settings.base_prefix
    print("=" * 60)
    print(" VDSTREAM - 720p Video Transcoding & Instant Streaming Platform")
    print(f" Web Dashboard: http://localhost:{settings.PORT}{prefix}/dashboard")
    print(f" REST API Docs: http://localhost:{settings.PORT}{prefix}/docs")
    print(f" API Base Path: http://localhost:{settings.PORT}{prefix}/api/v1")
    print(f" API Spec File: vdstream-api.md")
    print("=" * 60)
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False
    )
