from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

try:
    from api.order_api import router as orders_router
    from api.query_api import router as query_router
    from api.schedule_api import router as schedule_router
    from api.simulation_api import router as simulation_router
    from db import DB_PATH, init_db
    from integration.security import (
        configured_api_key,
        get_cors_origins,
        require_api_key,
        should_show_debug_errors,
    )
except ModuleNotFoundError:
    from .api.order_api import router as orders_router
    from .api.query_api import router as query_router
    from .api.schedule_api import router as schedule_router
    from .api.simulation_api import router as simulation_router
    from .db import DB_PATH, init_db
    from .integration.security import (
        configured_api_key,
        get_cors_origins,
        require_api_key,
        should_show_debug_errors,
    )

logger = logging.getLogger(__name__)

app = FastAPI(title="生产管理后端服务", version="0.1.0")

cors_origins = get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    public_paths = {"/docs", "/openapi.json", "/docs/oauth2-redirect", "/redoc"}
    if request.url.path in public_paths or not configured_api_key():
        return await call_next(request)

    try:
        await require_api_key(request.headers.get("X-API-Key"))
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": str(exc.detail), "data": None},
        )
    return await call_next(request)


@app.on_event("startup")
def startup_event() -> None:
    if not DB_PATH.exists():
        init_db()


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled backend exception")
    message = f"internal error: {exc}" if should_show_debug_errors() else "服务器内部错误"
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": message, "data": None},
    )


app.include_router(query_router)
app.include_router(orders_router)
app.include_router(schedule_router)
app.include_router(simulation_router)
