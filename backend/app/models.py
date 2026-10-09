"""VitalRoute data models.

Strict clinical separation (per docs/00, section 5):
  - Paramedics collect NEWS2 vitals + field triage tags (no ESI in the field).
  - The receiving hospital triage nurse assigns/anticipates the ESI level.
"""
from __future__ import annotations

import enum
import time
import uuid
from typing import Optional

from pydantic import BaseModel, Field


class CareTag(str, enum.Enum):
    STEMI = "STEMI"            # requires Cath Lab
    STROKE = "STROKE"          # requires CT scanner / thrombolysis
    TRAUMA = "TRAUMA"          # requires Level-1 trauma bay
    RESPIRATORY = "RESPIRATORY"# requires Ventilator / Respiratory ICU
    SEPSIS = "SEPSIS"          # requires Resuscitation / ICU
    PEDIATRIC = "PEDIATRIC"    # requires Pediatric ED / PICU
    OBSTETRIC = "OBSTETRIC"    # requires Labor & Delivery / OBGYN
    BURNS = "BURNS"            # requires Specialized Burn Care
    TOXICOLOGY = "TOXICOLOGY"  # requires Toxicology / Dialysis
    ANAPHYLAXIS = "ANAPHYLAXIS"# requires Emergency Airway
    GENERAL = "GENERAL"
    CUSTOM = "CUSTOM"          # Paramedic custom situation

    def __str__(self) -> str:
        return self.value


class SpecialistStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"          # scrubbed in / ready now  -> T_readiness = 0
    ON_CALL = "ON_CALL"        # needs call-in             -> 15-20 min
    UNAVAILABLE = "UNAVAILABLE"

    def __str__(self) -> str:
        return self.value


class HandshakeStatus(str, enum.Enum):
    UNCONFIRMED = "UNCONFIRMED"
    PENDING_RESPONSE = "PENDING_RESPONSE"
    CONFIRMED = "CONFIRMED"
    CONSTRAINED_REROUTE_REQUESTED = "CONSTRAINED_REROUTE_REQUESTED"
    TIMED_OUT = "TIMED_OUT"

    def __str__(self) -> str:
        return self.value


class Vitals(BaseModel):
    """Six NEWS2 vital sign inputs collected by the paramedic."""
    respiration_rate: int = Field(..., ge=0, le=80, description="breaths/min")
    spo2: int = Field(..., ge=50, le=100, description="percent")
    systolic_bp: int = Field(..., ge=40, le=300, description="mmHg")
    heart_rate: int = Field(..., ge=20, le=250, description="beats/min")
    consciousness: str = Field("A", pattern="^[AVPU]$", description="AVPU scale")
    temperature: float = Field(..., ge=30.0, le=43.0, description="celsius")


class AssessmentRequest(BaseModel):
    ambulance_id: str = "AMB-1"
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    vitals: Vitals
    care_tag: CareTag = CareTag.GENERAL
    emergency_description: Optional[str] = Field(
        None,
        description="Free-text situation description typed manually by the ambulance crew",
    )
    custom_requirements: list[str] = Field(
        default_factory=list,
        description="Specialized clinical resources requested (e.g. Burn Unit, Hyperbaric, Dialysis)",
    )
    paramedic_notes: Optional[str] = Field(
        None,
        description="Field notes or interventions performed by the ambulance crew",
    )
    offline_mode: bool = Field(
        False,
        description="Whether ambulance is operating in offline predictive mode",
    )


class HospitalSnapshot(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    beds_available: int
    icu_beds_available: int
    active_boarders: int          # ED boarding queue
    inbound_ambulances: int
    ct_operational: bool
    specialist_status: SpecialistStatus
    specialties: list[str] = Field(default_factory=list)
    last_update_ts: float
    # computed
    freshness: float = 0.0
    staleness_minutes: float = 0.0
    confidence_adjusted_beds: float = 0.0
    stale: bool = False
    # offline probabilistic forecast
    capacity_probability: float = 1.0
    icu_probability: float = 1.0
    forecast_mode: str = "LIVE"
    forecast_confidence_band: str = "VERIFIED_LIVE"
    forecast_disclaimer: str = ""


class RankedHospital(BaseModel):
    hospital: HospitalSnapshot
    eligible: bool
    ineligibility_reason: Optional[str] = None
    t_drive_min: float
    t_offload_min: float
    t_readiness_min: float
    ttdc_min: float
    capability_match: float
    utility: float
    rank: int


class PatientSummary(BaseModel):
    # ephemerally pseudo-anonymous per doc invariant (no demographics)
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    news2: int
    news2_risk_band: str
    care_tag: CareTag
    vitals: Vitals
    emergency_description: Optional[str] = None
    custom_requirements: list[str] = Field(default_factory=list)
    paramedic_notes: Optional[str] = None
    created_ts: float = Field(default_factory=time.time)


class Handshake(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    ambulance_id: str
    hospital_id: str
    patient: PatientSummary
    eta_min: float
    status: HandshakeStatus = HandshakeStatus.PENDING_RESPONSE
    created_ts: float = Field(default_factory=time.time)
    responded_ts: Optional[float] = None
    constraint_detail: Optional[str] = None
    anticipated_esi: Optional[int] = Field(None, ge=1, le=5)


class AssessmentResult(BaseModel):
    incident_id: str
    news2: int
    news2_risk_band: str
    care_tag: CareTag
    emergency_description: Optional[str] = None
    custom_requirements: list[str] = Field(default_factory=list)
    paramedic_notes: Optional[str] = None
    rankings: list[RankedHospital]
    recommended: Optional[str]
    rationale: list[str]
    offline_mode: bool = False
    system_status: str = "ONLINE"
    offline_warning: Optional[str] = None
    generated_ts: float = Field(default_factory=time.time)
    data_disclaimer: str = (
        "Synthetic multi-hospital simulation data — prototype environment. "
        "Not a live clinical system."
    )


class HospitalEvent(BaseModel):
    """Simulator injection: alter a hospital's operational state."""
    hospital_id: str
    beds_available: Optional[int] = Field(None, ge=0)
    icu_beds_available: Optional[int] = Field(None, ge=0)
    active_boarders: Optional[int] = Field(None, ge=0)
    inbound_ambulances: Optional[int] = Field(None, ge=0)
    ct_operational: Optional[bool] = None
    specialist_status: Optional[SpecialistStatus] = None
    specialties: Optional[list[str]] = None
    refresh_timestamp: bool = True


class WhatIfRequest(BaseModel):
    """Counterfactual sandbox: replay the last ranking under a modified state."""
    assessment: AssessmentRequest
    overrides: HospitalEvent

