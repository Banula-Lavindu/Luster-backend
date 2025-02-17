from fastapi import FastAPI, Request

from fastapi_app.routers.task import task

from .routers.gem import AddGem
from .routers.chat import chat, websocket_chat
from .routers import auth, UserProfile
from .routers.Dealers import Dealer_qr, dealers
from .database import Base, engine
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.staticfiles import StaticFiles
from .routers.notifications import notification_router
from .routers.gem.gem_qr_router import router as gem_qr_router
from .routers.gem.gem_share_router import router as gem_share_router
from .routers.Trade.deal_router import router as deal_router
from .routers.Trade.external_trade import router as external_trade_router
from .routers.calls.call_router import router as call_router
from .routers.calls.call_websocket import router as call_websocket_router
from .databases.init_indexes import setup_indexes
from fastapi_app.config import settings
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the database tables if they don't exist
Base.metadata.create_all(bind=engine)

# Ensure the uploads directory exists
os.makedirs("uploads/profile_images", exist_ok=True)
os.makedirs("uploads/cover_images", exist_ok=True)
os.makedirs("uploads/gem_images", exist_ok=True)
os.makedirs("uploads/qrcodes", exist_ok=True)
os.makedirs("uploads/dealer_images", exist_ok=True)
os.makedirs("uploads/chat_attachments", exist_ok=True)
os.makedirs("uploads/group_images", exist_ok=True)

app = FastAPI()

# Mount static file serving
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Add CORS middleware with specific origins
origins = [
    "http://localhost:3000",    # React default port
    "http://localhost:8000",    # FastAPI default port
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
    "*"                         # Remove this in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Add WebSocket-specific middleware
@app.middleware("http")
async def websocket_middleware(request: Request, call_next):
    if request.headers.get("upgrade", "").lower() == "websocket":
        # Don't validate CORS for WebSocket connections
        return await call_next(request)
    response = await call_next(request)
    return response

# Include routers
app.include_router(task.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(UserProfile.router)
app.include_router(AddGem.router)
app.include_router(Dealer_qr.router)
app.include_router(dealers.router)
app.include_router(websocket_chat.router)
app.include_router(notification_router.router)
app.include_router(gem_qr_router)
app.include_router(gem_share_router)
app.include_router(deal_router)

app.include_router(external_trade_router)
app.include_router(call_router)
app.include_router(call_websocket_router)

#uvicorn fastapi_app.main:app --reload --port 8001
