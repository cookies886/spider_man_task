from fastapi import APIRouter

from app.ws.client import router as client_ws_router
from app.ws.worker import router as worker_ws_router

ws_router = APIRouter()
ws_router.include_router(worker_ws_router)
ws_router.include_router(client_ws_router)
