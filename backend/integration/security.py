from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def configured_api_key() -> str:
    return os.getenv("MES_API_KEY", "").strip()


def get_cors_origins() -> list[str]:
    raw_origins = os.getenv(
        "MES_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:3000"]


def should_show_debug_errors() -> bool:
    return os.getenv("MES_DEBUG_ERRORS", "").strip().lower() in {"1", "true", "yes"}


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    api_key = configured_api_key()
    if not api_key:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, api_key):
        raise HTTPException(status_code=401, detail="未授权：缺少或错误的 X-API-Key")
