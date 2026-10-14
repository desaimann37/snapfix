"""Evaluation results for /eval, plus time-to-report measurements (legacy form vs SnapFix)."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import TimingRun

router = APIRouter(prefix="/api/eval", tags=["eval"])


def _result_files() -> list[Path]:
    d = Path(get_settings().eval_results_dir)
    return sorted(d.glob("*.json"), key=lambda p: p.name, reverse=True) if d.exists() else []


def timing_stats(db: Session) -> dict:
    out = {}
    for flow in ("baseline", "snapfix"):
        values = sorted(r.seconds for r in db.scalars(select(TimingRun).where(TimingRun.flow == flow)))
        out[flow] = {
            "n": len(values),
            "median_s": round(median(values), 1) if values else None,
            "min_s": values[0] if values else None,
            "max_s": values[-1] if values else None,
            "values": values[-50:],
        }
    b, s = out["baseline"]["median_s"], out["snapfix"]["median_s"]
    out["speedup"] = round(b / s, 1) if b and s else None
    return out


@router.get("/latest")
def latest(db: Session = Depends(get_db)) -> dict:
    files = _result_files()
    result = json.loads(files[0].read_text(encoding="utf-8")) if files else None
    return {"result": result, "timing": timing_stats(db), "runs": len(files)}


@router.get("/runs")
def runs() -> list[dict]:
    out = []
    for p in _result_files()[:20]:
        r = json.loads(p.read_text(encoding="utf-8"))
        out.append({"run_id": r["run_id"], "mode": r["mode"], "timestamp": r["timestamp"], "n_items": r["n_items"],
                    "category_accuracy": r["metrics"]["category_accuracy"],
                    "hazard_recall": r["metrics"]["hazard_recall"]})
    return out


class TimingIn(BaseModel):
    flow: str = Field(pattern="^(baseline|snapfix)$")
    seconds: float = Field(gt=0, le=3600)
    participant: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)


@router.post("/timing")
def add_timing(body: TimingIn, db: Session = Depends(get_db)) -> dict:
    run = TimingRun(flow=body.flow, seconds=round(body.seconds, 2), participant=body.participant, notes=body.notes)
    db.add(run)
    db.commit()
    return {"ok": True, "timing": timing_stats(db)}


@router.delete("/timing")
def clear_timing(confirm: bool = False, db: Session = Depends(get_db)) -> dict:
    if not confirm:
        raise HTTPException(400, "Pass confirm=true to delete all timing measurements")
    for run in db.scalars(select(TimingRun)):
        db.delete(run)
    db.commit()
    return {"ok": True}
