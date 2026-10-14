"""FastAPI application: routers, CORS, static media, SSE, background jobs."""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.ai.embeddings import embedder_status, get_embedder
from app.config import get_settings
from app.db import SessionLocal
from app.events import broker
from app.logging_setup import setup_logging
from app.routers import admin, agent, clusters, dashboard, eval, locations, meta, reports, sse, tickets
from app.runtime import effective_llm_mode

log = logging.getLogger("snapfix")
settings = get_settings()
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


def _warm_embedder() -> None:
    try:
        get_embedder().embed(["warm up"])
    except Exception:  # pragma: no cover
        log.exception("embedder warm-up failed")


def _cluster_job() -> None:
    from app.ai.cluster import run_clustering

    try:
        with SessionLocal() as db:
            run_clustering(db)
    except Exception:  # never let the background job crash the app
        log.exception("clustering job failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging(settings.log_level)
    broker.bind_loop(asyncio.get_running_loop())
    threading.Thread(target=_warm_embedder, daemon=True).start()
    scheduler = None
    if settings.scheduler_enabled:
        from datetime import datetime, timedelta

        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(_cluster_job, "interval", seconds=settings.cluster_interval_s, id="clustering",
                          next_run_time=datetime.now() + timedelta(seconds=20), max_instances=1, coalesce=True)
        scheduler.start()
    log.info("snapfix backend started", extra={"llm_mode": effective_llm_mode()})
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="SnapFix API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted({settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"}),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=settings.upload_dir, check_dir=False), name="media")
app.include_router(tickets.router)
app.include_router(locations.router)
app.include_router(sse.router)
app.include_router(admin.router)
app.include_router(reports.router)
app.include_router(meta.router)
app.include_router(clusters.router)
app.include_router(dashboard.router)
app.include_router(agent.router)
app.include_router(eval.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    db_ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "llm_mode": effective_llm_mode(),
        "embedder": embedder_status(),
        "sse_subscribers": broker.subscriber_count,
        "version": app.version,
    }
