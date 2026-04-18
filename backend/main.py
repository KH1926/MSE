from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

try:
    from api.orders import router as orders_router
    from api.query import router as query_router
    from api.schedule import router as schedule_router
    from api.simulation import router as simulation_router
    from db import DB_PATH, init_db
except ModuleNotFoundError:
    from .api.orders import router as orders_router
    from .api.query import router as query_router
    from .api.schedule import router as schedule_router
    from .api.simulation import router as simulation_router
    from .db import DB_PATH, init_db

app = FastAPI(title="生产管理后端服务", version="0.1.0")


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
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"internal error: {exc}", "data": None},
    )


app.include_router(query_router)
app.include_router(orders_router)
app.include_router(schedule_router)
app.include_router(simulation_router)
