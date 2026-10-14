"""Server-Sent Events stream for live dashboards."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.events import broker

router = APIRouter(prefix="/api", tags=["realtime"])

KEEPALIVE_S = 15


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    queue = broker.subscribe()

    async def events():
        try:
            yield "retry: 3000\n\n"
            yield f"event: hello\ndata: {json.dumps({'subscribers': broker.subscriber_count})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                data = json.dumps(msg["data"], default=str)
                yield f"id: {msg['id']}\nevent: {msg['event']}\ndata: {data}\n\n"
        finally:
            broker.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)
