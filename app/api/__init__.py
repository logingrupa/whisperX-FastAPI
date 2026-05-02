"""API layer - FastAPI routers and HTTP concerns."""

from app.api.audio_api import stt_router
from app.api.audio_services_api import service_router
from app.api.task_api import task_router
from app.api.websocket_api import websocket_router

# Phase 13 routers — registered unconditionally in app/main.py post Phase 19.
from app.api.auth_routes import auth_router
from app.api.key_routes import key_router
from app.api.account_routes import account_router
from app.api.billing_routes import billing_router
from app.api.billing_webhook_routes import billing_webhook_router
from app.api.ws_ticket_routes import ws_ticket_router

__all__ = [
    "stt_router",
    "service_router",
    "task_router",
    "websocket_router",
    "auth_router",
    "key_router",
    "account_router",
    "billing_router",
    "billing_webhook_router",
    "ws_ticket_router",
]
