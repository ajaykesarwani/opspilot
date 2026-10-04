from fastapi import APIRouter
from fastapi.responses import JSONResponse

from opspilot_api.deps import RepositoryDep, SettingsDep

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(settings: SettingsDep) -> dict[str, str]:
    """Liveness: the process is up. Deliberately does not touch the database."""
    return {"status": "ok", "service": settings.service_name}


@router.get("/readyz")
def readyz(repository: RepositoryDep) -> JSONResponse:
    """Readiness: dependencies are reachable (currently PostgreSQL)."""
    checks = {"database": "ok" if repository.ping() else "unavailable"}
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
