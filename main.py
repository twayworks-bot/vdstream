"""
VDSTREAM - Main Application Entrypoint
Exposes the FastAPI 'app' instance for Gunicorn/Uvicorn ASGI servers (main:app).
"""

import uvicorn
from app.main import app
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
