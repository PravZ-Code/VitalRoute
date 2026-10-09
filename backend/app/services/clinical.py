"""NEWS2 scoring (Royal College of Physicians) and risk banding.

ESI is deliberately NOT computed in the field: per docs/00 section 5,
ESI is an Emergency Department triage algorithm assigned by the receiving
hospital triage nurse. We only provide a *suggested anticipated ESI* helper
used by the hospital HUD as decision support.
"""
from __future__ import annotations

from .. import config
from ..models import Vitals


def _rr_score(rr: int) -> int:
    if rr <= 8:
        return 3
    if rr <= 11:
        return 1
    if rr <= 20:
        return 0
    if rr <= 24:
        return 2
    return 3


def _spo2_score(spo2: int) -> int:
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def _sbp_score(sbp: int) -> int:
    if sbp <= 90:
        return 3
    if sbp <= 100:
        return 2
    if sbp <= 110:
        return 1
    if sbp <= 219:
        return 0
    return 3


def _hr_score(hr: int) -> int:
    if hr <= 40:
        return 3
    if hr <= 50:
        return 1
    if hr <= 90:
        return 0
    if hr <= 110:
        return 1
    if hr <= 130:
        return 2
    return 3


def _temp_score(t: float) -> int:
    if t <= 35.0:
        return 3
    if t <= 36.0:
        return 1
    if t <= 38.0:
        return 0
    if t <= 39.0:
        return 1
    return 2


def news2_score(v: Vitals) -> int:
    return (
        _rr_score(v.respiration_rate)
        + _spo2_score(v.spo2)
        + _sbp_score(v.systolic_bp)
        + _hr_score(v.heart_rate)
        + (0 if v.consciousness == "A" else 3)
        + _temp_score(v.temperature)
    )


def risk_band(score: int) -> str:
    for ceiling, band in config.NEWS2_BANDS:
        if score <= ceiling:
            return band
    return "HIGH"


def suggested_esi(news2: int, care_tag: str, emergency_description: str | None = None) -> int:
    """Decision-support heuristic for the triage nurse (not a field score).

    ESI blends acuity with anticipated resource needs.
    """
    desc = (emergency_description or "").lower()
    critical_keywords = ("arrest", "unresponsive", "apnea", "pulseless", "intubated",
                         "stridor", "cyanosis", "massive bleed", "crush")
    high_keywords = ("chest pain", "dyspnea", "altered", "stroke", "paralysis",
                     "hemorrhage", "burn", "poisoning", "toxic", "lethargic", "sepsis")

    if any(k in desc for k in critical_keywords):
        return 1

    high_acuity_tag = care_tag in ("STEMI", "STROKE", "TRAUMA", "BURNS", "ANAPHYLAXIS", "RESPIRATORY", "SEPSIS")
    if news2 >= 7 or (high_acuity_tag and news2 >= 5):
        return 1
    if news2 >= 5 or high_acuity_tag or any(k in desc for k in high_keywords):
        return 2
    if news2 >= 3:
        return 3
    if news2 >= 1:
        return 4
    return 5
