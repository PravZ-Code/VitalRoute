"""Pillar 1 — Capacity-Confidence & Offline Probabilistic Forecasting Engine.

Mathematical framework:
1. Freshness Decay: F(t) = exp(-lambda * dt) (15-min half-life)
2. Uncertainty-penalized capacity: C_adj = Capacity_reported * F - sigma * (1-F)
3. Offline Diurnal Probabilistic Forecaster:
   When connectivity is lost or reports are stale:
   - Evaluates arrival time t_arrival = now + T_drive
   - Regresses toward historical diurnal occupancy distribution mu(hour, day)
   - Computes predictive variance Var(C_arrival) growing with horizon
   - Outputs calibrated availability probability P(Capacity >= 1 | arrival_time, staleness)
     via Gaussian cumulative distribution function Phi(z).
"""
from __future__ import annotations

import datetime
import math
import time

from .. import config

# Diurnal ED arrival and occupancy cycle across 24 hours (0..23)
# Reflects operational patterns: lull in early morning (03:00-06:00),
# afternoon discharge transition (11:00-14:00), peak presentation (17:00-22:00).
DIURNAL_OCCUPANCY_MULTIPLIER: list[float] = [
    0.70, 0.65, 0.60, 0.55, 0.55, 0.60, 0.70, 0.85,  # 00:00 - 07:00 (overnight)
    1.00, 1.15, 1.25, 1.30, 1.20, 1.10, 1.15, 1.25,  # 08:00 - 15:00 (daytime)
    1.35, 1.45, 1.50, 1.45, 1.35, 1.20, 1.00, 0.85,  # 16:00 - 23:00 (evening peak)
]


def freshness(last_update_ts: float, now: float | None = None,
              lambda_: float = config.LAMBDA_DECAY) -> float:
    now = time.time() if now is None else now
    dt_minutes = max(0.0, (now - last_update_ts) / 60.0)
    return math.exp(-lambda_ * dt_minutes)


def staleness_minutes(last_update_ts: float, now: float | None = None) -> float:
    now = time.time() if now is None else now
    return max(0.0, (now - last_update_ts) / 60.0)


def confidence_adjusted_capacity(reported: float, f: float,
                                 sigma: float = config.UNCERTAINTY_SIGMA) -> float:
    return reported * f - sigma * (1.0 - f)


def is_stale(f: float, threshold: float = config.STALE_THRESHOLD) -> bool:
    return f < threshold


def normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function (Phi)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def forecast_capacity_probability(
    reported_beds: int,
    last_update_ts: float,
    travel_time_min: float = 0.0,
    now: float | None = None,
    is_offline: bool = False,
    is_icu: bool = False,
) -> dict:
    """Forecast probability P(Beds >= 1 at arrival) under stale or offline conditions.

    Combines:
    1. Memory weight of last reported capacity: W = exp(-lambda * total_horizon)
    2. Regression toward hospital diurnal historical mean at arrival time
    3. Variance expansion reflecting prediction horizon uncertainty
    4. Calibrated Gaussian CDF probability calculation Phi((E[C] - 0.5) / sigma)
    """
    now = time.time() if now is None else now
    dt_stale_min = max(0.0, (now - last_update_ts) / 60.0)
    total_horizon_min = dt_stale_min + travel_time_min

    # Arrival time hour (0..23)
    arrival_dt = datetime.datetime.fromtimestamp(now + travel_time_min * 60.0)
    hour = arrival_dt.hour
    diurnal_factor = DIURNAL_OCCUPANCY_MULTIPLIER[hour]

    # Historical diurnal mean capacity baseline (lower during evening surge)
    base_mean = 2.0 if is_icu else 4.5
    hist_mean = max(0.5, base_mean / diurnal_factor)
    hist_sigma = 1.1 if is_icu else 2.1

    # Weight of last known sensor reading vs regression to historical mean
    weight_memory = math.exp(-config.LAMBDA_DECAY * total_horizon_min)
    if is_offline:
        # Additional uncertainty penalty if ambulance is disconnected from central network
        weight_memory *= 0.80

    # Forecast variance: increases with staleness and travel horizon
    horizon_uncertainty = (1.0 - weight_memory ** 2) * (hist_sigma ** 2) + 0.36
    total_std_dev = math.sqrt(horizon_uncertainty)

    if reported_beds <= 0:
        # A zero-capacity facility frees beds via patient discharges/transfers
        # Model via Poisson queueing process: P(N >= 1 in horizon) = 1 - exp(-lambda * horizon)
        turnover_rate_per_min = (0.15 / 60.0) if is_icu else (0.50 / 60.0)
        expected_freed = turnover_rate_per_min * total_horizon_min
        expected_capacity = min(float(hist_mean), expected_freed)
        prob = 1.0 - math.exp(-expected_freed)
        if is_offline:
            prob *= 0.85
    else:
        expected_capacity = weight_memory * float(reported_beds) + (1.0 - weight_memory) * hist_mean
        # Probability that capacity >= 1 bed upon arrival
        z_score = (expected_capacity - 0.5) / max(0.1, total_std_dev)
        prob = normal_cdf(z_score)

    # Bound within [0.02, 0.98] to reflect real-world operational stochasticity
    prob = max(0.02, min(0.98, prob))

    # Categorize confidence band
    if not is_offline and dt_stale_min < 5.0:
        band = "VERIFIED_LIVE"
        mode = "LIVE"
    elif dt_stale_min >= 90.0 or total_horizon_min >= 120.0 or prob < 0.35:
        band = "LOW"
        mode = "OFFLINE_PROBABILISTIC" if is_offline else "PROBABILISTIC"
    elif is_offline or dt_stale_min >= 25.0 or prob < 0.70:
        band = "MODERATE"
        mode = "OFFLINE_PROBABILISTIC" if is_offline else "PROBABILISTIC"
    else:
        band = "HIGH"
        mode = "OFFLINE_PROBABILISTIC" if is_offline else "PROBABILISTIC"

    return {
        "probability": round(prob, 3),
        "expected_capacity": round(expected_capacity, 1),
        "std_dev": round(total_std_dev, 2),
        "confidence_band": band,
        "forecast_mode": mode,
        "is_offline": is_offline,
        "disclaimer": (
            "Probabilistic forecast based on historical diurnal occupancy patterns. "
            "Unconfirmed estimate — NOT a reservation. Radio contact required."
            if (is_offline or dt_stale_min >= 15.0)
            else "Live telemetry report from receiving emergency department."
        ),
    }
