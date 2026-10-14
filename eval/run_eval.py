"""SnapFix evaluation harness.

    cd backend && uv run python ../eval/run_eval.py          # live if ANTHROPIC_API_KEY is set, else mock
    cd backend && uv run python ../eval/run_eval.py --mock   # deterministic keyword baseline only

Runs every item in eval/dataset/labels.csv through the REAL intake pipeline (extraction, hazard rules, location
resolution, duplicate detection, routing) against an isolated, freshly seeded SQLite database, so the demo
database is never touched. Writes eval/results/<timestamp>.json (read by /eval) and a markdown summary.

Exit code 1 if hazard recall is below 100% (safety must never regress).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
REPO = EVAL_DIR.parent
sys.path.insert(0, str(REPO / "backend"))


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SnapFix evaluation")
    parser.add_argument("--mock", action="store_true", help="force mock mode (no API calls)")
    parser.add_argument("--limit", type=int, default=0, help="only the first N items")
    parser.add_argument("--labels", default=str(EVAL_DIR / "dataset" / "labels.csv"))
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    tmp = tempfile.mkdtemp(prefix="snapfix-eval-")
    os.environ.update({
        "DATABASE_URL": f"sqlite+pysqlite:///{Path(tmp, 'eval.db').as_posix()}",
        "UPLOAD_DIR": str(Path(tmp, "uploads")),
        "BACKGROUND_JOBS": "false",
        "SCHEDULER_ENABLED": "false",
        "NOTIFIER": "console",
    })
    os.environ.setdefault("EVAL_RESULTS_DIR", str(EVAL_DIR / "results"))
    if args.mock:
        os.environ["LLM_MODE"] = "mock"

    import logging

    logging.basicConfig(level=logging.WARNING)
    from app import pipeline, taxonomy
    from app.ai.embeddings import get_embedder
    from app.ai.extract import PROMPT_VERSION, mock_extract
    from app.config import get_settings
    from app.db import SessionLocal, init_engine
    from app.models import Base, Location, Report
    from app.runtime import effective_llm_mode
    from app.schemas import ConfirmIn, TicketDraft
    from app.seed import generate

    settings = get_settings()
    mode = effective_llm_mode()
    engine = init_engine()
    Base.metadata.create_all(engine)
    db = SessionLocal()
    generate.run(db, history=False, cluster=False)  # campus, teams, SOPs; no tickets
    rooms = {loc.room.upper(): loc for loc in db.query(Location).all()}

    with open(args.labels, newline="", encoding="utf-8") as f:
        items = list(csv.DictReader(f))
    if args.limit:
        items = items[: args.limit]

    print(f"SnapFix eval: {len(items)} items, mode={mode}, embedder={get_embedder().name}")
    results = []
    started = time.perf_counter()
    for i, row in enumerate(items, 1):
        text = row["user_text"].strip()
        image = None
        if row.get("image_file"):
            path = EVAL_DIR / "dataset" / "images" / row["image_file"]
            image = path.read_bytes() if path.exists() else None
        true_room = (row.get("true_room") or "").strip().upper() or None

        t0 = time.perf_counter()
        intake = pipeline.intake(db, image=image, text=text, location_code=(row.get("location_code") or None))
        resolved = intake.resolution.location
        if intake.ticket is not None:  # hazard fast path (ticket already created, enrichment ran inline)
            db.expire_all()
            report = db.get(Report, intake.report.id)
            draft = TicketDraft(**report.extracted_json)
            ticket_id, merged = intake.ticket.id, intake.merged
        else:
            draft = intake.draft
            pick = resolved or (rooms.get(true_room) if true_room else None) or next(iter(rooms.values()))
            out = pipeline.confirm(db, intake.report.id, ConfirmIn(location_id=pick.id))
            report = db.get(Report, intake.report.id)
            ticket_id, merged = out.ticket.id, out.merged
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        pred_hazard = intake.hazard.is_hazard
        true_hazard = row["true_is_hazard"].strip().lower() == "true"
        pred_sev = 4 if pred_hazard else int(draft.severity)
        base = mock_extract(text, has_image=image is not None)
        rec = {
            "i": i,
            "text": text,
            "has_image": image is not None,
            "true": {"category": row["true_category"], "trade": row["true_trade"], "severity": int(row["true_severity"]),
                     "is_hazard": true_hazard, "room": true_room, "group": row.get("duplicate_group_id") or None},
            "pred": {"category": draft.category, "trade": taxonomy.trade_for_category(draft.category),
                     "severity": pred_sev, "is_hazard": pred_hazard, "hazard_type": intake.hazard.hazard_type,
                     "room": resolved.room.upper() if resolved else None, "location_method": intake.resolution.method,
                     "confidence": draft.confidence},
            "baseline": {"category": base.category, "trade": base.trade, "severity": 4 if base.is_hazard else base.severity},
            "ticket_id": str(ticket_id),
            "merged": merged,
            "server_ms": report.latency_ms,
            "wall_ms": elapsed_ms,
            "cost_usd": report.cost_usd,
            "llm_mode": report.llm_mode,
            "notes": row.get("notes") or "",
        }
        results.append(rec)
        ok = "✓" if rec["pred"]["category"] == rec["true"]["category"] else "✗"
        print(f"  [{i:3d}] {ok} {rec['pred']['category']:20s} {'HAZARD ' if pred_hazard else ''}{text[:60]}")

    # ---------------------------------------------------------------------------------------------
    n = len(results)
    def field_acc(key, src="pred"):
        return ratio(sum(r[src][key] == r["true"][key] for r in results), n)

    sev_within = ratio(sum(abs(r["pred"]["severity"] - r["true"]["severity"]) <= 1 for r in results), n)
    base_within = ratio(sum(abs(r["baseline"]["severity"] - r["true"]["severity"]) <= 1 for r in results), n)
    tp = sum(r["pred"]["is_hazard"] and r["true"]["is_hazard"] for r in results)
    fn = sum((not r["pred"]["is_hazard"]) and r["true"]["is_hazard"] for r in results)
    fp = sum(r["pred"]["is_hazard"] and not r["true"]["is_hazard"] for r in results)
    with_room = [r for r in results if r["true"]["room"]]
    loc_acc = ratio(sum(r["pred"]["room"] == r["true"]["room"] for r in with_room), len(with_room))
    no_qr = [r for r in with_room if r["pred"]["location_method"] != "qr"]
    loc_acc_no_qr = ratio(sum(r["pred"]["room"] == r["true"]["room"] for r in no_qr), len(no_qr))

    same_pred = same_true = both = 0
    for a, b in combinations(results, 2):
        t = bool(a["true"]["group"]) and a["true"]["group"] == b["true"]["group"]
        p = a["ticket_id"] == b["ticket_id"]
        same_true += t
        same_pred += p
        both += t and p
    d_prec, d_rec = ratio(both, same_pred), ratio(both, same_true)
    d_f1 = round(2 * d_prec * d_rec / (d_prec + d_rec), 4) if d_prec and d_rec else (0.0 if same_true else None)

    trades = taxonomy.TRADES
    matrix = [[0] * len(trades) for _ in trades]
    for r in results:
        matrix[trades.index(r["true"]["trade"])][trades.index(r["pred"]["trade"])] += 1

    server = [float(r["server_ms"]) for r in results if r["server_ms"] is not None]
    costs = [r["cost_usd"] for r in results]
    metrics = {
        "category_accuracy": field_acc("category"),
        "trade_accuracy": field_acc("trade"),
        "severity_exact": field_acc("severity"),
        "severity_within_1": sev_within,
        "hazard_recall": ratio(tp, tp + fn),
        "hazard_precision": ratio(tp, tp + fp),
        "hazard_counts": {"tp": tp, "fn": fn, "fp": fp},
        "location_accuracy": loc_acc,
        "location_items": len(with_room),
        "location_accuracy_without_qr": loc_acc_no_qr,
        "location_items_without_qr": len(no_qr),
        "dedupe_precision": d_prec,
        "dedupe_recall": d_rec,
        "dedupe_f1": d_f1,
        "dedupe_pairs": {"true_same": same_true, "pred_same": same_pred, "both": both},
        "latency_ms": {"p50": pct(server, 0.5), "p95": pct(server, 0.95),
                       "mean": round(statistics.mean(server), 1) if server else None},
        "cost_per_report_usd": round(sum(costs) / n, 6) if n else None,
        "cost_total_usd": round(sum(costs), 4),
    }
    baseline = {
        "name": "keyword classifier (no LLM)",
        "category_accuracy": field_acc("category", "baseline"),
        "trade_accuracy": field_acc("trade", "baseline"),
        "severity_exact": field_acc("severity", "baseline"),
        "severity_within_1": base_within,
    }
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "note": ("MOCK MODE: predictions come from the keyword classifier, not Claude. Run with ANTHROPIC_API_KEY "
                 "set for real model accuracy.") if mode == "mock" else "Live run with Claude.",
        "models": {"main": settings.anthropic_model_main, "fast": settings.anthropic_model_fast},
        "prompt_version": PROMPT_VERSION,
        "embedder": get_embedder().name,
        "n_items": n,
        "n_with_photo": sum(r["has_image"] for r in results),
        "metrics": metrics,
        "baseline": baseline,
        "confusion_trade": {"labels": trades, "matrix": matrix},
        "items": results,
        "duration_s": round(time.perf_counter() - started, 1),
    }
    results_dir = Path(os.environ["EVAL_RESULTS_DIR"])
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{run_id}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (results_dir / f"{run_id}.md").write_text(markdown(out), encoding="utf-8")
    print(markdown(out))
    print(f"\nWrote {results_dir / (run_id + '.json')}")
    if metrics["hazard_recall"] is not None and metrics["hazard_recall"] < 1.0:
        print("FAIL: hazard recall below 100%", file=sys.stderr)
        return 1
    return 0


def markdown(out: dict) -> str:
    m, b = out["metrics"], out["baseline"]

    def f(v):
        return "-" if v is None else (f"{v * 100:.1f}%" if isinstance(v, float) and v <= 1 else str(v))

    lat = m["latency_ms"]
    lines = [
        f"# SnapFix evaluation {out['run_id']}",
        "",
        f"- Mode: **{out['mode']}** ({out['note']})",
        f"- Items: {out['n_items']} ({out['n_with_photo']} with photos) · prompt `{out['prompt_version']}` · "
        f"embedder `{out['embedder']}`",
        "",
        "| Metric | SnapFix | Keyword baseline |",
        "|---|---|---|",
        f"| Category accuracy | {f(m['category_accuracy'])} | {f(b['category_accuracy'])} |",
        f"| Trade accuracy | {f(m['trade_accuracy'])} | {f(b['trade_accuracy'])} |",
        f"| Severity exact | {f(m['severity_exact'])} | {f(b['severity_exact'])} |",
        f"| Severity within ±1 | {f(m['severity_within_1'])} | {f(b['severity_within_1'])} |",
        f"| Hazard recall (must be 100%) | {f(m['hazard_recall'])} | |",
        f"| Hazard precision | {f(m['hazard_precision'])} | |",
        f"| Location auto-resolved correctly | {f(m['location_accuracy'])} ({m['location_items']} items) | |",
        f"| … from text/photo alone (no QR) | {f(m['location_accuracy_without_qr'])} "
        f"({m['location_items_without_qr']} items) | |",
        f"| Dedupe precision / recall / F1 | {f(m['dedupe_precision'])} / {f(m['dedupe_recall'])} / "
        f"{f(m['dedupe_f1'])} | |",
        f"| Photo → ticket p50 / p95 (server) | {lat['p50'] and round(lat['p50'])} ms / "
        f"{lat['p95'] and round(lat['p95'])} ms | |",
        f"| Cost per report | ${m['cost_per_report_usd']:.4f} | $0 |",
        "",
        "## Misclassified items",
        "",
    ]
    misses = [r for r in out["items"] if r["pred"]["category"] != r["true"]["category"]]
    lines += [f"- `{r['text']}` → predicted `{r['pred']['category']}`, expected `{r['true']['category']}`"
              for r in misses] or ["- none"]
    hz = [r for r in out["items"] if r["true"]["is_hazard"] and not r["pred"]["is_hazard"]]
    lines += ["", "## Missed hazards", ""] + ([f"- `{r['text']}`" for r in hz] or ["- none"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
