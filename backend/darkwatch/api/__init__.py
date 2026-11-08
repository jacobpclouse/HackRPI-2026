"""FastAPI app factory: routers first, the static frontend mounted last."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from darkwatch import __version__, paths
from darkwatch.ais import refresh as ais_refresh
from darkwatch.api import coverage, evidence, health, media, orbits, scene, ships, validation


async def _http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        {"error": str(exc.detail), "detail": exc.detail, "status": exc.status_code, "path": request.url.path},
        status_code=exc.status_code,
    )


async def _validation_error(request: Request, exc: RequestValidationError):
    problems = []
    for err in exc.errors():
        where = ".".join(str(part) for part in err.get("loc", ()) if part not in ("query", "path", "body"))
        problems.append(f"{where}: {err.get('msg')}" if where else str(err.get("msg")))
    message = "Invalid request. " + "; ".join(problems)
    return JSONResponse(
        {"error": message, "detail": message, "status": 400, "path": request.url.path},
        status_code=400,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    ais_refresh.start()
    try:
        yield
    finally:
        await ais_refresh.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="DarkWatch", version=__version__, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=800)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    for module in (health, orbits, coverage, scene, media, validation, evidence, ships):
        app.include_router(module.router)
    evidence_dir = paths.evidence_dir()
    if evidence_dir.is_dir():
        app.mount("/evidence", StaticFiles(directory=str(evidence_dir)), name="evidence")
    # Last, so every /api/* route wins over a same-named static file.
    app.mount("/", StaticFiles(directory=str(paths.frontend_dir()), html=True), name="ui")
    return app
