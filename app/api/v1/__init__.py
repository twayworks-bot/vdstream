from fastapi import APIRouter
from app.api.v1.videos import router as videos_router
from app.api.v1.streams import router as streams_router
from app.api.v1.system import router as system_router

api_v1_router = APIRouter()
api_v1_router.include_router(videos_router, prefix="/videos", tags=["Videos"])
api_v1_router.include_router(streams_router, prefix="/streams", tags=["Streams"])
api_v1_router.include_router(system_router, prefix="/system", tags=["System"])
