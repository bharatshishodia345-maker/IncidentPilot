"""Top-level route composition."""

from fastapi import APIRouter

from app.api import actions, health, identity, incidents, integrations, intelligence, learning, room

api_router = APIRouter()
api_router.include_router(health.router)

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(identity.router)
v1_router.include_router(incidents.router)
v1_router.include_router(room.router)
v1_router.include_router(intelligence.router)
v1_router.include_router(actions.router)
v1_router.include_router(learning.router)
v1_router.include_router(integrations.router)

api_router.include_router(v1_router)
