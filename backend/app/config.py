"""VitalRoute configuration — all values per docs/04 mathematical spec."""

# Pillar 1: Capacity-Confidence Engine
LAMBDA_DECAY = 0.046            # ln(2)/15 -> 15-minute freshness half-life
STALE_THRESHOLD = 0.50          # F(t) < 0.50 => "Unverified / Stale"
UNCERTAINTY_SIGMA = 2.0         # sigma_uncertainty penalty on stale beds

# Pillar 2: TTDC Optimizer
OFFLOAD_BETA = 6.0              # minutes per active ED boarder
OFFLOAD_GAMMA = 4.0             # minutes per inbound ambulance ahead
READINESS_ON_CALL_MIN = 17.5    # 15-20 min specialist call-in
READINESS_UNAVAILABLE_MIN = float("inf")
ROAD_FACTOR = 1.35              # Haversine -> road distance correction
AVG_SPEED_KMH = 38.0            # urban ambulance average speed

# Pillar 3: Handshake
HANDSHAKE_TIMEOUT_SEC = 180     # deterministic fallback per doc Blocker 3

# Clinical risk bands (NEWS2, Royal College of Physicians)
NEWS2_BANDS = [(0, "LOW"), (4, "LOW-MEDIUM"), (6, "MEDIUM"), (20, "HIGH")]

