#!/usr/bin/env python3
import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="FaultCore Test HTTP Server")

request_count = {"total": 0, "by_endpoint": {}}


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
    request_count["total"] += 1
    endpoint = str(request.url.path)
    request_count["by_endpoint"][endpoint] = request_count["by_endpoint"].get(endpoint, 0) + 1

    print(f"[{datetime.now().isoformat()}] {request.method} {endpoint}")
    response = await call_next(request)
    return response


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "FaultCore Test Server", "version": "1.0.0", "timestamp": datetime.now().isoformat()}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/echo/{msg}")
async def echo(msg: str) -> dict[str, str]:
    return {"message": msg, "timestamp": datetime.now().isoformat()}


@app.get("/delay/{seconds}")
async def delay(seconds: int) -> dict[str, str | int]:
    if seconds > 60:
        raise HTTPException(status_code=400, detail="Maximum delay is 60 seconds")

    await asyncio.sleep(seconds)
    return {"delayed": seconds, "timestamp": datetime.now().isoformat()}


@app.post("/upload")
async def upload(data: dict[str, Any]) -> dict[str, Any]:
    return {"received": len(str(data)), "data": data, "timestamp": datetime.now().isoformat()}


@app.get("/stats")
async def stats() -> dict[str, Any]:
    return request_count


@app.get("/slow")
async def slow() -> dict[str, str]:
    await asyncio.sleep(5)
    return {"message": "This was a slow response", "timestamp": datetime.now().isoformat()}


@app.get("/chunked/{size}")
async def chunked(size: int) -> dict[str, str | int]:
    if size > 1024 * 1024:
        raise HTTPException(status_code=400, detail="Maximum size is 1MB")

    data = "x" * size
    return {"data": data, "size": size, "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
