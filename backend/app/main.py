import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.core.config import CORS_ALLOW_ORIGINS
from app.database.database import Base, engine
from app.devices.routes import router as devices_router
from app.issues.routes import router as issues_router
from app.websocket.device import router as device_ws_router
from app.websocket.map import router as map_ws_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("urban_pulse")

app = FastAPI(title="Urban Pulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    logger.info("Urban Pulse starting up — creating database tables if needed")
    Base.metadata.create_all(bind=engine)
    logger.info("Urban Pulse startup complete")


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(devices_router)
app.include_router(issues_router)
app.include_router(device_ws_router)
app.include_router(map_ws_router)
