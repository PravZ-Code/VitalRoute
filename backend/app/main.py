"""VitalRoute — Confidence-Aware Emergency Destination Orchestration.

FastAPI decision core: REST API + native WebSocket handshake layer.
All clinical math runs locally (NumPy-free deterministic — pure Python, <15ms).
Includes persistent SQLite database engine and clinical audit middleware.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import time
import urllib.parse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, database, state
from .middleware import ClinicalAuditMiddleware
from .models import (AssessmentRequest, AssessmentResult, Handshake,
                     HandshakeStatus, HospitalEvent, PatientSummary, WhatIfRequest)
from .services import clinical, ttdc
from .services.simulation import simulator
from .ws import manager

# Path Resolution for static assets and mobile PWA
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
if not STATIC_DIR.exists():
    STATIC_DIR = BASE_DIR.parent / "static"

MOBILE_DIR = BASE_DIR / "mobile"
if not MOBILE_DIR.exists():
    MOBILE_DIR = BASE_DIR.parent / "mobile"
if not MOBILE_DIR.exists():
    MOBILE_DIR = STATIC_DIR / "mobile"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    database.init_db()

    # Seed hospitals into database if not present, or load persisted state
    saved_hospitals = database.load_hospitals()
    if not saved_hospitals:
        for h in state.get_hospitals().values():
            database.save_hospital(h)
    else:
        for h_id, h_data in saved_hospitals.items():
            state.HOSPITALS[h_id] = h_data

    database.log_audit_event("SYSTEM_STARTUP", {
        "status": "Database connected",
        "hospitals_count": len(state.HOSPITALS),
        "db_path": database.DB_PATH,
    })

    loop = asyncio.get_running_loop()

    async def _broadcast_sim_changes(changes: list[dict]) -> None:
        if not changes:
            return
        hospitals = state.get_hospitals()
        for ch in changes:
            hid = ch.get("hospital_id")
            if hid and hid in hospitals:
                database.save_hospital(hospitals[hid])
                snap = ttdc.snapshot(hospitals[hid]).model_dump()
                await manager.broadcast_all({
                    "type": "hospital_update",
                    "hospital": snap,
                    "changes": [ch.get("field", "status")],
                })

    simulator.set_broadcaster(lambda changes: asyncio.run_coroutine_threadsafe(_broadcast_sim_changes(changes), loop))
    simulator.start()
    yield
    simulator.stop()
    database.log_audit_event("SYSTEM_SHUTDOWN", {"status": "Graceful stop"})



app = FastAPI(
    title="VitalRoute",
    version="1.0.0",
    description="Confidence-Aware Emergency Destination Orchestration (SDG 3)",
    lifespan=lifespan,
)

# Healthcare Security & Audit Middleware
app.add_middleware(ClinicalAuditMiddleware)

# Cross-Origin Resource Sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- health
@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "vitalroute",
        "database": "sqlite-connected",
        "ts": time.time(),
        "data_mode": "synthetic-simulation",
    }


# ---------------------------------------------------------------- database audit
@app.get("/api/db/audit")
async def get_audit_trail(limit: int = 50) -> list[dict]:
    """Inspect recent clinical audit log entries."""
    return database.get_recent_audit_events(limit=limit)


# ---------------------------------------------------------------- hospitals
@app.get("/api/hospitals")
async def get_hospitals() -> list[dict]:
    snaps = [ttdc.snapshot(h).model_dump() for h in state.get_hospitals().values()]
    return sorted(snaps, key=lambda s: s["name"])


@app.get("/api/hospitals/{hospital_id}")
async def get_hospital(hospital_id: str) -> dict:
    hospitals = state.get_hospitals()
    if hospital_id not in hospitals:
        raise HTTPException(404, "unknown hospital")
    return ttdc.snapshot(hospitals[hospital_id]).model_dump()


@app.post("/api/hospitals/event")
async def inject_event(ev: HospitalEvent) -> dict:
    hospitals = state.get_hospitals()
    if ev.hospital_id not in hospitals:
        raise HTTPException(404, "unknown hospital")
    fields = ev.model_dump(exclude={"hospital_id"}, exclude_none=True)
    refresh = fields.pop("refresh_timestamp", True)
    changes = list(fields.keys())
    updated = state.update_hospital(ev.hospital_id, refresh_timestamp=refresh, **fields)

    # Persist in SQLite database
    database.save_hospital(updated)
    database.log_audit_event("HOSPITAL_EVENT", {
        "hospital_id": ev.hospital_id,
        "fields_updated": changes,
    })

    snap = ttdc.snapshot(updated).model_dump()
    await manager.broadcast_all({"type": "hospital_update", "hospital": snap, "changes": changes})
    return snap



# ---------------------------------------------------------------- assessment
@app.post("/api/assessments", response_model=AssessmentResult)
async def create_assessment(req: AssessmentRequest) -> AssessmentResult:
    news2 = clinical.news2_score(req.vitals)
    state.AMBULANCES[req.ambulance_id] = {
        "latitude": req.latitude,
        "longitude": req.longitude,
        "incident": True,
    }
    ranked, rationale = ttdc.rank_hospitals(
        state.get_hospitals(),
        req.latitude,
        req.longitude,
        req.care_tag,
        custom_requirements=req.custom_requirements,
        is_offline=req.offline_mode,
    )
    recommended = ranked[0].hospital.id if ranked and ranked[0].rank == 1 else None
    offline_warn = (
        "Operating in Offline Probabilistic Mode: Recommendations derived from local "
        "historical diurnal occupancy model. Not a confirmed reservation — voice radio "
        "handshake required."
        if req.offline_mode
        else None
    )
    result = AssessmentResult(
        incident_id=f"INC-{abs(hash((req.ambulance_id, time.time()))) % 10**6:06d}",
        news2=news2,
        news2_risk_band=clinical.risk_band(news2),
        care_tag=req.care_tag,
        emergency_description=req.emergency_description,
        custom_requirements=req.custom_requirements,
        paramedic_notes=req.paramedic_notes,
        rankings=ranked,
        recommended=recommended,
        rationale=rationale,
        offline_mode=req.offline_mode,
        system_status="OFFLINE_PREDICTIVE" if req.offline_mode else "ONLINE",
        offline_warning=offline_warn,
    )

    # Log clinical assessment event in database
    database.log_audit_event("ASSESSMENT", {
        "ambulance_id": req.ambulance_id,
        "care_tag": req.care_tag.value,
        "news2": news2,
        "recommended": recommended,
        "offline_mode": req.offline_mode,
    })

    await manager.broadcast_all({"type": "assessment", "result": result.model_dump()})
    await manager.broadcast(f"ambulance:{req.ambulance_id}", {
        "type": "route_calculated",
        "result": result.model_dump(),
        "recommended": recommended,
    })
    return result



# ---------------------------------------------------------------- handshake
@app.post("/api/handshake", response_model=Handshake, status_code=201)
async def request_handshake(req: AssessmentRequest, hospital_id: str) -> Handshake:
    hospitals = state.get_hospitals()
    if hospital_id not in hospitals:
        raise HTTPException(404, "unknown hospital")
    news2 = clinical.news2_score(req.vitals)
    patient = PatientSummary(
        news2=news2,
        news2_risk_band=clinical.risk_band(news2),
        care_tag=req.care_tag,
        vitals=req.vitals,
        emergency_description=req.emergency_description,
        custom_requirements=req.custom_requirements,
        paramedic_notes=req.paramedic_notes,
    )
    eta = ttdc.drive_time_min(req.latitude, req.longitude, hospitals[hospital_id])
    hs = Handshake(
        ambulance_id=req.ambulance_id,
        hospital_id=hospital_id,
        patient=patient,
        eta_min=round(eta, 1),
    )
    state.add_handshake(hs)

    # Persist in database
    database.save_handshake(hs.model_dump())
    database.log_audit_event("HANDSHAKE_REQUEST", {
        "hs_id": hs.id,
        "ambulance_id": hs.ambulance_id,
        "hospital_id": hospital_id,
        "eta_min": hs.eta_min,
        "care_tag": req.care_tag.value,
    })

    suggested_esi = clinical.suggested_esi(
        news2, str(req.care_tag.value), req.emergency_description
    )
    payload = {
        "type": "handshake_request",
        "handshake": hs.model_dump(),
        "suggested_esi": suggested_esi,
    }
    await manager.broadcast(f"hospital:{hospital_id}", payload)
    await manager.broadcast("hospitals", payload)
    await manager.broadcast(f"ambulance:{req.ambulance_id}", {
        "type": "handshake_created",
        "handshake": hs.model_dump(),
    })
    # deterministic timeout fallback
    asyncio.create_task(_timeout_watchdog(hs.id))
    return hs



async def _timeout_watchdog(hs_id: str) -> None:
    await asyncio.sleep(config.HANDSHAKE_TIMEOUT_SEC)
    hs = state.get_handshake(hs_id)
    if hs and hs.status == HandshakeStatus.PENDING_RESPONSE:
        hs.status = HandshakeStatus.TIMED_OUT
        database.update_handshake(hs_id, status=HandshakeStatus.TIMED_OUT.value)
        await manager.broadcast(
            f"ambulance:{hs.ambulance_id}",
            {
                "type": "handshake_timeout",
                "handshake": hs.model_dump(),
                "fallback": "revert to regional protocol routing",
            },
        )
        await manager.broadcast(
            "hospitals",
            {"type": "handshake_timeout", "handshake": hs.model_dump()},
        )


@app.post("/api/handshake/{hs_id}/ack", response_model=Handshake)
async def acknowledge_handshake(
    hs_id: str,
    confirm: bool = True,
    constraint: str | None = None,
    anticipated_esi: int | None = None,
) -> Handshake:
    hs = state.get_handshake(hs_id)
    if not hs:
        raise HTTPException(404, "handshake not found")
    if hs.status != HandshakeStatus.PENDING_RESPONSE:
        raise HTTPException(409, f"handshake already resolved ({hs.status})")
    hs.responded_ts = time.time()
    if confirm:
        hs.status = HandshakeStatus.CONFIRMED
        hs.anticipated_esi = anticipated_esi
    else:
        hs.status = HandshakeStatus.CONSTRAINED_REROUTE_REQUESTED
        hs.constraint_detail = constraint

    # Update SQLite database
    database.update_handshake(
        hs_id,
        status=hs.status.value,
        responded_ts=hs.responded_ts,
        constraint=hs.constraint_detail,
        esi=hs.anticipated_esi,
    )
    database.log_audit_event("HANDSHAKE_ACK", {
        "hs_id": hs_id,
        "status": hs.status.value,
        "confirm": confirm,
        "anticipated_esi": anticipated_esi,
    })

    # Broadcast update
    msg = {
        "type": "handshake_ack",
        "handshake": hs.model_dump(),
        "confirmed": confirm,
    }
    await manager.broadcast(f"ambulance:{hs.ambulance_id}", msg)
    await manager.broadcast(f"hospital:{hs.hospital_id}", msg)
    await manager.broadcast("hospitals", msg)
    return hs


@app.get("/api/handshakes", response_model=list[Handshake])
async def list_handshakes() -> list[Handshake]:
    return state.all_handshakes()


@app.get("/api/handshakes/hospital/{hospital_id}")
async def list_hospital_handshakes(hospital_id: str) -> list[dict]:
    handshakes = [
        h.model_dump()
        for h in state.all_handshakes()
        if h.hospital_id == hospital_id
    ]
    return sorted(handshakes, key=lambda x: x["created_ts"], reverse=True)


# ------------------------------------------------------- counterfactuals
@app.post("/api/whatif", response_model=AssessmentResult)
async def what_if(req: WhatIfRequest) -> AssessmentResult:
    hospitals = state.get_hospitals()
    if req.overrides.hospital_id not in hospitals:
        raise HTTPException(404, "unknown hospital")
    fields = req.overrides.model_dump(exclude={"hospital_id"}, exclude_none=True)
    fields.pop("refresh_timestamp", None)
    hospitals[req.overrides.hospital_id] = {
        **hospitals[req.overrides.hospital_id],
        **fields,
    }
    news2 = clinical.news2_score(req.assessment.vitals)
    ranked, rationale = ttdc.rank_hospitals(
        hospitals,
        req.assessment.latitude,
        req.assessment.longitude,
        req.assessment.care_tag,
        custom_requirements=req.assessment.custom_requirements,
    )
    recommended = ranked[0].hospital.id if ranked and ranked[0].rank == 1 else None
    return AssessmentResult(
        incident_id="WHATIF",
        news2=news2,
        news2_risk_band=clinical.risk_band(news2),
        care_tag=req.assessment.care_tag,
        emergency_description=req.assessment.emergency_description,
        custom_requirements=req.assessment.custom_requirements,
        paramedic_notes=req.assessment.paramedic_notes,
        rankings=ranked,
        recommended=recommended,
        rationale=rationale,
    )


# ---------------------------------------------------------------- websockets
@app.websocket("/ws/{channel:path}")
async def ws_endpoint(ws: WebSocket, channel: str) -> None:
    channel = urllib.parse.unquote(channel)
    if not all(c.isalnum() or c in "-_:" for c in channel):
        await ws.close(code=4400)
        return
    await manager.connect(channel, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(channel, ws)


# ---------------------------------------------------------------- static & mobile
@app.get("/mobile")
@app.get("/mobile/")
async def mobile_app():
    mobile_index = MOBILE_DIR / "index.html"
    if mobile_index.is_file():
        return FileResponse(mobile_index)
    return FileResponse(STATIC_DIR / "index.html")


if MOBILE_DIR.exists():
    app.mount("/assets/mobile", StaticFiles(directory=MOBILE_DIR), name="mobile-assets")

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    if full_path:
        candidate = (STATIC_DIR / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(STATIC_DIR.resolve()):
            return FileResponse(candidate)
        candidate_mobile = (MOBILE_DIR / full_path).resolve()
        if candidate_mobile.is_file() and candidate_mobile.is_relative_to(MOBILE_DIR.resolve()):
            return FileResponse(candidate_mobile)
    mobile_index = MOBILE_DIR / "index.html"
    if mobile_index.is_file():
        return FileResponse(mobile_index)
    return FileResponse(STATIC_DIR / "index.html")

