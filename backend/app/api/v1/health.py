from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_database_probe
from app.db.health import DatabaseProbe

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]


@router.get("/health")
async def health() -> HealthResponse:
    """Liveness: the process is running. Never checks dependencies, so an outage elsewhere
    doesn't make the orchestrator restart healthy API instances."""
    return HealthResponse(status="ok")


@router.get("/ready", responses={503: {"description": "A dependency is unavailable"}})
async def ready(probe: Annotated[DatabaseProbe, Depends(get_database_probe)]) -> ReadinessResponse:
    """Readiness: this instance can serve traffic. Load balancers stop routing to it on 503."""
    if not await probe.check():
        raise HTTPException(status_code=503, detail="The database is unavailable.")
    return ReadinessResponse(status="ready")
