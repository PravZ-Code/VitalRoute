"""Pillar 2 — Time-to-Definitive-Care (TTDC) Optimizer + Pillar 4 rationale.

TTDC(H_i)   = T_drive + T_offload + T_readiness
T_offload   = beta * ActiveBoarders + gamma * InboundAmbulances
Utility(H_i)= (1 / TTDC) * CapabilityMatch * F(H_i)
"""
from __future__ import annotations

import math
import time

from .. import config
from ..models import (CareTag, HospitalSnapshot, RankedHospital,
                      SpecialistStatus)
from . import confidence

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def drive_time_min(amb_lat: float, amb_lon: float, hosp: dict) -> float:
    road_km = (haversine_km(amb_lat, amb_lon, hosp["latitude"], hosp["longitude"])
               * config.ROAD_FACTOR)
    return road_km / config.AVG_SPEED_KMH * 60.0


def offload_delay_min(hosp: dict) -> float:
    return (config.OFFLOAD_BETA * hosp["active_boarders"]
            + config.OFFLOAD_GAMMA * hosp["inbound_ambulances"])


def readiness_min(hosp: dict) -> float:
    s = hosp["specialist_status"]
    if s == SpecialistStatus.ACTIVE:
        return 0.0
    if s == SpecialistStatus.ON_CALL:
        return config.READINESS_ON_CALL_MIN
    return config.READINESS_UNAVAILABLE_MIN


def capability_match(hosp: dict, tag: CareTag,
                     custom_requirements: list[str] | None = None) -> tuple[float, str | None]:
    """Binary mandatory capability checks; returns (match, reason_if_failed)."""
    if hosp.get("beds_available", 0) <= 0:
        return 0.0, "No ED beds available"
    if tag == CareTag.STEMI and hosp.get("specialist_status") == SpecialistStatus.UNAVAILABLE:
        return 0.0, "Cath Lab team unavailable — STEMI diversion"
    if tag == CareTag.STROKE and not hosp.get("ct_operational"):
        return 0.0, "CT scanner offline — thrombolysis workup impossible"
    if tag == CareTag.TRAUMA and hosp.get("specialist_status") == SpecialistStatus.UNAVAILABLE:
        return 0.0, "Trauma surgery team unavailable"
    if tag == CareTag.RESPIRATORY and hosp.get("icu_beds_available", 0) <= 0 and hosp.get("specialist_status") == SpecialistStatus.UNAVAILABLE:
        return 0.0, "No ICU/Respiratory critical care beds"
    if tag == CareTag.SEPSIS and hosp.get("icu_beds_available", 0) <= 0:
        return 0.0, "ICU bed required for septic shock resuscitation"
    
    # Check custom requirements against hospital specialties / capabilities if specified
    hosp_specs = [str(s).lower() for s in hosp.get("specialties", [])]
    if custom_requirements and hosp_specs:
        for req in custom_requirements:
            req_clean = req.strip().lower()
            if not req_clean:
                continue
            if not any(req_clean in s or s in req_clean for s in hosp_specs):
                return 0.0, f"Missing requested clinical resource: {req}"

    return 1.0, None


def snapshot(hosp: dict, now: float | None = None,
             travel_time_min: float = 0.0, is_offline: bool = False) -> HospitalSnapshot:
    now = time.time() if now is None else now
    f = confidence.freshness(hosp["last_update_ts"], now)
    forecast_bed = confidence.forecast_capacity_probability(
        reported_beds=hosp.get("beds_available", 0),
        last_update_ts=hosp["last_update_ts"],
        travel_time_min=travel_time_min,
        now=now,
        is_offline=is_offline,
        is_icu=False,
    )
    forecast_icu = confidence.forecast_capacity_probability(
        reported_beds=hosp.get("icu_beds_available", 0),
        last_update_ts=hosp["last_update_ts"],
        travel_time_min=travel_time_min,
        now=now,
        is_offline=is_offline,
        is_icu=True,
    )
    return HospitalSnapshot(
        **hosp,
        freshness=round(f, 3),
        staleness_minutes=round(confidence.staleness_minutes(hosp["last_update_ts"], now), 1),
        confidence_adjusted_beds=round(
            confidence.confidence_adjusted_capacity(hosp.get("beds_available", 0), f), 2),
        stale=confidence.is_stale(f),
        capacity_probability=forecast_bed["probability"],
        icu_probability=forecast_icu["probability"],
        forecast_mode=forecast_bed["forecast_mode"],
        forecast_confidence_band=forecast_bed["confidence_band"],
        forecast_disclaimer=forecast_bed["disclaimer"],
    )


def rank_hospitals(hospitals: dict[str, dict], amb_lat: float, amb_lon: float,
                   tag: CareTag, now: float | None = None,
                   custom_requirements: list[str] | None = None,
                   is_offline: bool = False
                   ) -> tuple[list[RankedHospital], list[str]]:
    now = time.time() if now is None else now
    ranked: list[RankedHospital] = []
    for h in hospitals.values():
        t_drive = drive_time_min(amb_lat, amb_lon, h)
        snap = snapshot(h, now, travel_time_min=t_drive, is_offline=is_offline)
        match, reason = capability_match(h, tag, custom_requirements)
        t_off = offload_delay_min(h)
        t_ready = readiness_min(h)
        ttdc = t_drive + t_off + t_ready

        # Utility factors in TTDC, capability match, freshness, and arrival availability probability
        prob_weight = snap.capacity_probability if is_offline else (0.3 + 0.7 * snap.capacity_probability)
        utility = (1.0 / ttdc) * match * snap.freshness * prob_weight if math.isfinite(ttdc) else 0.0
        ranked.append(RankedHospital(
            hospital=snap, eligible=bool(match) and math.isfinite(ttdc),
            ineligibility_reason=reason,
            t_drive_min=round(t_drive, 1), t_offload_min=round(t_off, 1),
            t_readiness_min=round(t_ready, 1) if math.isfinite(t_ready) else -1,
            ttdc_min=round(ttdc, 1) if math.isfinite(ttdc) else -1,
            capability_match=match, utility=round(utility, 4), rank=0))
    eligible = sorted((r for r in ranked if r.eligible),
                      key=lambda r: r.utility, reverse=True)
    for i, r in enumerate(eligible, 1):
        r.rank = i
    rationale = build_rationale(eligible, is_offline=is_offline)
    return eligible + [r for r in ranked if not r.eligible], rationale


def build_rationale(sorted_eligible: list[RankedHospital], is_offline: bool = False) -> list[str]:
    """Pillar 4 — transparent factor decomposition ("The Why Inspector")."""
    if not sorted_eligible:
        return ["No eligible receiving facility — escalate to regional dispatch protocol."]
    out: list[str] = []
    top = sorted_eligible[0]

    if is_offline:
        out.append(
            f"OFFLINE PREDICTIVE MODE: Local diurnal forecast predicts {top.hospital.capacity_probability:.0%} "
            f"probability of bed availability at {top.hospital.name} upon estimated arrival ({top.t_drive_min:.0f}m travel). "
            f"This is an unconfirmed statistical estimate — radio contact required."
        )

    for other in sorted_eligible[1:]:
        h1, h2 = top.hospital, other.hospital
        saving = other.ttdc_min - top.ttdc_min
        reasons: list[str] = []
        if top.t_drive_min > other.t_drive_min:
            reasons.append(
                f"although {h1.name} is {top.t_drive_min - other.t_drive_min:.0f} min "
                f"farther by road")
        if h2.stale:
            reasons.append(
                f"{h2.name}'s capacity report is {h2.staleness_minutes:.0f} min old "
                f"(freshness {h2.freshness:.2f} — unverified)")
        if other.t_offload_min - top.t_offload_min >= 5:
            reasons.append(
                f"{h2.name} carries an estimated {other.t_offload_min:.0f}-min ambulance "
                f"offload delay ({other.hospital.active_boarders} boarders)")
        if other.t_readiness_min > 0 and other.t_readiness_min != top.t_readiness_min:
            reasons.append(
                f"{h2.name}'s specialist team is on-call (+{other.t_readiness_min:.0f} min)")
        if is_offline and h1.capacity_probability > h2.capacity_probability:
            reasons.append(
                f"higher predicted arrival capacity probability ({h1.capacity_probability:.0%} vs {h2.capacity_probability:.0%})")
        why = "; ".join(reasons) if reasons else "lower combined clinical timeline"
        out.append(
            f"{h1.name} preferred over {h2.name}: {why}. "
            f"Net Time-to-Definitive-Care saving: {saving:.0f} min "
            f"({top.ttdc_min:.0f} vs {other.ttdc_min:.0f} min).")
    if top.hospital.stale and not is_offline:
        out.append(
            f"WARNING: recommendation {top.hospital.name} is based on stale data "
            f"(freshness {top.hospital.freshness:.2f}) — pre-arrival readiness "
            f"handshake REQUIRED before locking destination.")
    return out
